import hashlib
import json
import logging
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from disputepilot.core.models import (
    DisputeCase,
    DisputeStatus,
    RazorpayDispute,
    RazorpayEvidence,
)
from disputepilot.razorpay.approval import (
    ApprovalService,
    compute_accept_payload_hash,
    compute_contest_payload_hash,
)

logger = logging.getLogger("disputepilot.razorpay.gateway")

# UNVERIFIED: Razorpay documentation is ambiguous on whether X-Razorpay-Idempotency-Key
# or standard Idempotency-Key is recognized/required by the Disputes API.
# Both headers are sent on all mutating requests for defensive compatibility.
IDEMPOTENCY_HEADERS: tuple[str, ...] = ("X-Razorpay-Idempotency-Key", "Idempotency-Key")


CONTEST_SUMMARY_MAX_CHARS = 1000  # Razorpay: "summary ... maximum length of 1000 characters"


class RazorpayAPIError(httpx.HTTPStatusError):
    """Non-2xx Razorpay response carrying Razorpay's own error description.

    Subclasses ``httpx.HTTPStatusError`` so existing ``except httpx.HTTPStatusError`` handlers
    still work. The message never includes credentials or the raw response body.
    """

    def __init__(self, response: httpx.Response) -> None:
        self.status_code = response.status_code
        self.code = ""
        self.description = ""
        try:
            err = response.json().get("error", {})
            self.code = str(err.get("code", ""))
            self.description = str(err.get("description", ""))
        except (ValueError, AttributeError):
            pass
        detail = self.description or f"HTTP {response.status_code}"
        try:
            request = response.request
        except RuntimeError:  # response built without a request (e.g. in tests)
            request = httpx.Request("GET", "https://api.razorpay.com")
        super().__init__(
            f"Razorpay API error ({response.status_code}): {detail}",
            request=request,
            response=response,
        )


def _raise_for_status(resp: httpx.Response) -> None:
    if resp.status_code >= 400:
        raise RazorpayAPIError(resp)


