import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from disputepilot.core.models import ReasonClass
from disputepilot.extraction.llm import GeminiDailyQuotaError

logger = logging.getLogger("disputepilot.core.reasons")
REASONS_YAML_DEFAULT = Path(__file__).parent / "reasons.yaml"


class ReasonMatch(BaseModel):
    """Result of mapping a reason code or description."""

    reason_class: ReasonClass
    rule_matched: str
    raw_reason: str | None
    confidence: float = 1.0
    quote: str | None = None
    needs_review: bool = False


@lru_cache(maxsize=1)
def load_reasons_config(config_path: str | None = None) -> dict[str, Any]:
    """Load and cache the reason mapping YAML configuration.

    Args:
        config_path: Path to custom reasons.yaml, or None for package default.

    Returns:
        Parsed configuration dictionary.
    """
    path = Path(config_path) if config_path else REASONS_YAML_DEFAULT
    with open(path, encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f)
    return data


# ---------------------------------------------------------------------------------------------
# Keyword matching safeguards (see evals/adversarial for the cases that motivated each one)
# ---------------------------------------------------------------------------------------------
_NEGATORS = frozenset(
    {"not", "no", "never", "without", "nothing", "none", "neither", "nor", "cannot",
     "isnt", "wasnt", "didnt", "doesnt", "dont", "wont", "hasnt", "havent", "hadnt", "arent", "werent"}
)
_CLAUSE_BREAK = re.compile(r"[.;:!?,]|\b(?:but|however|although|though|yet)\b")
_MULTI_ISSUE = re.compile(r"\b(?:and also|as well as|in addition|besides|moreover|plus|also)\b")
# Common romanised-Hindi function words. English keyword rules are unreliable on code-mixed text
# ("duplicate piece lag raha" means counterfeit), so such text is not rule-classified.
_HINGLISH = frozenset(
    {"nahi", "nahin", "hai", "hain", "tha", "thi", "kiya", "kar", "diya", "liya", "aaya", "aya", "gaya", "gayi",
     "mera", "meri", "mere", "wo", "woh", "ye", "yeh", "koi", "kuch", "bhi", "fir", "phir", "abhi", "tak",
     "paisa", "paise", "kat", "baar", "ek", "hi", "ne", "ko", "ka", "ki", "ke", "me", "mein", "se", "par",
     "nikla", "bheja", "dikhaya", "lag", "raha", "rahi", "ho", "hua", "hui", "aur", "lekin", "bank"}
)


def _normalise(text: str) -> str:
    t = text.strip().lower().replace("\u2019", "'").replace("\u2018", "'")
    return re.sub(r"\s+", " ", t)


def _starts_with_negator(keyword: str) -> bool:
    first = re.sub(r"[^a-z]", "", keyword.split(" ", 1)[0].lower())
    return first in _NEGATORS or keyword.lower().startswith(("didn't", "did not"))


def _is_negated(text: str, start: int) -> bool:
    """True if the keyword at ``start`` is negated by a nearby word in the same clause.

    Looks at up to 3 words before it, stopping at clause punctuation or a contrast word
    ("but", "yet"...). "not only X" is not negation of X.
    """
    clause = _CLAUSE_BREAK.split(text[max(0, start - 60) : start])[-1]
    words = [w.replace("'", "") for w in re.findall(r"[a-z']+", clause)][-3:]
    for i, w in enumerate(words):
        if w in _NEGATORS:
            if w == "not" and i + 1 < len(words) and words[i + 1] == "only":
                continue
            return True
    return False


def _is_code_mixed(text: str) -> bool:
    return sum(1 for w in re.findall(r"[a-z]+", text) if w in _HINGLISH) >= 3


