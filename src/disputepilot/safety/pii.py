"""PII detection, tokenization, and rehydration module."""

import re
import time
from typing import NamedTuple

# Default Vault Time-To-Live: 24 hours (in seconds)
DEFAULT_VAULT_TTL = 86400.0


class Vault(dict[str, str]):
    """Secure PII Vault that stores token-to-original mappings.

    Security guarantees:
    1. PAN and Aadhaar are NEVER stored as original values; only redaction placeholders are kept.
    2. __repr__ and __str__ are redacted so no log line, print, or traceback leaks token mappings.
    3. Supports TTL-based expiration and explicit memory purge.
    """

    def __init__(
        self,
        mapping: dict[str, str] | None = None,
        *,
        vault_id: str = "",
        created_at: float | None = None,
        ttl: float = DEFAULT_VAULT_TTL,
    ) -> None:
        super().__init__(mapping or {})
        self.vault_id = vault_id
        self.created_at = created_at if created_at is not None else time.time()
        self.ttl = ttl

    @property
    def expires_at(self) -> float:
        """Timestamp when this vault expires."""
        return self.created_at + self.ttl

    def is_expired(self, now: float | None = None) -> bool:
        """Check if this vault has exceeded its TTL."""
        current = now if now is not None else time.time()
        return current >= self.expires_at

    def __repr__(self) -> str:
        return f"<Vault id={self.vault_id!r} tokens={len(self)} [SECURE]>"

    def __str__(self) -> str:
        return f"<Vault id={self.vault_id!r} tokens={len(self)} [SECURE]>"


# Regex patterns for Indian financial & demographic PII

# Permanent Account Number (PAN): 5 letters, 4 digits, 1 letter
PAN_REGEX = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")

# Aadhaar: 12 digits, often grouped in 4-4-4 with space or dash
AADHAAR_REGEX = re.compile(r"\b(?:\d{4}[ -]?\d{4}[ -]?\d{4}|\d{12})\b")

# Email addresses
EMAIL_REGEX = re.compile(r"\b[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+\b")

# UPI Virtual Payment Address (VPA): e.g. user@okhdfcbank, name@upi, 9898429450@paytm
UPI_REGEX = re.compile(r"\b[a-zA-Z0-9_.+-]+@[a-zA-Z0-9_-]{2,32}\b(?!\.[a-zA-Z])")

# Indian mobile numbers: +91 or 0 prefix, 10 digits starting with 6, 7, 8, or 9
PHONE_REGEX = re.compile(r"(?<!\d)(?:\+91[\s\-]?)?[6-9]\d{4}[\s\-]?\d{5}(?!\d)")


class _PIIMatch(NamedTuple):
    type: str
    val: str
    start: int
    end: int