class DisputesGateway(ABC):
    """Abstract interface for dispute operations and document uploads."""

    @abstractmethod
    def list_disputes(
        self,
        status: str | None = None,
        phase: str | None = None,
        limit: int = 10,
        skip: int = 0,
        count: int | None = None,
    ) -> list[RazorpayDispute]:
        """List disputes with optional filtering and pagination."""

    @abstractmethod
    def fetch_dispute(self, dispute_id: str) -> RazorpayDispute:
        """Fetch a single dispute by its ID."""

    @abstractmethod
    def accept_dispute(
        self,
        dispute_id: str,
        approval_token: str,
        idempotency_key: str | None = None,
    ) -> RazorpayDispute:
        """Accept a dispute. Requires a valid human approval token."""

    @abstractmethod
    def contest_dispute(
        self,
        dispute_id: str,
        action: str,  # 'draft' or 'submit'
        summary: str | None = None,
        amount: int | None = None,
        evidence: dict[str, list[str]] | RazorpayEvidence | None = None,
        approval_token: str | None = None,
        idempotency_key: str | None = None,
    ) -> RazorpayDispute:
        """Contest a dispute with 'draft' or 'submit'. 'submit' requires an approval token."""

    @abstractmethod
    def upload_document(
        self,
        file_content: bytes,
        file_name: str,
        purpose: str = "dispute_evidence",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Upload an evidence document to Razorpay Documents API."""


class SimGateway(DisputesGateway):
    """Simulated gateway implementation reading from data/cases and writing to data/drafts."""

    def __init__(
        self,
        data_dir: Path | str = "data/cases",
        drafts_dir: Path | str = "data/drafts",
        approval_service: ApprovalService | None = None,
        simulated_accept_status: DisputeStatus | str | None = None,
        simulated_submit_status: DisputeStatus | str | None = None,
    ) -> None:
        """Initialize the simulator gateway.

        Args:
            data_dir: Path to directory containing case JSON files.
            drafts_dir: Path to directory for persisting contested drafts.
            approval_service: Service for human approval token verification.
            simulated_accept_status: Optional simulated status on accept (if None, status remains unchanged).
            simulated_submit_status: Optional simulated status on submit (if None, status remains unchanged).
        """
        self.data_dir = Path(data_dir)
        self.drafts_dir = Path(drafts_dir)
        self.drafts_dir.mkdir(parents=True, exist_ok=True)
        self.approval_service = approval_service or ApprovalService()
        self.simulated_accept_status = (
            DisputeStatus(simulated_accept_status)
            if isinstance(simulated_accept_status, str)
            else simulated_accept_status
        )
        self.simulated_submit_status = (
            DisputeStatus(simulated_submit_status)
            if isinstance(simulated_submit_status, str)
            else simulated_submit_status
        )
        self._memory_overrides: dict[str, RazorpayDispute] = {}

    def _load_all_cases(self) -> list[DisputeCase]:
        cases: list[DisputeCase] = []
        if not self.data_dir.exists():
            return cases

        for jf in sorted(self.data_dir.glob("*.json")):
            try:
                with open(jf, encoding="utf-8") as f:
                    data = json.load(f)
                cases.append(DisputeCase.model_validate(data))
            except (json.JSONDecodeError, OSError, ValueError):
                pass
        return cases

    def list_disputes(
        self,
        status: str | None = None,
        phase: str | None = None,
        limit: int = 10,
        skip: int = 0,
        count: int | None = None,
    ) -> list[RazorpayDispute]:
        effective_limit = count if count is not None else limit
        cases = self._load_all_cases()
        disputes: list[RazorpayDispute] = []

        for c in cases:
            disp = self._memory_overrides.get(c.dispute.id, c.dispute)
            if status and disp.status.value != status.lower():
                continue
            if phase and disp.phase.value != phase.lower():
                continue
            disputes.append(disp)

        return disputes[skip : skip + effective_limit]

    def fetch_dispute(self, dispute_id: str) -> RazorpayDispute:
        if dispute_id in self._memory_overrides:
            return self._memory_overrides[dispute_id]

        cases = self._load_all_cases()
        for c in cases:
            if c.dispute.id == dispute_id or c.case_id == dispute_id:
                return c.dispute

        raise KeyError(f"Dispute '{dispute_id}' not found in simulation data.")

    def accept_dispute(
        self,
        dispute_id: str,
        approval_token: str,
        idempotency_key: str | None = None,
    ) -> RazorpayDispute:
        orig = self.fetch_dispute(dispute_id)
        expected_hash = compute_accept_payload_hash(dispute_id=dispute_id, amount=orig.amount)

        self.approval_service.require_approval(
            token=approval_token,
            action="accept",
            dispute_id=dispute_id,
            expected_payload_hash=expected_hash,
        )

        # Do NOT assume status (e.g. 'lost' or 'closed'). Use simulated status if specified, otherwise keep orig.
        update_fields: dict[str, Any] = {}
        if self.simulated_accept_status is not None:
            update_fields["status"] = self.simulated_accept_status
        updated = orig.model_copy(update=update_fields) if update_fields else orig
        self._memory_overrides[dispute_id] = updated
        return updated

    def contest_dispute(
        self,
        dispute_id: str,
        action: str,
        summary: str | None = None,
        amount: int | None = None,
        evidence: dict[str, list[str]] | RazorpayEvidence | None = None,
        approval_token: str | None = None,
        idempotency_key: str | None = None,
    ) -> RazorpayDispute:
        act = action.lower()
        orig = self.fetch_dispute(dispute_id)

        evidence_obj = orig.evidence.model_copy()
        if evidence:
            ev_dict = evidence.model_dump() if isinstance(evidence, RazorpayEvidence) else evidence
            for k, v in ev_dict.items():
                if hasattr(evidence_obj, k) and isinstance(v, list):
                    setattr(evidence_obj, k, v)

        # Construct exact contest payload
        payload: dict[str, Any] = {"action": act}
        if summary:
            payload["summary"] = summary
        if amount is not None:
            payload["amount"] = amount
        ev_dump = evidence_obj.model_dump()
        for k, v in ev_dump.items():
            if v:
                payload[k] = v

        if act == "submit":
            expected_hash = compute_contest_payload_hash(payload)
            self.approval_service.require_approval(
                token=approval_token,
                action="submit",
                dispute_id=dispute_id,
                expected_payload_hash=expected_hash,
            )

        if act == "draft":
            draft_path = self.drafts_dir / f"{dispute_id}_draft.json"
            draft_data = {
                "dispute_id": dispute_id,
                "action": "draft",
                "summary": summary,
                "amount": amount or orig.amount,
                "evidence": evidence_obj.model_dump(),
                "saved_at": int(time.time()),
            }
            with open(draft_path, "w", encoding="utf-8") as f:
                json.dump(draft_data, f, indent=2)
            updated = orig.model_copy(update={"evidence": evidence_obj})
        else:
            # Do NOT assume status (e.g. 'under_review' or 'submitted'). Use simulated status if specified.
            update_fields: dict[str, Any] = {"evidence": evidence_obj}
            if self.simulated_submit_status is not None:
                update_fields["status"] = self.simulated_submit_status
            updated = orig.model_copy(update=update_fields)

        self._memory_overrides[dispute_id] = updated
        return updated

    def upload_document(
        self,
        file_content: bytes,
        file_name: str,
        purpose: str = "dispute_evidence",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        content_hash = hashlib.sha256(file_content).hexdigest()[:12]
        doc_id = f"doc_sim_{content_hash}"
        saved_file = self.drafts_dir / f"{doc_id}_{file_name}"
        with open(saved_file, "wb") as f:
            f.write(file_content)

        return {
            "id": doc_id,
            "entity": "document",
            "purpose": purpose,
            "name": file_name,
            "size": len(file_content),
            "created_at": int(time.time()),
        }


class RazorpayGateway(DisputesGateway):
    """Production Razorpay gateway using HTTPX with Basic Auth, retries, and idempotency."""

    def __init__(
        self,
        key_id: str,
        key_secret: str,
        base_url: str = "https://api.razorpay.com",
        approval_service: ApprovalService | None = None,
        client: httpx.Client | None = None,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
    ) -> None:
        """Initialize RazorpayGateway.

        Docs: https://razorpay.com/docs/api/disputes/
        """
        self.key_id = key_id
        self.key_secret = key_secret
        self.base_url = base_url.rstrip("/")
        self.approval_service = approval_service or ApprovalService()
        self.client = client or httpx.Client(timeout=30.0)
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.last_status_code: int | None = None

    def _execute_with_retry(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        pre_retry_check: Callable[[], RazorpayDispute | None] | None = None,
    ) -> httpx.Response | RazorpayDispute:
        """Execute HTTP request with idempotency keys and exponential backoff retry on 5xx/429.

        Before retrying, if pre_retry_check returns an updated dispute whose status changed,
        retrying halts immediately and that dispute is returned.
        """
        url = f"{self.base_url}{path}"
        headers: dict[str, str] = {}

        if idempotency_key:
            for header_name in IDEMPOTENCY_HEADERS:
                headers[header_name] = idempotency_key

        auth = httpx.BasicAuth(self.key_id, self.key_secret)

        last_resp: httpx.Response | None = None
        for attempt in range(self.max_retries):
            # Before retrying (attempts > 0), run pre-retry check if configured
            if attempt > 0 and pre_retry_check is not None:
                updated_dispute = pre_retry_check()
                if updated_dispute is not None:
                    # Status already changed on server; do not resend request!
                    return updated_dispute

            try:
                resp = self.client.request(
                    method=method,
                    url=url,
                    auth=auth,
                    headers=headers,
                    params=params,
                    json=json_data,
                    files=files,
                    data=data,
                )
                last_resp = resp
                self.last_status_code = resp.status_code

                # If successful or not a retryable error, return response immediately
                if resp.status_code not in (429, 500, 502, 503, 504):
                    return resp

            except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout, httpx.NetworkError, httpx.TimeoutException):
                if pre_retry_check is not None:
                    updated_dispute = pre_retry_check()
                    if updated_dispute is not None:
                        return updated_dispute
                if attempt == self.max_retries - 1:
                    raise

            # Exponential backoff before next attempt
            sleep_duration = self.backoff_factor * (2**attempt)
            time.sleep(sleep_duration)

        if pre_retry_check is not None:
            updated_dispute = pre_retry_check()
            if updated_dispute is not None:
                return updated_dispute

        if last_resp is not None:
            return last_resp
        raise RuntimeError(f"Request failed after {self.max_retries} attempts.")

    def request_json(self, method: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Authenticated, retried JSON request. Reads only; mutating calls have dedicated methods."""
        if method.upper() != "GET":
            raise ValueError("request_json is read-only; use the dedicated mutating methods.")
        result = self._execute_with_retry("GET", path, params=params)
        if isinstance(result, RazorpayDispute):
            raise TypeError("Unexpected dispute response from generic request.")
        _raise_for_status(result)
        body = result.json()
        return body if isinstance(body, dict) else {"items": body}

    def list_disputes(
        self,
        status: str | None = None,
        phase: str | None = None,
        limit: int = 10,
        skip: int = 0,
        count: int | None = None,
    ) -> list[RazorpayDispute]:
        """Fetch all disputes: GET /v1/disputes (Docs: https://razorpay.com/docs/api/disputes/#fetch-all-disputes)."""
        effective_limit = count if count is not None else limit
        params: dict[str, Any] = {"count": effective_limit, "skip": skip}
        if status:
            params["status"] = status
        if phase:
            params["phase"] = phase

        result = self._execute_with_retry("GET", "/v1/disputes", params=params)
        if isinstance(result, RazorpayDispute):
            return [result]

        _raise_for_status(result)
        body = result.json()
        items = body.get("items", [])
        return [RazorpayDispute.model_validate(item) for item in items]

    def fetch_dispute(self, dispute_id: str) -> RazorpayDispute:
        """Fetch dispute with ID: GET /v1/disputes/:id (Docs: https://razorpay.com/docs/api/disputes/#fetch-a-dispute-with-id)."""
        result = self._execute_with_retry("GET", f"/v1/disputes/{dispute_id}")
        if isinstance(result, RazorpayDispute):
            return result

        _raise_for_status(result)
        return RazorpayDispute.model_validate(result.json())

    def accept_dispute(
        self,
        dispute_id: str,
        approval_token: str,
        idempotency_key: str | None = None,
    ) -> RazorpayDispute:
        """Accept a dispute: POST /v1/disputes/:id/accept (Docs: https://razorpay.com/docs/api/disputes/#accept-a-dispute)."""
        current = self.fetch_dispute(dispute_id)
        initial_status = current.status

        # Recompute accept payload hash (dispute_id and amount) at call time
        expected_hash = compute_accept_payload_hash(dispute_id=dispute_id, amount=current.amount)
        self.approval_service.require_approval(
            token=approval_token,
            action="accept",
            dispute_id=dispute_id,
            expected_payload_hash=expected_hash,
        )

        idem_key = idempotency_key or f"acc_{uuid.uuid4().hex}"

        def pre_retry_status_check() -> RazorpayDispute | None:
            try:
                rechecked = self.fetch_dispute(dispute_id)
                if rechecked.status != initial_status:
                    return rechecked
            except (httpx.HTTPError, KeyError, ValueError) as err:
                logger.debug("Failed to re-check dispute status before retry: %s", err)
            return None

        result = self._execute_with_retry(
            method="POST",
            path=f"/v1/disputes/{dispute_id}/accept",
            idempotency_key=idem_key,
            pre_retry_check=pre_retry_status_check,
        )
        if isinstance(result, RazorpayDispute):
            return result

        _raise_for_status(result)
        # Read status from API response; do not assume what status it moved to
        return RazorpayDispute.model_validate(result.json())

    def contest_dispute(
        self,
        dispute_id: str,
        action: str,
        summary: str | None = None,
        amount: int | None = None,
        evidence: dict[str, list[str]] | RazorpayEvidence | None = None,
        approval_token: str | None = None,
        idempotency_key: str | None = None,
    ) -> RazorpayDispute:
        """Contest a dispute: PATCH /v1/disputes/:id/contest (Docs: https://razorpay.com/docs/api/disputes/#contest-a-dispute)."""
        act = action.lower()

        if summary and len(summary) > CONTEST_SUMMARY_MAX_CHARS:
            raise ValueError(
                f"Contest summary is {len(summary)} characters; Razorpay allows at most "
                f"{CONTEST_SUMMARY_MAX_CHARS}. Shorten it and attach the full letter as a document."
            )

        payload: dict[str, Any] = {"action": act}
        if summary:
            payload["summary"] = summary
        if amount is not None:
            payload["amount"] = amount

        if evidence:
            ev_dict = evidence.model_dump() if isinstance(evidence, RazorpayEvidence) else evidence
            for k, v in ev_dict.items():
                if v:
                    payload[k] = v

        initial_status: DisputeStatus | None = None
        if act == "submit":
            current = self.fetch_dispute(dispute_id)
            initial_status = current.status

            # Recompute contest payload hash at call time
            expected_hash = compute_contest_payload_hash(payload)
            self.approval_service.require_approval(
                token=approval_token,
                action="submit",
                dispute_id=dispute_id,
                expected_payload_hash=expected_hash,
            )

        idem_key = idempotency_key or f"cnt_{uuid.uuid4().hex}"

        def pre_retry_status_check() -> RazorpayDispute | None:
            if initial_status is None:
                return None
            try:
                rechecked = self.fetch_dispute(dispute_id)
                if rechecked.status != initial_status:
                    return rechecked
            except (httpx.HTTPError, KeyError, ValueError) as err:
                logger.debug("Failed to re-check dispute status before retry: %s", err)
            return None

        result = self._execute_with_retry(
            method="PATCH",
            path=f"/v1/disputes/{dispute_id}/contest",
            json_data=payload,
            idempotency_key=idem_key,
            pre_retry_check=pre_retry_status_check if act == "submit" else None,
        )
        if isinstance(result, RazorpayDispute):
            return result

        _raise_for_status(result)
        # Read status from API response; do not assume what status it moved to
        return RazorpayDispute.model_validate(result.json())

    def upload_document(
        self,
        file_content: bytes,
        file_name: str,
        purpose: str = "dispute_evidence",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Upload document: POST /v1/documents (Docs: https://razorpay.com/docs/api/documents/#upload-a-document)."""
        idem_key = idempotency_key or f"doc_{uuid.uuid4().hex}"
        files = {"file": (file_name, file_content)}
        data = {"purpose": purpose}

        result = self._execute_with_retry(
            method="POST",
            path="/v1/documents",
            files=files,
            data=data,
            idempotency_key=idem_key,
        )
        if isinstance(result, RazorpayDispute):
            raise TypeError("Unexpected dispute response from document upload.")

        _raise_for_status(result)
        return result.json()