def _keyword_candidates(cleaned: str, config: dict[str, Any]) -> list[tuple[str, str, int, int]]:
    """All whole-word, non-negated keyword hits as (class_value, keyword, start, end)."""
    hits: list[tuple[str, str, int, int]] = []
    for class_key, class_data in config.items():
        if class_key in ReasonClass.__members__.values():
            target = ReasonClass(class_key)
        else:
            try:
                target = ReasonClass[class_key.upper()]
            except KeyError:
                continue
        for kw in class_data.get("keywords", []):
            kw_clean = _normalise(str(kw))
            if not kw_clean:
                continue
            # Whole word, allowing simple inflections ("mismatch" -> "mismatched"), never a longer
            # word that merely contains it ("other" in "another", "broken" in "unbroken").
            pattern = r"(?<![a-z0-9])" + re.escape(kw_clean) + r"(?:s|es|ed|d|ing)?(?![a-z0-9])"
            for m in re.finditer(pattern, cleaned):
                if not _starts_with_negator(kw_clean) and _is_negated(cleaned, m.start()):
                    continue
                hits.append((target.value, kw_clean, m.start(), m.end()))
    # Longest phrase wins: drop a hit that sits inside a longer hit ("not received" in "refund not received").
    kept = [
        h for h in hits
        if not any(o is not h and o[2] <= h[2] and h[3] <= o[3] and (o[3] - o[2]) > (h[3] - h[2]) for o in hits)
    ]
    # A specific class beats the generic catch-all.
    specific = [h for h in kept if h[0] != ReasonClass.OTHER.value]
    return specific or kept


