"""Safety subpackage providing card redaction, PII tokenization, untrusted wrapping, and safe ingestion."""

from disputepilot.safety.card_scanner import (
    CardFinding,
    extract_text_from_pdf_bytes,
    is_luhn_valid,
    redact_text,
    scan_pdf_bytes,
    scan_text,
)
from disputepilot.safety.ingest import (
    BinaryDocumentError,
    IngestResult,
    get_vault,
    ingest_document,
    purge_vault,
)
from disputepilot.safety.pii import (
    DEFAULT_VAULT_TTL,
    Vault,
    rehydrate,
    tokenize_pii,
)
from disputepilot.safety.untrusted import (
    detect_injection,
    wrap_untrusted,
)

__all__ = [
    "DEFAULT_VAULT_TTL",
    "BinaryDocumentError",
    "CardFinding",
    "IngestResult",
    "Vault",
    "detect_injection",
    "extract_text_from_pdf_bytes",
    "get_vault",
    "ingest_document",
    "is_luhn_valid",
    "purge_vault",
    "redact_text",
    "rehydrate",
    "scan_pdf_bytes",
    "scan_text",
    "tokenize_pii",
    "wrap_untrusted",
]
