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
        expected_hash = compute_accept_payload_hash(
            dispute_id=dispute_id, amount=orig.amount
        )

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
            ev_dict = (
                evidence.model_dump()
                if isinstance(evidence, RazorpayEvidence)
                else evidence
            )
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

            except (
                httpx.ConnectError,
                httpx.ReadTimeout,
                httpx.WriteTimeout,
                httpx.NetworkError,
                httpx.TimeoutException,
            ):
                if attempt == self.max_retries - 1:
                    raise

            # Exponential backoff before next attempt
            sleep_duration = self.backoff_factor * (2**attempt)
            time.sleep(sleep_duration)

        if last_resp is not None:
            return last_resp
        raise RuntimeError(f"Request failed after {self.max_retries} attempts.")

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

        result.raise_for_status()
        body = result.json()
        items = body.get("items", [])
        return [RazorpayDispute.model_validate(item) for item in items]

    def fetch_dispute(self, dispute_id: str) -> RazorpayDispute:
        """Fetch dispute with ID: GET /v1/disputes/:id (Docs: https://razorpay.com/docs/api/disputes/#fetch-a-dispute-with-id)."""
        result = self._execute_with_retry("GET", f"/v1/disputes/{dispute_id}")
        if isinstance(result, RazorpayDispute):
            return result

        result.raise_for_status()
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
        expected_hash = compute_accept_payload_hash(
            dispute_id=dispute_id, amount=current.amount
        )
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

        result.raise_for_status()
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

        payload: dict[str, Any] = {"action": act}
        if summary:
            payload["summary"] = summary
        if amount is not None:
            payload["amount"] = amount

        if evidence:
            ev_dict = (
                evidence.model_dump()
                if isinstance(evidence, RazorpayEvidence)
                else evidence
            )
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

        result.raise_for_status()
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
        import mimetypes

        idem_key = idempotency_key or f"doc_{uuid.uuid4().hex}"
        mime_type = mimetypes.guess_type(file_name)[0] or "application/pdf"
        files = {"file": (file_name, file_content, mime_type)}
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

        result.raise_for_status()
        return result.json()