def classify_reason(
    reason_code_or_text: str | None,
    config_path: Path | str | None = None,
    llm_client: Any | None = None,
    case_id: str | None = None,
) -> ReasonMatch:
    """Map Razorpay reason code or text description to one of the 7 ReasonClass categories or UNCLASSIFIED.

    Checks rules in reasons.yaml as the first pass. If no rule matches with high confidence,
    calls LLMClient.generate_json with an enum of the 7 reason classes plus 'unclassified'.
    If the LLM is unavailable or confidence is below 0.6, returns 'unclassified' with needs_review=True.
    Never silently defaults to 'other'.

    Args:
        reason_code_or_text: Raw reason string from Razorpay dispute entity.
        config_path: Optional custom path to reasons.yaml.
        llm_client: Optional LLMClient instance for second-pass semantic classification.
        case_id: Optional case identifier for telemetry and checkpointing.

    Returns:
        ReasonMatch with assigned ReasonClass, rule matched, confidence, quote, and needs_review.
    """
    if reason_code_or_text is None or not str(reason_code_or_text).strip():
        return ReasonMatch(
            reason_class=ReasonClass.UNCLASSIFIED,
            rule_matched="empty_reason",
            raw_reason=reason_code_or_text,
            confidence=0.0,
            quote=None,
            needs_review=True,
        )

    cleaned = str(reason_code_or_text).strip().lower()
    config = load_reasons_config(str(config_path) if config_path else None)

    # 1. Exact code match (High Confidence)
    for class_key, class_data in config.items():
        if class_key in ReasonClass.__members__.values():
            target_class = ReasonClass(class_key)
        else:
            try:
                target_class = ReasonClass[class_key.upper()]
            except KeyError:
                continue

        codes = class_data.get("codes", [])
        for code in codes:
            if cleaned == str(code).strip().lower():
                return ReasonMatch(
                    reason_class=target_class,
                    rule_matched=f"exact_code:{code}",
                    raw_reason=reason_code_or_text,
                    confidence=1.0,
                    quote=str(code),
                    needs_review=False,
                )

    # 2. Keyword match: whole words, negation-aware, longest phrase wins, conflicts go to a human
    code_mixed = _is_code_mixed(cleaned)
    candidates = [] if code_mixed else _keyword_candidates(cleaned, config)
    classes = sorted({h[0] for h in candidates})
    if len(classes) > 1:
        return ReasonMatch(
            reason_class=ReasonClass.UNCLASSIFIED,
            rule_matched="conflict:" + "|".join(classes),
            raw_reason=reason_code_or_text,
            confidence=0.0,
            quote=", ".join(sorted({h[1] for h in candidates})),
            needs_review=True,
        )
    if len(classes) == 1:
        first = min(candidates, key=lambda h: h[2])
        if _MULTI_ISSUE.search(cleaned):
            return ReasonMatch(
                reason_class=ReasonClass.UNCLASSIFIED,
                rule_matched=f"multi_issue:{classes[0]}",
                raw_reason=reason_code_or_text,
                confidence=0.0,
                quote=first[1],
                needs_review=True,
            )
        return ReasonMatch(
            reason_class=ReasonClass(classes[0]),
            rule_matched=f"keyword:{first[1]}",
            raw_reason=reason_code_or_text,
            confidence=1.0,
            quote=first[1],
            needs_review=False,
        )
    if code_mixed and llm_client is None:
        return ReasonMatch(
            reason_class=ReasonClass.UNCLASSIFIED,
            rule_matched="rules_skipped:code_mixed_text",
            raw_reason=reason_code_or_text,
            confidence=0.0,
            quote=None,
            needs_review=True,
        )

    # 3. Second pass: LLM classification if available
    if llm_client is not None:
        try:
            system_instruction = (
                "You are an expert payment dispute reason classifier. "
                "Classify the dispute reason description into exactly ONE of the 7 standard classes, "
                "or 'unclassified' if ambiguous, unsupported, or uncertain.\n"
                "Allowed reason classes:\n"
                "- item_not_received\n"
                "- not_as_described\n"
                "- unauthorised\n"
                "- duplicate_charge\n"
                "- subscription_cancelled\n"
                "- refund_not_received\n"
                "- other\n"
                "- unclassified"
            )
            user_prompt = (
                f"Dispute reason text to classify:\n<<<DISPUTE_REASON>>>\n{reason_code_or_text}\n<<<END_DISPUTE_REASON>>>\n\n"
                "Return JSON adhering strictly to schema with reason_class, confidence (0.0 to 1.0), and a short quote."
            )
            schema = {
                "type": "object",
                "properties": {
                    "reason_class": {
                        "type": "string",
                        "enum": [
                            "item_not_received",
                            "not_as_described",
                            "unauthorised",
                            "duplicate_charge",
                            "subscription_cancelled",
                            "refund_not_received",
                            "other",
                            "unclassified",
                        ],
                    },
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "quote": {"type": "string"},
                },
                "required": ["reason_class", "confidence", "quote"],
            }
            res = llm_client.generate_json(
                system=system_instruction,
                user=user_prompt,
                json_schema=schema,
                case_id=case_id,
                stage="classification",
            )
            raw_class = str(res.get("reason_class", "unclassified")).strip().lower()
            try:
                confidence = float(res.get("confidence", 0.0))
            except (ValueError, TypeError):
                confidence = 0.0
            quote = res.get("quote")

            if confidence >= 0.6 and raw_class != "unclassified":
                try:
                    target_class = ReasonClass(raw_class)
                    return ReasonMatch(
                        reason_class=target_class,
                        rule_matched=f"llm:{raw_class}",
                        raw_reason=reason_code_or_text,
                        confidence=confidence,
                        quote=quote,
                        needs_review=False,
                    )
                except ValueError:
                    pass

            return ReasonMatch(
                reason_class=ReasonClass.UNCLASSIFIED,
                rule_matched="llm:unclassified_or_low_confidence",
                raw_reason=reason_code_or_text,
                confidence=confidence,
                quote=quote,
                needs_review=True,
            )
        except GeminiDailyQuotaError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM reason classification failed or unavailable: %s", exc)
            return ReasonMatch(
                reason_class=ReasonClass.UNCLASSIFIED,
                rule_matched="unclassified:llm_unavailable",
                raw_reason=reason_code_or_text,
                confidence=0.0,
                quote=None,
                needs_review=True,
            )

    # 4. Fallback when LLM is unavailable: return unclassified with needs_review=True
    return ReasonMatch(
        reason_class=ReasonClass.UNCLASSIFIED,
        rule_matched="unclassified:no_rule_match_no_llm",
        raw_reason=reason_code_or_text,
        confidence=0.0,
        quote=None,
        needs_review=True,
    )

