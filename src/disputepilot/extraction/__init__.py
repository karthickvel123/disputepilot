"""Extraction subpackage for evidence ingestion, schema extraction, and cross-checks."""

from disputepilot.extraction.cross_checks import (
    CrossCheckFlag,
    Severity,
    SeverityTier,
    check_address_mismatch,
    check_delivery_after_dispute,
    check_invoice_amount_mismatch,
    check_invoice_payment_mismatch,
    check_refund_not_mentioned,
    run_cross_checks,
)
from disputepilot.extraction.extractor import (
    DroppedField,
    ExtractedDocument,
    extract_document,
)
from disputepilot.extraction.llm import (
    FakeLLMClient,
    GeminiClient,
    LLMClient,
    get_llm_client,
)
from disputepilot.extraction.schemas import (
    CancellationPolicy,
    ChatTranscript,
    DeliveryProof,
    ExtractedField,
    Invoice,
    get_schema_for_doc_type,
)

__all__ = [
    "CancellationPolicy",
    "ChatTranscript",
    "CrossCheckFlag",
    "DeliveryProof",
    "DroppedField",
    "ExtractedDocument",
    "ExtractedField",
    "FakeLLMClient",
    "GeminiClient",
    "Invoice",
    "LLMClient",
    "Severity",
    "SeverityTier",
    "check_address_mismatch",
    "check_delivery_after_dispute",
    "check_invoice_amount_mismatch",
    "check_invoice_payment_mismatch",
    "check_refund_not_mentioned",
    "extract_document",
    "get_llm_client",
    "get_schema_for_doc_type",
    "run_cross_checks",
]
