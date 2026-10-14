"""Ground-truth fact extraction and representation for rebuttal drafting."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from disputepilot.core.models import DisputeCase
from disputepilot.extraction.extractor import ExtractedDocument


class Fact(BaseModel):
    """An individual verified factual assertion extracted from API records or documents."""

    fact_id: str
    text: str
    source: str
    raw_value: Any = None
    entities: list[str] = Field(default_factory=list)


class FactSet(BaseModel):
    """Collection of verified facts for a dispute case."""

    case_id: str
    facts: list[Fact] = Field(default_factory=list)

    def get_fact(self, fact_id: str) -> Fact | None:
        """Retrieve fact by ID."""
        for f in self.facts:
            if f.fact_id == fact_id:
                return f
        return None

    def fact_ids(self) -> set[str]:
        """Return all available fact IDs."""
        return {f.fact_id for f in self.facts}


def _format_epoch(epoch: int | None) -> str:
    if epoch is None:
        return "N/A"
    try:
        dt = datetime.fromtimestamp(epoch, tz=UTC)
        return f"{dt.strftime('%Y-%m-%d')} ({dt.strftime('%d %B %Y')}, epoch {epoch})"
    except (ValueError, OSError):
        return str(epoch)


def _format_amount(paise: int | None, currency: str = "INR") -> str:
    if paise is None:
        return "N/A"
    rupees = paise / 100.0
    return f"{currency} {rupees:.2f} ({paise} paise, {int(rupees)})"


def build_fact_set(case: DisputeCase, extracted_docs: list[ExtractedDocument]) -> FactSet:
    """Construct an authoritative FactSet from case API records and verified extracted document fields.

    Args:
        case: DisputeCase containing dispute, order, and refund data.
        extracted_docs: List of safely extracted documents with surviving fields.

    Returns:
        FactSet containing verified, citation-ready facts.
    """
    facts: list[Fact] = []

    # 1. Dispute API Records
    disp = case.dispute
    facts.append(
        Fact(
            fact_id="fact_dispute_id",
            text=f"Dispute ID is {disp.id}.",
            source="api:dispute.id",
            raw_value=disp.id,
            entities=[disp.id],
        )
    )
    facts.append(
        Fact(
            fact_id="fact_payment_id",
            text=f"Payment ID associated with dispute is {disp.payment_id}.",
            source="api:dispute.payment_id",
            raw_value=disp.payment_id,
            entities=[disp.payment_id],
        )
    )
    facts.append(
        Fact(
            fact_id="fact_dispute_amount",
            text=f"Disputed amount is {_format_amount(disp.amount, disp.currency)}.",
            source="api:dispute.amount",
            raw_value=disp.amount,
            entities=[str(disp.amount), str(disp.amount // 100), f"{disp.amount / 100:.2f}"],
        )
    )
    facts.append(
        Fact(
            fact_id="fact_dispute_reason",
            text=f"Dispute reason code is {disp.reason_code}.",
            source="api:dispute.reason_code",
            raw_value=disp.reason_code,
            entities=[disp.reason_code] if disp.reason_code else [],
        )
    )
    facts.append(
        Fact(
            fact_id="fact_dispute_created_at",
            text=f"Dispute was initiated on {_format_epoch(disp.created_at)}.",
            source="api:dispute.created_at",
            raw_value=disp.created_at,
            entities=[str(disp.created_at)],
        )
    )
    if disp.respond_by:
        facts.append(
            Fact(
                fact_id="fact_dispute_respond_by",
                text=f"Merchant response deadline is {_format_epoch(disp.respond_by)}.",
                source="api:dispute.respond_by",
                raw_value=disp.respond_by,
                entities=[str(disp.respond_by)],
            )
        )

    # 2. Order API Records
    order = case.order
    if order:
        facts.append(
            Fact(
                fact_id="fact_order_id",
                text=f"Order ID is {order.id}.",
                source="api:order.id",
                raw_value=order.id,
                entities=[order.id],
            )
        )
        facts.append(
            Fact(
                fact_id="fact_customer_name",
                text=f"Customer name on the order is {order.customer_name}.",
                source="api:order.customer_name",
                raw_value=order.customer_name,
                entities=[order.customer_name],
            )
        )
        facts.append(
            Fact(
                fact_id="fact_customer_email",
                text=f"Customer email is {order.customer_email}.",
                source="api:order.customer_email",
                raw_value=order.customer_email,
                entities=[order.customer_email],
            )
        )
        facts.append(
            Fact(
                fact_id="fact_customer_phone",
                text=f"Customer phone number is {order.customer_phone}.",
                source="api:order.customer_phone",
                raw_value=order.customer_phone,
                entities=[order.customer_phone],
            )
        )
        facts.append(
            Fact(
                fact_id="fact_order_amount",
                text=f"Order amount is {_format_amount(order.amount, order.currency)}.",
                source="api:order.amount",
                raw_value=order.amount,
                entities=[str(order.amount), str(order.amount // 100), f"{order.amount / 100:.2f}"],
            )
        )
        facts.append(
            Fact(
                fact_id="fact_order_created_at",
                text=f"Order was placed on {_format_epoch(order.created_at)}.",
                source="api:order.created_at",
                raw_value=order.created_at,
                entities=[str(order.created_at)],
            )
        )
        facts.append(
            Fact(
                fact_id="fact_shipping_address",
                text=f"Shipping address on record is {order.shipping_address}.",
                source="api:order.shipping_address",
                raw_value=order.shipping_address,
                entities=[order.shipping_address],
            )
        )
        facts.append(
            Fact(
                fact_id="fact_order_status",
                text=f"Order fulfillment status is {order.status}.",
                source="api:order.status",
                raw_value=order.status,
                entities=[order.status],
            )
        )
        if order.tracking_number:
            facts.append(
                Fact(
                    fact_id="fact_tracking_number",
                    text=f"Shipment tracking AWB is {order.tracking_number}.",
                    source="api:order.tracking_number",
                    raw_value=order.tracking_number,
                    entities=[order.tracking_number],
                )
            )
        if order.delivered_at:
            facts.append(
                Fact(
                    fact_id="fact_order_delivered_at",
                    text=f"Shipment delivery occurred on {_format_epoch(order.delivered_at)}.",
                    source="api:order.delivered_at",
                    raw_value=order.delivered_at,
                    entities=[str(order.delivered_at)],
                )
            )

    # 3. Refund Records
    if case.refund:
        ref = case.refund
        facts.append(
            Fact(
                fact_id="fact_refund_id",
                text=f"Refund ID is {ref.id} with status '{ref.status}'.",
                source="api:refund.id",
                raw_value=ref.id,
                entities=[ref.id, ref.status],
            )
        )
        facts.append(
            Fact(
                fact_id="fact_refund_amount",
                text=f"Refund amount is {_format_amount(ref.amount, disp.currency)}.",
                source="api:refund.amount",
                raw_value=ref.amount,
                entities=[str(ref.amount), str(ref.amount // 100), f"{ref.amount / 100:.2f}"],
            )
        )
        facts.append(
            Fact(
                fact_id="fact_refund_created_at",
                text=f"Refund was issued on {_format_epoch(ref.created_at)}.",
                source="api:refund.created_at",
                raw_value=ref.created_at,
                entities=[str(ref.created_at)],
            )
        )

    # 4. Verified Extracted Document Fields
    for doc in extracted_docs:
        doc_source = f"doc:{doc.doc_id}"
        for field_name, field_obj in doc.surviving_fields.items():
            val = getattr(field_obj, "value", None)
            if val is None and isinstance(field_obj, dict):
                val = field_obj.get("value")
            if val is None:
                val = str(field_obj)

            fact_id = f"fact_doc_{doc.doc_id}_{field_name}"
            # Render human-friendly text
            if isinstance(val, (int, float)) and "amount" in field_name:
                display_val = _format_amount(int(val), disp.currency)
            elif "date" in field_name or "epoch" in field_name:
                display_val = _format_epoch(int(val)) if isinstance(val, int) else str(val)
            else:
                display_val = str(val)

            facts.append(
                Fact(
                    fact_id=fact_id,
                    text=f"Document {doc.doc_id} ({doc.doc_type}) verifies {field_name.replace('_', ' ')}: {display_val}.",
                    source=doc_source,
                    raw_value=val,
                    entities=[str(val)],
                )
            )

    return FactSet(case_id=case.case_id, facts=facts)
