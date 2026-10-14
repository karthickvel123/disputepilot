"""Card scanner and redaction module with Luhn validation."""

import re
from typing import NamedTuple

from pydantic import BaseModel


class CardFinding(BaseModel):
    """Details of a detected payment card or CVV/CVC finding."""

    type: str  # "card_number" or "cvv"
    span: tuple[int, int]
    masked: str


class _RawSpan(NamedTuple):
    type: str
    start: int
    end: int
    masked: str


def is_luhn_valid(number: str) -> bool:
    """Validate digit string using the Luhn mod-10 algorithm.

    Args:
        number: String containing only digits, or with spaces/dashes.

    Returns:
        True if valid card checksum (13-19 digits), False otherwise.
    """
    digits = [int(c) for c in number if c.isdigit()]
    if not (13 <= len(digits) <= 19):
        return False

    checksum = 0
    # From rightmost digit (check digit) moving left, double every second digit
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            doubled = d * 2
            checksum += doubled - 9 if doubled > 9 else doubled
        else:
            checksum += d

    return checksum % 10 == 0


# Candidate card regex: 13 to 19 digits allowing optional spaces, hyphens, or dots between digits
CARD_CANDIDATE_REGEX = re.compile(r"(?<!\d)(?:\d[ \-\.]*?){13,19}(?!\d)")

# CVV/CVC keywords regex: looks for cvv, cvc, cid, or security code followed by 3-4 digits
CVV_REGEX = re.compile(
    r"(?i)\b(?:cvv2?|cvc2?|cid|security\s*code)\s*[:=\-]?\s*(\d{3,4})\b"
)


def _normalize_protected_ids(protected_ids: set[str] | list[str] | None) -> set[str]:
    """Extract exact strings and digit-only representations from protected IDs."""
    normalized: set[str] = set()
    if not protected_ids:
        return normalized

    for pid in protected_ids:
        if not pid:
            continue
        pid_str = str(pid).strip()
        normalized.add(pid_str)
        digits_only = "".join(c for c in pid_str if c.isdigit())
        if digits_only:
            normalized.add(digits_only)

    return normalized


def scan_text(
    text: str,
    protected_ids: set[str] | list[str] | None = None,
) -> list[CardFinding]:
    """Scan text for Luhn-valid card numbers and CVV/CVC values.

    Luhn-invalid strings (such as 16-digit order numbers or courier AWB codes)
    are strictly ignored and not returned as findings.
    Any digit string matching a protected ID (order id, AWB, payment id) is
    omitted from findings and will not be redacted.

    Args:
        text: Input string to scan.
        protected_ids: Optional set or list of identifiers to protect from scanning/redaction.

    Returns:
        List of CardFinding objects containing type, span, and masked preview.
    """
    raw_findings: list[_RawSpan] = []
    protected = _normalize_protected_ids(protected_ids)

    # 1. Scan for card numbers
    for match in CARD_CANDIDATE_REGEX.finditer(text):
        start, end = match.span()

        # Trim non-digit boundaries if matched
        while start < end and not text[start].isdigit():
            start += 1
        while end > start and not text[end - 1].isdigit():
            end -= 1

        candidate = text[start:end]
        raw_digits = "".join(c for c in candidate if c.isdigit())

        # Allowlist check: if candidate or digits match a protected ID, leave it alone
        if candidate.strip() in protected or raw_digits in protected:
            continue

        if 13 <= len(raw_digits) <= 19 and is_luhn_valid(raw_digits):
            # Mask preview showing last 4 digits only
            last_4 = raw_digits[-4:]
            masked_preview = f"****-****-****-{last_4}"
            raw_findings.append(
                _RawSpan(
                    type="card_number",
                    start=start,
                    end=end,
                    masked=masked_preview,
                )
            )

    # 2. Scan for CVV/CVC values
    for match in CVV_REGEX.finditer(text):
        start, end = match.span(1)
        cvv_digits = match.group(1)

        if cvv_digits in protected:
            continue

        raw_findings.append(
            _RawSpan(
                type="cvv",
                start=start,
                end=end,
                masked="*" * len(cvv_digits),
            )
        )

    # Sort findings by start position
    raw_findings.sort(key=lambda f: f.start)

    # Deduplicate / merge any overlapping spans
    filtered: list[CardFinding] = []
    last_end = -1
    for rf in raw_findings:
        if rf.start >= last_end:
            filtered.append(
                CardFinding(
                    type=rf.type,
                    span=(rf.start, rf.end),
                    masked=rf.masked,
                )
            )
            last_end = rf.end

    return filtered


def redact_text(
    text: str,
    protected_ids: set[str] | list[str] | None = None,
) -> str:
    """Redact Luhn-valid card numbers and CVV/CVC values from text.

    Card numbers are replaced with [REDACTED_CARD].
    CVV/CVC numbers are replaced with [REDACTED_CVV].
    Luhn-invalid digit strings and protected IDs (AWB, order IDs) are left alone.

    Args:
        text: Input text.
        protected_ids: Optional set or list of identifiers to protect from redaction.

    Returns:
        Cleaned text with sensitive card information redacted.
    """
    findings = scan_text(text, protected_ids=protected_ids)
    if not findings:
        return text

    # Process from back to front to preserve character indices
    sorted_findings = sorted(findings, key=lambda f: f.span[0], reverse=True)
    redacted = text
    for f in sorted_findings:
        start, end = f.span
        replacement = "[REDACTED_CARD]" if f.type == "card_number" else "[REDACTED_CVV]"
        redacted = redacted[:start] + replacement + redacted[end:]

    return redacted
