"""Document ingestion pipeline integrating card redaction, PII tokenization, and safety checks."""

import logging
import secrets
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from disputepilot.safety.card_scanner import CardFinding, redact_text, scan_text
from disputepilot.safety.pii import DEFAULT_VAULT_TTL, Vault, tokenize_pii
from disputepilot.safety.untrusted import detect_injection

logger = logging.getLogger("disputepilot.safety.ingest")


class BinaryDocumentError(ValueError, TypeError):
    """Raised when binary, scan, or image data is provided instead of text."""


# Common file extensions for images, scans, and binary formats
BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".pdf",
    ".tiff",
    ".bmp",
    ".webp",
    ".gif",
    ".bin",
    ".exe",
    ".zip",
    ".tar",
    ".gz",
    ".doc",
    ".docx",
}

# In-memory vault registry indexed by vault_id
_VAULT_REGISTRY: dict[str, Vault] = {}


class IngestResult(BaseModel):
    """Result of document ingestion with sensitive data sanitized and flags extracted."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    clean_text: str
    findings: list[CardFinding]
    injection_flags: list[str]
    vault_id: str
    vault: Vault = Field(default_factory=Vault)


def get_vault(vault_id: str, now: float | None = None) -> Vault | None:
    """Retrieve PII rehydration vault by vault_id if not expired or purged.

    Args:
        vault_id: Unique vault identifier.
        now: Optional current timestamp in seconds (for deterministic testing).

    Returns:
        Vault if found and unexpired, None otherwise.
    """
    vault = _VAULT_REGISTRY.get(vault_id)
    if vault is None:
        return None

    if vault.is_expired(now):
        _VAULT_REGISTRY.pop(vault_id, None)
        vault.clear()
        return None

    return vault


def purge_vault(vault_id: str) -> bool:
    """Purge a vault immediately from registry and memory.

    Args:
        vault_id: Unique vault identifier.

    Returns:
        True if vault was found and purged, False if not found.
    """
    vault = _VAULT_REGISTRY.pop(vault_id, None)
    if vault is not None:
        vault.clear()
        return True
    return False


def ingest_document(
    text_or_path: str | Path | bytes | bytearray,
    case_id: str,
    known_names: list[str] | None = None,
    protected_ids: set[str] | list[str] | None = None,
    ttl: float = DEFAULT_VAULT_TTL,
) -> IngestResult:
    """Ingest, scan, redact, tokenize, and inspect an evidence document.

    Non-negotiable security guarantee:
    1. The original text containing payment card numbers or CVV values is NEVER written
       to disk or logs. Only the sanitized clean_text is propagated.
    2. Bytes and binary inputs (images, scans, PDFs) are strictly rejected with an explicit
       instruction that they must be converted to text by local OCR before ingestion.
    3. Any digit string matching a protected_id (order ID, AWB, payment ID) is protected.

    Args:
        text_or_path: Raw text string, Path to text file, or file path.
        case_id: Dispute case identifier.
        known_names: Optional known customer names from order records.
        protected_ids: Optional set or list of identifiers (order id, AWB, payment id) to leave intact.
        ttl: Vault TTL in seconds (default 24h = 86400s).

    Returns:
        IngestResult containing sanitized clean_text, card findings, injection flags, and vault_id.

    Raises:
        ValueError: If input is bytes, binary, image, scan, or unreadable non-text.
    """
    ocr_error_msg = "Images and scans must be converted to text by local OCR before ingestion."

    # 1. Reject bytes or binary input objects
    if isinstance(text_or_path, (bytes, bytearray)):
        raise BinaryDocumentError(ocr_error_msg)

    # 2. Resolve raw content from path or string
    if isinstance(text_or_path, Path):
        file_path = text_or_path
    elif (
        isinstance(text_or_path, str)
        and "\n" not in text_or_path
        and len(text_or_path) < 1024
    ):
        try:
            candidate_p = Path(text_or_path)
            file_path = candidate_p if candidate_p.exists() and candidate_p.is_file() else None
        except OSError:
            file_path = None
    else:
        file_path = None

    if file_path is not None:
        if file_path.suffix.lower() in BINARY_EXTENSIONS:
            raise BinaryDocumentError(ocr_error_msg)
        try:
            with open(file_path, "rb") as f:
                raw_bytes = f.read()
            if b"\x00" in raw_bytes:
                raise BinaryDocumentError(ocr_error_msg)
            raw_content = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise BinaryDocumentError(ocr_error_msg) from exc
    elif isinstance(text_or_path, str):
        if "\x00" in text_or_path:
            raise BinaryDocumentError(ocr_error_msg)
        raw_content = text_or_path
    else:
        raise BinaryDocumentError(ocr_error_msg)

    # 3. Card Scanner: scan and redact card numbers and CVVs (respecting protected_ids)
    findings = scan_text(raw_content, protected_ids=protected_ids)
    clean_no_cards = redact_text(raw_content, protected_ids=protected_ids)

    # 4. Non-negotiable logging discipline: Never log raw card numbers
    if findings:
        logger.warning(
            "Sanitized %d sensitive card/CVV matches for case '%s'. Raw text suppressed.",
            len(findings),
            case_id,
        )
    else:
        logger.info("Ingested document for case '%s'. No payment card strings detected.", case_id)

    # 5. PII Tokenization
    tokenized_text, vault = tokenize_pii(
        clean_no_cards,
        known_names=known_names,
        case_id=case_id,
    )

    # 6. Injection Detection
    injection_flags = detect_injection(tokenized_text)
    if injection_flags:
        logger.warning(
            "Detected prompt injection indicators for case '%s': %s",
            case_id,
            injection_flags,
        )

    # 7. Register vault for per-case rehydration with TTL
    vault_id = f"vault_{case_id}_{secrets.token_hex(4)}"
    vault.vault_id = vault_id
    vault.ttl = ttl
    _VAULT_REGISTRY[vault_id] = vault

    return IngestResult(
        clean_text=tokenized_text,
        findings=findings,
        injection_flags=injection_flags,
        vault_id=vault_id,
        vault=vault,
    )
