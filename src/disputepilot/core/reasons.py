import logging
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

    # 2. Keyword substring match (High Confidence)
    for class_key, class_data in config.items():
        if class_key in ReasonClass.__members__.values():
            target_class = ReasonClass(class_key)
        else:
            try:
                target_class = ReasonClass[class_key.upper()]
            except KeyError:
                continue

        keywords = class_data.get("keywords", [])
        for kw in keywords:
            kw_clean = str(kw).strip().lower()
            if kw_clean and kw_clean in cleaned:
                return ReasonMatch(
                    reason_class=target_class,
                    rule_matched=f"keyword:{kw}",
                    raw_reason=reason_code_or_text,
                    confidence=1.0,
                    quote=str(kw),
                    needs_review=False,
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
            try:
                res = llm_client.generate_json(
                    system=system_instruction,
                    user=user_prompt,
                    json_schema=schema,
                    case_id=case_id,
                    stage="classification",
                )
            except TypeError:
                res = llm_client.generate_json(
                    system=system_instruction,
                    user=user_prompt,
                    json_schema=schema,
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

