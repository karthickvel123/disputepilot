"""Core Pydantic v2 data models for DisputePilot."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


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

    FRAUD = "fraud"
    RETRIEVAL = "retrieval"
    CHARGEBACK = "chargeback"
    PRE_ARBITRATION = "pre_arbitration"
    ARBITRATION = "arbitration"
    UNKNOWN = "unknown"  # a phase Razorpay added that this build does not know yet

    @classmethod
    def _missing_(cls, value: object) -> "DisputePhase":
        return cls.UNKNOWN


class DisputeStatus(str, Enum):
    """Dispute status states."""

    OPEN = "open"
    UNDER_REVIEW = "under_review"
    WON = "won"
    LOST = "lost"
    CLOSED = "closed"
    UNKNOWN = "unknown"  # a status Razorpay added that this build does not know yet

    @classmethod
    def _missing_(cls, value: object) -> "DisputeStatus":
        return cls.UNKNOWN


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
    term_and_conditions: list[str] = Field(default_factory=list)
    # Razorpay returns `others` as [{"type": str, "document_ids": [str]}]; the fixtures use [str].
    others: list[Any] = Field(default_factory=list)

    @field_validator(
        "shipping_proof",
        "billing_proof",
        "cancellation_proof",
        "customer_communication",
        "proof_of_service",
        "explanation_letter",
        "refund_confirmation",
        "access_activity_log",
        "refund_cancellation_policy",
        "term_and_conditions",
        "others",
        mode="before",
    )
    @classmethod
    def _null_to_empty_list(cls, v: Any) -> Any:
        """Razorpay returns unset evidence categories as JSON null, not []."""
        return [] if v is None else v

    def document_ids(self) -> dict[str, list[str]]:
        """Flat category -> document ids view (expands the structured `others` entries)."""
        out: dict[str, list[str]] = {}
        for name, value in self.model_dump().items():
            if name == "others":
                continue
            if isinstance(value, list) and value and all(isinstance(x, str) for x in value):
                out[name] = list(value)
        return out


class RazorpayDispute(BaseModel):
    """Razorpay Disputes entity model."""

    id: str
    entity: str = "dispute"
    payment_id: str
    amount: int  # in paise
    currency: str = "INR"
    amount_deducted: int = 0  # in paise
    reason_code: str
    reason_description: str | None = None
    phase: DisputePhase
    status: DisputeStatus = DisputeStatus.OPEN
    respond_by: int  # unix timestamp in seconds
    created_at: int  # unix timestamp in seconds
    evidence: RazorpayEvidence = Field(default_factory=RazorpayEvidence)

    @field_validator("evidence", mode="before")
    @classmethod
    def _null_evidence(cls, v: Any) -> Any:
        return {} if v is None else v

    @field_validator("phase", mode="before")
    @classmethod
    def _coerce_phase(cls, v: Any) -> Any:
        # Resolve through the Enum ourselves so unknown values become UNKNOWN regardless of how
        # the installed pydantic version treats Enum._missing_.
        return DisputePhase(v) if isinstance(v, str) else v

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: Any) -> Any:
        return DisputeStatus(v) if isinstance(v, str) else v

    @field_validator("amount_deducted", mode="before")
    @classmethod
    def _null_deducted(cls, v: Any) -> Any:
        return 0 if v is None else v


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
    customer_name: str = ""
    customer_email: str = ""
    customer_phone: str = ""
    shipping_address: str = ""
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
    # Present only on synthetic fixtures. Live cases have no ground truth.
    ground_truth: GroundTruth | None = None
    documents: list[EvidenceDocument] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