def tokenize_pii(
    text: str,
    known_names: list[str] | None = None,
    case_id: str | None = None,
) -> tuple[str, Vault]:
    """Tokenize sensitive PII and known names in text, returning clean text and a vault.

    Supported entities:
    - Email addresses -> [EMAIL_1], [EMAIL_2], ...
    - Indian phone numbers -> [PHONE_1], [PHONE_2], ...
    - UPI IDs -> [UPI_1], [UPI_2], ...
    - PAN numbers -> [PAN_1], [PAN_2], ... (never rehydrated, never stored)
    - 12-digit Aadhaar numbers -> [AADHAAR_1], [AADHAAR_2], ... (never rehydrated, never stored)
    - Known customer names and 3+ letter name parts -> [NAME_1], [NAME_2], ...

    Args:
        text: Input text containing potential PII.
        known_names: Optional list of names (e.g. from customer order) to tokenize.
        case_id: Optional case identifier for auditing.

    Returns:
        Tuple of (tokenized_text, vault) where vault maps token strings to original values.
    """
    raw_matches: list[_PIIMatch] = []

    # 1. Emails
    for m in EMAIL_REGEX.finditer(text):
        raw_matches.append(_PIIMatch("EMAIL", m.group(0), m.start(), m.end()))

    # 2. UPI IDs
    for m in UPI_REGEX.finditer(text):
        raw_matches.append(_PIIMatch("UPI", m.group(0), m.start(), m.end()))

    # 3. PAN
    for m in PAN_REGEX.finditer(text):
        raw_matches.append(_PIIMatch("PAN", m.group(0), m.start(), m.end()))

    # 4. Aadhaar (validate exact 12 digits)
    for m in AADHAAR_REGEX.finditer(text):
        digits = "".join(c for c in m.group(0) if c.isdigit())
        if len(digits) == 12:
            raw_matches.append(_PIIMatch("AADHAAR", m.group(0), m.start(), m.end()))

    # 5. Phone numbers
    for m in PHONE_REGEX.finditer(text):
        digits = "".join(c for c in m.group(0) if c.isdigit())
        # Ensure it's not a substring of a 12-digit Aadhaar number
        if len(digits) in (10, 11, 12):  # 10 digits, or 11 with leading 0, or 12 with 91
            raw_matches.append(_PIIMatch("PHONE", m.group(0), m.start(), m.end()))

    # 6. Known Names and Name Parts (3+ letters, case-insensitive, whole-word)
    if known_names:
        name_candidates: set[str] = set()
        for name in known_names:
            cleaned_name = name.strip()
            if len(cleaned_name) >= 2:
                name_candidates.add(cleaned_name)
            # Tokenize each name part of 3+ letters
            for part in re.split(r"\s+", cleaned_name):
                clean_part = part.strip(".,;:?!-()\"'")
                if len(clean_part) >= 3:
                    name_candidates.add(clean_part)

        for candidate in sorted(name_candidates, key=len, reverse=True):
            pattern = re.compile(rf"\b{re.escape(candidate)}\b", re.IGNORECASE)
            for m in pattern.finditer(text):
                raw_matches.append(_PIIMatch("NAME", m.group(0), m.start(), m.end()))

    # Sort matches by start position. Higher priority types break ties.
    priority = {"EMAIL": 1, "UPI": 2, "PAN": 3, "AADHAAR": 4, "PHONE": 5, "NAME": 6}
    raw_matches.sort(key=lambda m: (m.start, priority.get(m.type, 99), -(m.end - m.start)))

    # Resolve overlapping spans (first/higher priority wins, longer span breaks start ties)
    non_overlapping: list[_PIIMatch] = []
    last_end = -1
    for m in raw_matches:
        if m.start >= last_end:
            non_overlapping.append(m)
            last_end = m.end

    # Assign tokens consistently per entity value
    counters: dict[str, int] = {
        "EMAIL": 1,
        "PHONE": 1,
        "UPI": 1,
        "PAN": 1,
        "AADHAAR": 1,
        "NAME": 1,
    }
    val_to_token: dict[str, str] = {}
    vault_mapping: dict[str, str] = {}

    for m in non_overlapping:
        lookup_key = (m.type, m.val.lower() if m.type in ("EMAIL", "UPI", "NAME") else m.val)
        if lookup_key not in val_to_token:
            token = f"[{m.type}_{counters[m.type]}]"
            counters[m.type] += 1
            val_to_token[lookup_key] = token

            # Non-negotiable security guarantee:
            # PAN and Aadhaar are NEVER stored as original values in the vault.
            # Store only a redaction placeholder so no code path can ever restore them.
            if m.type in ("PAN", "AADHAAR"):
                vault_mapping[token] = "[PERMANENTLY_REDACTED]"
            else:
                vault_mapping[token] = m.val

    # Replace from back to front to preserve offsets
    tokenized = text
    for m in sorted(non_overlapping, key=lambda x: x.start, reverse=True):
        lookup_key = (m.type, m.val.lower() if m.type in ("EMAIL", "UPI", "NAME") else m.val)
        token = val_to_token[lookup_key]
        tokenized = tokenized[: m.start] + token + tokenized[m.end :]

    vault = Vault(vault_mapping, vault_id=case_id or "")
    return tokenized, vault


def rehydrate(text: str, vault: dict[str, str] | Vault) -> str:
    """Rehydrate tokenized text using the per-case vault.

    Non-negotiable security guarantee: PAN ([PAN_...]) and Aadhaar ([AADHAAR_...])
    tokens are NEVER rehydrated and remain permanently redacted.

    Args:
        text: Tokenized text.
        vault: Mapping of tokens to original values.

    Returns:
        Rehydrated text with safe PII restored and financial identifiers kept masked.
    """
    rehydrated = text
    for token, original in vault.items():
        # PAN and Aadhaar are strictly never rehydrated
        if token.startswith(("[PAN_", "[AADHAAR_")):
            continue
        rehydrated = rehydrated.replace(token, original)

    return rehydrated
