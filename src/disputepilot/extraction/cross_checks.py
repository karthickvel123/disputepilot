"""Deterministic cross-check auditing between dispute records, order data, and extracted evidence."""

import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from disputepilot.core.models import DisputeCase
from disputepilot.extraction.extractor import ExtractedDocument


class Severity(str, Enum):
    """Severity tier for cross-check discrepancies."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


SeverityTier = Severity


class CrossCheckFlag(BaseModel):
    """Audit flag describing an inconsistency between evidence and case metadata."""

    flag_code: str
    severity: Severity
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


def check_delivery_after_dispute(
    delivery_epoch: int | None,
    dispute_created_at: int,
) -> CrossCheckFlag | None:
    """Flag if delivery was recorded after the dispute was filed."""
    if delivery_epoch is not None and delivery_epoch > dispute_created_at:
        return CrossCheckFlag(
            flag_code="DELIVERY_AFTER_DISPUTE",
            severity=Severity.CRITICAL,
            message=(
                f"Courier delivery recorded at epoch {delivery_epoch}, which is after "
                f"the dispute was filed at epoch {dispute_created_at}."
            ),
            details={
                "delivery_epoch": delivery_epoch,
                "dispute_created_at": dispute_created_at,
                "difference_seconds": delivery_epoch - dispute_created_at,
            },
        )
    return None


def check_invoice_amount_mismatch(
    invoice_amount_paise: int | None,
    dispute_amount_paise: int,
) -> CrossCheckFlag | None:
    """Flag if the billing proof invoice amount differs from disputed amount."""
    if invoice_amount_paise is not None and invoice_amount_paise != dispute_amount_paise:
        return CrossCheckFlag(
            flag_code="INVOICE_AMOUNT_MISMATCH",
            severity=Severity.HIGH,
            message=(
                f"Invoice grand total (INR {invoice_amount_paise / 100:.2f}) does not match "
                f"the disputed amount (INR {dispute_amount_paise / 100:.2f})."
            ),
            details={
                "invoice_amount_paise": invoice_amount_paise,
                "dispute_amount_paise": dispute_amount_paise,
                "difference_paise": abs(invoice_amount_paise - dispute_amount_paise),
            },
        )
    return None


def _normalize_address_tokens(address: str) -> set[str]:
    """Tokenize and normalize address string into salient words."""
    # Remove punctuation and split on whitespace
    cleaned = re.sub(r"[^\w\s]", " ", address.lower())
    tokens = {t.strip() for t in cleaned.split() if len(t.strip()) > 1}
    # Remove generic stop words that don't distinguish addresses
    stop_words = {"india", "street", "road", "flat", "floor", "near", "sector", "opp", "behind"}
    return tokens - stop_words


def check_address_mismatch(
    delivery_address: str | None,
    shipping_address: str | None,
    threshold: float = 0.5,
) -> CrossCheckFlag | None:
    """Flag if POD delivery destination diverges from order shipping address."""
    if not delivery_address or not shipping_address:
        return None

    tokens_del = _normalize_address_tokens(delivery_address)
    tokens_ship = _normalize_address_tokens(shipping_address)

    if not tokens_del or not tokens_ship:
        return None

    overlap = len(tokens_del & tokens_ship) / len(tokens_del | tokens_ship)
    if overlap < threshold:
        return CrossCheckFlag(
            flag_code="ADDRESS_MISMATCH",
            severity=Severity.HIGH,
            message=(
                f"Delivery address on courier proof has only {overlap:.0%} normalized token "
                f"overlap with the order shipping address."
            ),
            details={
                "delivery_address": delivery_address,
                "shipping_address": shipping_address,
                "token_overlap": round(overlap, 3),
                "threshold": threshold,
            },
        )
    return None


def check_refund_not_mentioned(
    has_refund: bool,
    refund_mentioned_in_comms: bool | None,
    refund_amount_paise: int | None = None,
) -> CrossCheckFlag | None:
    """Flag if a refund exists in merchant records but is unmentioned in customer chat."""
    if has_refund and refund_mentioned_in_comms is False:
        return CrossCheckFlag(
            flag_code="REFUND_EXISTS_UNMENTIONED",
            severity=Severity.MEDIUM,
            message=(
                "A processed refund exists in merchant records, but customer communications "
                "do not mention or confirm receipt of this refund."
            ),
            details={
                "has_refund": has_refund,
                "refund_mentioned_in_comms": refund_mentioned_in_comms,
                "refund_amount_paise": refund_amount_paise,
            },
        )
    return None


def _extract_val(field: Any) -> Any:
    if hasattr(field, "value"):
        return field.value
    if isinstance(field, dict) and "value" in field:
        return field["value"]
    return field


def run_cross_checks(
    case: DisputeCase,
    extracted_docs: list[ExtractedDocument],
) -> list[CrossCheckFlag]:
    """Execute all deterministic cross-checks over case records and extracted evidence.

    Args:
        case: DisputeCase containing dispute, order, and refund data.
        extracted_docs: List of safely extracted documents for this case.

    Returns:
        List of generated CrossCheckFlag objects.
    """
    flags: list[CrossCheckFlag] = []

    # 1. Inspect Delivery Proofs
    delivery_epoch: int | None = None
    delivery_address: str | None = None

    for doc in extracted_docs:
        if "delivery_epoch" in doc.surviving_fields:
            field = doc.surviving_fields["delivery_epoch"]
            delivery_epoch = _extract_val(field)
        elif "delivery_date" in doc.surviving_fields and delivery_epoch is None:
            # Fallback to order delivery timestamp if epoch not explicitly extracted
            delivery_epoch = case.order.delivered_at

        if "delivery_address" in doc.surviving_fields:
            delivery_address = _extract_val(doc.surviving_fields["delivery_address"])

    if delivery_epoch is None and case.order.delivered_at is not None:
        delivery_epoch = case.order.delivered_at

    flag_del = check_delivery_after_dispute(
        delivery_epoch=delivery_epoch,
        dispute_created_at=case.dispute.created_at,
    )
    if flag_del:
        flags.append(flag_del)

    # 2. Inspect Invoices for amount mismatch
    invoice_amount_paise: int | None = None
    for doc in extracted_docs:
        if "total_amount_paise" in doc.surviving_fields:
            invoice_amount_paise = _extract_val(doc.surviving_fields["total_amount_paise"])
            break

    if invoice_amount_paise is not None:
        flag_amt = check_invoice_amount_mismatch(
            invoice_amount_paise=invoice_amount_paise,
            dispute_amount_paise=case.dispute.amount,
        )
        if flag_amt:
            flags.append(flag_amt)

    # 3. Address match between POD and Order
    if delivery_address and case.order.shipping_address:
        flag_addr = check_address_mismatch(
            delivery_address=delivery_address,
            shipping_address=case.order.shipping_address,
        )
        if flag_addr:
            flags.append(flag_addr)

    # 4. Refund existence vs customer communication
    refund_mentioned: bool | None = None
    for doc in extracted_docs:
        if "refund_mentioned" in doc.surviving_fields:
            refund_mentioned = _extract_val(doc.surviving_fields["refund_mentioned"])
            break

    has_refund = case.refund is not None and case.refund.status == "processed"
    refund_paise = case.refund.amount if case.refund else None

    flag_ref = check_refund_not_mentioned(
        has_refund=has_refund,
        refund_mentioned_in_comms=refund_mentioned,
        refund_amount_paise=refund_paise,
    )
    if flag_ref:
        flags.append(flag_ref)

    return flags
