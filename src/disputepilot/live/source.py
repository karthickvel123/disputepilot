"""Live case source: assembles a ``DisputeCase`` from Razorpay APIs plus the evidence locker.

Failure policy: the dispute itself is mandatory (without it there is no case). Every enrichment
(payment, order, refunds, merchant notes) is optional - if one fails or is empty, the case still
loads and the gap is recorded in ``case.metadata["data_gaps"]`` so the UI can say exactly what is
missing instead of showing a blank or broken page.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

from disputepilot.core.models import (
    DisputeCase,
    EvidenceDocument,
    Order,
    RazorpayDispute,
    Refund,
)
from disputepilot.live.locker import EvidenceLocker
from disputepilot.razorpay.commerce import (
    RazorpayCommerceClient,
    order_from_razorpay,
    refund_from_razorpay,
)
from disputepilot.razorpay.gateway import RazorpayAPIError, RazorpayGateway

logger = logging.getLogger("disputepilot.live.source")

PAGE_SIZE = 100  # Razorpay list endpoints cap `count` at 100
MAX_PAGES = 5


class CaseNotFound(LookupError):
    """The dispute does not exist (or does not belong to these credentials)."""


class SourceError(RuntimeError):
    """Razorpay could not be reached or rejected the request; message is safe to show."""


def describe_error(exc: Exception) -> str:
    """User-safe description of an upstream failure (never includes keys or response bodies)."""
    if isinstance(exc, RazorpayAPIError):
        if exc.status_code in (401, 403):
            return "Razorpay rejected the API credentials (check RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET)."
        return exc.description or f"Razorpay returned HTTP {exc.status_code}."
    if isinstance(exc, httpx.HTTPStatusError):  # e.g. persistent 5xx after retries
        return f"Razorpay is unavailable right now (HTTP {exc.response.status_code})."
    if isinstance(exc, httpx.TimeoutException):
        return "Razorpay did not respond in time."
    if isinstance(exc, httpx.HTTPError):
        return "Could not reach Razorpay (network error)."
    return f"Unexpected error: {type(exc).__name__}."


class LiveCaseSource:
    def __init__(
        self,
        gateway: RazorpayGateway,
        locker: EvidenceLocker,
        cache_ttl: int = 30,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.gateway = gateway
        self.commerce = RazorpayCommerceClient(gateway)
        self.locker = locker
        self.cache_ttl = cache_ttl
        self._clock = clock
        self._cache: tuple[float, list[RazorpayDispute]] | None = None

    # ---- worklist ---------------------------------------------------------------------------
    def list_disputes(self, force: bool = False) -> tuple[list[RazorpayDispute], str | None]:
        """All disputes (paginated). Returns (disputes, error). On failure serves the last good
        list if there is one so the worklist degrades instead of disappearing."""
        now = self._clock()
        if not force and self._cache and now - self._cache[0] < self.cache_ttl:
            return self._cache[1], None
        try:
            collected: list[RazorpayDispute] = []
            for page in range(MAX_PAGES):
                batch = self.gateway.list_disputes(limit=PAGE_SIZE, skip=page * PAGE_SIZE)
                collected.extend(batch)
                if len(batch) < PAGE_SIZE:
                    break
            self._cache = (now, collected)
            return collected, None
        except Exception as exc:  # noqa: BLE001 - boundary: must never take the page down
            logger.warning("Listing disputes failed: %s", type(exc).__name__)
            msg = describe_error(exc)
            if self._cache:
                return self._cache[1], f"{msg} Showing the last successful sync."
            return [], msg

    def invalidate(self) -> None:
        self._cache = None

    # ---- single case ------------------------------------------------------------------------
    def get_case(self, dispute_id: str) -> DisputeCase:
        try:
            dispute = self.gateway.fetch_dispute(dispute_id)
        except RazorpayAPIError as exc:
            if exc.status_code in (400, 404):
                raise CaseNotFound(f"Dispute '{dispute_id}' not found in Razorpay.") from exc
            raise SourceError(describe_error(exc)) from exc
        except httpx.HTTPError as exc:
            raise SourceError(describe_error(exc)) from exc

        gaps: list[str] = []

        payment: dict[str, Any] = {}
        try:
            payment = self.commerce.fetch_payment(dispute.payment_id)
        except Exception as exc:  # noqa: BLE001
            gaps.append(f"Payment {dispute.payment_id} could not be loaded: {describe_error(exc)}")

        order_entity: dict[str, Any] | None = None
        order_id = payment.get("order_id")
        if order_id:
            try:
                order_entity = self.commerce.fetch_order(str(order_id))
            except Exception as exc:  # noqa: BLE001
                gaps.append(f"Order {order_id} could not be loaded: {describe_error(exc)}")
        elif payment:
            gaps.append("Payment has no order_id, so order details are unavailable.")

        order = (
            order_from_razorpay(payment, order_entity)
            if payment
            else Order(id="unknown", amount=dispute.amount, currency=dispute.currency, created_at=dispute.created_at)
        )

        refund: Refund | None = None
        if payment:
            try:
                refund = refund_from_razorpay(self.commerce.list_refunds(dispute.payment_id))
            except Exception as exc:  # noqa: BLE001
                gaps.append(f"Refunds could not be loaded: {describe_error(exc)}")

        # Merchant-side fulfilment fields Razorpay does not hold (only present if stored in notes).
        if payment:
            if not order.customer_name:
                gaps.append("Customer name is not in Razorpay notes (notes.customer_name).")
            if not order.shipping_address:
                gaps.append("Shipping address is not in Razorpay notes (notes.shipping_address).")
            if not order.tracking_number:
                gaps.append("Tracking number is not in Razorpay notes (notes.tracking_number).")

        documents: list[EvidenceDocument] = []
        for d in self.locker.list_for_dispute(dispute_id):
            documents.append(
                EvidenceDocument(
                    doc_id=f"locker_{d.id}",
                    doc_type=d.category,
                    file_name=d.file_name,
                    file_path=d.razorpay_doc_id or f"locker://{d.id}",
                    content=d.excerpt,
                )
            )
        if not documents and not dispute.evidence.document_ids():
            gaps.append("No evidence files uploaded yet.")

        return DisputeCase(
            case_id=dispute_id,
            dispute=dispute,
            order=order,
            refund=refund,
            documents=documents,
            metadata={"source": "razorpay_live", "data_gaps": gaps},
        )
