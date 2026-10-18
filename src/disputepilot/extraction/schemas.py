"""Strict extraction schemas for evidence document types."""

from pydantic import BaseModel, ConfigDict, Field


class ExtractedField[T](BaseModel):
    """Atomic extracted field containing value, verbatim source quote, and confidence score."""

    model_config = ConfigDict(extra="forbid")

    value: T
    source_quote: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class DeliveryProof(BaseModel):
    """Extraction schema for Courier Proof of Delivery (POD)."""

    model_config = ConfigDict(extra="forbid")

    tracking_number: ExtractedField[str] | None = None
    carrier: ExtractedField[str] | None = None
    recipient_name: ExtractedField[str] | None = None
    delivery_address: ExtractedField[str] | None = None
    delivery_status: ExtractedField[str] | None = None
    delivery_date: ExtractedField[str] | None = None
    delivery_epoch: ExtractedField[int] | None = None
    order_id: ExtractedField[str] | None = None
    signed_by: ExtractedField[str] | None = None
    otp_verified: ExtractedField[bool] | None = None


class Invoice(BaseModel):
    """Extraction schema for Merchant Tax Invoice / Billing Proof."""

    model_config = ConfigDict(extra="forbid")

    invoice_number: ExtractedField[str] | None = None
    order_id: ExtractedField[str] | None = None
    payment_id: ExtractedField[str] | None = None
    customer_name: ExtractedField[str] | None = None
    customer_email: ExtractedField[str] | None = None
    customer_phone: ExtractedField[str] | None = None
    shipping_address: ExtractedField[str] | None = None
    billing_address: ExtractedField[str] | None = None
    total_amount_paise: ExtractedField[int] | None = None
    invoice_date: ExtractedField[str] | None = None


class ChatTranscript(BaseModel):
    """Extraction schema for Customer Support Chat Transcripts."""

    model_config = ConfigDict(extra="forbid")

    ticket_id: ExtractedField[str] | None = None
    customer_name: ExtractedField[str] | None = None
    issue_reported: ExtractedField[str] | None = None
    merchant_response: ExtractedField[str] | None = None
    refund_mentioned: ExtractedField[bool] | None = None
    refund_offered: ExtractedField[bool] | None = None
    customer_admitted_receipt: ExtractedField[bool] | None = None


class CancellationPolicy(BaseModel):
    """Extraction schema for Merchant Refund / Cancellation Policy."""

    model_config = ConfigDict(extra="forbid")

    cancellation_window_days: ExtractedField[int] | None = None
    refund_allowed: ExtractedField[bool] | None = None
    return_policy_terms: ExtractedField[str] | None = None
    restocking_fee_paise: ExtractedField[int] | None = None


# Schema registry mapping document types to Pydantic classes
DOC_TYPE_SCHEMAS: dict[str, type[BaseModel]] = {
    "delivery_proof": DeliveryProof,
    "courier_pod": DeliveryProof,
    "shipping_proof": DeliveryProof,
    "invoice": Invoice,
    "billing_proof": Invoice,
    "chat_transcript": ChatTranscript,
    "customer_communication": ChatTranscript,
    "cancellation_policy": CancellationPolicy,
    "refund_cancellation_policy": CancellationPolicy,
}


def get_schema_for_doc_type(doc_type: str) -> type[BaseModel]:
    """Retrieve corresponding strict schema class for a document type."""
    normalized = doc_type.strip().lower()
    schema_cls = DOC_TYPE_SCHEMAS.get(normalized)
    if not schema_cls:
        # Default to DeliveryProof or Invoice based on name
        if "delivery" in normalized or "pod" in normalized or "ship" in normalized:
            return DeliveryProof
        if "invoice" in normalized or "bill" in normalized:
            return Invoice
        if "chat" in normalized or "comm" in normalized or "transcript" in normalized:
            return ChatTranscript
        if "policy" in normalized or "refund" in normalized or "cancel" in normalized:
            return CancellationPolicy
        return DeliveryProof

    return schema_cls