class HybridGateway(DisputesGateway):
    """Hybrid gateway: live RazorpayGateway for API writes, SimGateway for case data.

    This is the recommended mode for development and demos. Since Razorpay test
    accounts typically contain zero disputes, case listing and fetching fall
    through to local JSON fixtures so the UI stays populated. If a dispute
    exists on live Razorpay, accept and contest submit call the real Razorpay API.
    If a dispute only exists in local case data (sim), accept and contest route
    to SimGateway. Document uploads go to the real Razorpay Documents API with
    fallback to local storage.

    For contest(action="draft"), SimGateway is used (saves to disk only).
    """

    def __init__(
        self,
        live: RazorpayGateway,
        sim: SimGateway,
    ) -> None:
        self.live = live
        self.sim = sim

    def list_disputes(
        self,
        status: str | None = None,
        phase: str | None = None,
        limit: int = 10,
        skip: int = 0,
        count: int | None = None,
    ) -> list[RazorpayDispute]:
        """Try live API first; if it returns nothing, fall back to sim data."""
        try:
            live_results = self.live.list_disputes(
                status=status,
                phase=phase,
                limit=limit,
                skip=skip,
                count=count,
            )
            if live_results:
                return live_results
            logger.info(
                "Live Razorpay returned 0 disputes; falling back to local case data."
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Live list_disputes failed (%s); falling back to sim.", exc)
        return self.sim.list_disputes(
            status=status,
            phase=phase,
            limit=limit,
            skip=skip,
            count=count,
        )

    def fetch_dispute(self, dispute_id: str) -> RazorpayDispute:
        """Try live API; fall back to sim on 404 or error."""
        try:
            return self.live.fetch_dispute(dispute_id)
        except Exception:  # noqa: BLE001
            logger.debug("Live fetch_dispute(%s) failed; trying sim.", dispute_id)
        return self.sim.fetch_dispute(dispute_id)

    def _is_live_dispute(self, dispute_id: str) -> bool:
        """Check if dispute exists on live Razorpay API."""
        try:
            self.live.fetch_dispute(dispute_id)
            return True
        except Exception:  # noqa: BLE001
            return False

    def accept_dispute(
        self,
        dispute_id: str,
        approval_token: str,
        idempotency_key: str | None = None,
    ) -> RazorpayDispute:
        """Route accept to live API if dispute exists on Razorpay; fall back to sim."""
        if self._is_live_dispute(dispute_id):
            return self.live.accept_dispute(
                dispute_id=dispute_id,
                approval_token=approval_token,
                idempotency_key=idempotency_key,
            )
        return self.sim.accept_dispute(
            dispute_id=dispute_id,
            approval_token=approval_token,
            idempotency_key=idempotency_key,
        )

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
        """Route draft to sim (local save); route submit to live API if dispute is on Razorpay, else sim."""
        if action.lower() == "draft":
            return self.sim.contest_dispute(
                dispute_id=dispute_id,
                action="draft",
                summary=summary,
                amount=amount,
                evidence=evidence,
            )
        if self._is_live_dispute(dispute_id):
            return self.live.contest_dispute(
                dispute_id=dispute_id,
                action=action,
                summary=summary,
                amount=amount,
                evidence=evidence,
                approval_token=approval_token,
                idempotency_key=idempotency_key,
            )
        return self.sim.contest_dispute(
            dispute_id=dispute_id,
            action=action,
            summary=summary,
            amount=amount,
            evidence=evidence,
            approval_token=approval_token,
            idempotency_key=idempotency_key,
        )

    def upload_document(
        self,
        file_content: bytes,
        file_name: str,
        purpose: str = "dispute_evidence",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Upload to live Razorpay Documents API, fallback to sim if it fails."""
        try:
            return self.live.upload_document(
                file_content=file_content,
                file_name=file_name,
                purpose=purpose,
                idempotency_key=idempotency_key,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Live upload_document failed (%s); falling back to sim.", exc
            )
            return self.sim.upload_document(
                file_content=file_content,
                file_name=file_name,
                purpose=purpose,
                idempotency_key=idempotency_key,
            )


def create_gateway(
    approval_service: ApprovalService | None = None,
    data_dir: Path | str = "data/cases",
    drafts_dir: Path | str = "data/drafts",
) -> DisputesGateway:
    """Factory: build the right gateway from environment variables.

    Env vars consulted:
        RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET — Razorpay test credentials.
        GATEWAY_MODE — "live", "hybrid", or "sim" (default: auto-detect).

    Selection logic:
        - "sim" → SimGateway (pure local, no Razorpay calls).
        - "live" → RazorpayGateway (all calls go to Razorpay; fails if 0 test disputes).
        - "hybrid" → HybridGateway (live writes, sim reads).
        - unset/auto → hybrid if credentials present, else sim.
    """
    import os

    svc = approval_service or ApprovalService()
    key_id = (os.environ.get("RAZORPAY_KEY_ID") or "").strip()
    key_secret = (os.environ.get("RAZORPAY_KEY_SECRET") or "").strip()
    mode = (os.environ.get("GATEWAY_MODE") or "").strip().lower()

    sim = SimGateway(
        data_dir=Path(data_dir),
        drafts_dir=Path(drafts_dir),
        approval_service=svc,
    )

    has_creds = bool(key_id and key_secret and key_id.startswith("rzp_test_"))

    if mode == "sim" or (not mode and not has_creds):
        logger.info("Gateway mode: sim (local case data only).")
        return sim

    if not has_creds:
        logger.warning(
            "GATEWAY_MODE=%s but RAZORPAY_KEY_ID/KEY_SECRET not set or not test-mode. "
            "Falling back to sim.",
            mode,
        )
        return sim

    live = RazorpayGateway(
        key_id=key_id,
        key_secret=key_secret,
        approval_service=svc,
    )

    if mode == "live":
        logger.info("Gateway mode: live (all calls to Razorpay API).")
        return live

    # Default: hybrid
    logger.info(
        "Gateway mode: hybrid (live Razorpay for writes, local case data for reads)."
    )
    return HybridGateway(live=live, sim=sim)
