"""Core Pydantic v2 data models for DisputePilot."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ReasonClass(str, Enum):
    """The 7 standard dispute reason classes."""

    ITEM_NOT_RECEIVED = "item_not_received"
    NOT_AS_DESCRIBED = "not_as_described"
    UNAUTHORISED = "unauthorised"
    DUPLICATE_CHARGE = "duplicate_charge"
    SUBSCRIPTION_CANCELLED = "subscription_cancelled"
    REFUND_NOT_RECEIVED = "refund_not_received"
    OTHER = "other"
    UNCLASSIFIED = "unclassified"


class DisputePhase(str, Enum):
    """Dispute phases supported by Razorpay."""

    CHARGEBACK = "chargeback"
    RETRIEVAL = "retrieval"
    PRE_ARBITRATION = "pre_arbitration"


class DisputeStatus(str, Enum):
    """Dispute status states."""

    OPEN = "open"
    UNDER_REVIEW = "under_review"
    WON = "won"
    LOST = "lost"
    CLOSED = "closed"


class RazorpayEvidence(BaseModel):
    """Razorpay dispute evidence object mapping categories to uploaded document identifiers."""

    model_config = ConfigDict(extra="allow")

    shipping_proof: list[str] = Field(default_factory=list)
    billing_proof: list[str] = Field(default_factory=list)
    cancellation_proof: list[str] = Field(default_factory=list)
    customer_communication: list[str] = Field(default_factory=list)
    proof_of_service: list[str] = Field(default_factory=list)
    explanation_letter: list[str] = Field(default_factory=list)
    refund_confirmation: list[str] = Field(default_factory=list)
    access_activity_log: list[str] = Field(default_factory=list)
    refund_cancellation_policy: list[str] = Field(default_factory=list)
    others: list[str] = Field(default_factory=list)


class RazorpayDispute(BaseModel):
    """Razorpay Disputes entity model."""

    id: str
    entity: str = "dispute"
    payment_id: str
    amount: int  # in paise
    currency: str = "INR"
    amount_deducted: int = 0  # in paise
    reason_code: str
    phase: DisputePhase
    status: DisputeStatus = DisputeStatus.OPEN
    respond_by: int  # unix timestamp in seconds
    created_at: int  # unix timestamp in seconds
    evidence: RazorpayEvidence = Field(default_factory=RazorpayEvidence)


class OrderItem(BaseModel):
    """Line item in an order."""

    name: str
    quantity: int
    amount: int  # in paise


class Order(BaseModel):
    """Merchant order record."""

    id: str
    entity: str = "order"
    amount: int  # in paise
    currency: str = "INR"
    status: str = "paid"
    created_at: int  # unix timestamp in seconds
    customer_name: str
    customer_email: str
    customer_phone: str
    shipping_address: str
    items: list[OrderItem] = Field(default_factory=list)
    tracking_number: str | None = None
    delivered_at: int | None = None  # unix timestamp in seconds


class Refund(BaseModel):
    """Razorpay refund record."""

    id: str
    entity: str = "refund"
    payment_id: str
    amount: int  # in paise
    currency: str = "INR"
    status: str = "processed"
    created_at: int  # unix timestamp in seconds
    arn: str | None = None  # Bank Acquirer Reference Number


class AdversarialInfo(BaseModel):
    """Adversarial metadata for simulated cases."""

    is_adversarial: bool = False
    adversarial_types: list[str] = Field(default_factory=list)
    details: list[str] = Field(default_factory=list)


class GroundTruth(BaseModel):
    """Ground truth classification and winnability rule outcome."""

    reason_class: ReasonClass
    available_evidence: list[str]
    winnable: bool
    rule_explanation: str
    adversarial: AdversarialInfo = Field(default_factory=AdversarialInfo)


class EvidenceDocument(BaseModel):
    """A simulated evidence document."""

    doc_id: str
    doc_type: str
    file_name: str
    file_path: str
    content: str


class DisputeCase(BaseModel):
    """Complete simulated dispute case."""

    case_id: str
    dispute: RazorpayDispute
    order: Order
    refund: Refund | None = None
    ground_truth: GroundTruth
    documents: list[EvidenceDocument] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
