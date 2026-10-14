"""Deterministic rebuttal draft verifier enforcing strict citation and entity grounding."""

import re

from pydantic import BaseModel, Field

from disputepilot.drafting.drafter import DraftSentence, RebuttalDraft
from disputepilot.drafting.facts import FactSet


class StrippedSentence(BaseModel):
    """Details of a sentence stripped due to missing citation or fabricated claims."""

    section: str
    sentence: str
    cited_fact_ids: list[str]
    reasons: list[str]
    ungrounded_entities: list[str] = Field(default_factory=list)


class VerifierReport(BaseModel):
    """Comprehensive deterministic audit report of draft rebuttal verification."""

    case_id: str
    total_sentences: int
    valid_sentences: int
    stripped_count: int
    is_clean: bool
    stripped_sentences: list[StrippedSentence] = Field(default_factory=list)


# Regex patterns for numbers, dates, and domain IDs
DATE_ISO_PATTERN = re.compile(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b")
DATE_TEXT_PATTERN = re.compile(
    r"\b(?:\d{1,2}(?:st|nd|rd|th)?\s+)?(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)(?:\s+\d{1,2}(?:st|nd|rd|th)?)?(?:,?\s+\d{4})?\b",
    re.IGNORECASE,
)
ID_PATTERN = re.compile(r"\b(?=[a-zA-Z0-9_-]{4,}\b)(?:[a-zA-Z]+[0-9]+[a-zA-Z0-9_-]*|[0-9]+[a-zA-Z]+[a-zA-Z0-9_-]*|[a-zA-Z0-9]+[-_][a-zA-Z0-9_-]+)\b")
NUMBER_PATTERN = re.compile(r"\b\d+(?:,\d{3})*(?:\.\d+)?\b")


def extract_entities_from_sentence(sentence: str) -> dict[str, list[str]]:
    """Extract all numbers, dates, and IDs present in a sentence.

    Args:
        sentence: Raw sentence text.

    Returns:
        Dictionary mapping entity types ('dates', 'ids', 'numbers') to found tokens.
    """
    dates: list[str] = []
    ids: list[str] = []
    numbers: list[str] = []

    # 1. Dates
    for m in DATE_ISO_PATTERN.finditer(sentence):
        dates.append(m.group(0))
    for m in DATE_TEXT_PATTERN.finditer(sentence):
        # Avoid single month word if it's not a complete date
        val = m.group(0).strip()
        if any(char.isdigit() for char in val):
            dates.append(val)

    # 2. Identifiers (e.g., disp_0001, ord_987, AWB12345)
    for m in ID_PATTERN.finditer(sentence):
        token = m.group(0).strip(".,;:?!")
        ids.append(token)

    # 3. Numbers (integers, amounts, timestamps)
    for m in NUMBER_PATTERN.finditer(sentence):
        num_str = m.group(0).replace(",", "")
        # Filter out numbers that were already captured as parts of dates or IDs
        if not any(num_str in d for d in dates) and not any(num_str in i for i in ids):
            numbers.append(num_str)

    return {"dates": dates, "ids": ids, "numbers": numbers}


def _normalize_text_for_lookup(text: str) -> str:
    """Normalize text by lowercasing and standardizing whitespace and punctuation."""
    return re.sub(r"[\s,\.\-_:/]+", " ", text).lower().strip()


def verify_sentence(
    sentence: DraftSentence,
    section_name: str,
    fact_set: FactSet,
) -> tuple[bool, StrippedSentence | None]:
    """Deterministically verify an individual draft sentence against the provided FactSet.

    Rules:
    1. Sentence must cite at least one fact ID.
    2. Every cited fact ID must exist in the FactSet.
    3. Every number, date, and ID in the sentence must appear in at least one cited fact.

    Args:
        sentence: DraftSentence with text and cited fact IDs.
        section_name: Name of the draft section.
        fact_set: Authoritative FactSet.

    Returns:
        Tuple of (is_valid, StrippedSentence if invalid else None).
    """
    reasons: list[str] = []
    ungrounded: list[str] = []

    # Rule 1: Must cite at least one fact
    if not sentence.cited_fact_ids:
        reasons.append("Missing citation: sentence cites zero fact IDs.")
        return False, StrippedSentence(
            section=section_name,
            sentence=sentence.sentence,
            cited_fact_ids=[],
            reasons=reasons,
            ungrounded_entities=[],
        )

    # Rule 2: All cited facts must exist in FactSet
    cited_facts = []
    for fid in sentence.cited_fact_ids:
        f = fact_set.get_fact(fid)
        if not f:
            reasons.append(f"Invalid citation: fact ID '{fid}' does not exist in FactSet.")
        else:
            cited_facts.append(f)

    if reasons:
        return False, StrippedSentence(
            section=section_name,
            sentence=sentence.sentence,
            cited_fact_ids=sentence.cited_fact_ids,
            reasons=reasons,
            ungrounded_entities=ungrounded,
        )

    # Build reference text and entities corpus from all cited facts
    reference_corpus_parts: list[str] = []
    for f in cited_facts:
        reference_corpus_parts.append(f.text)
        if f.raw_value is not None:
            reference_corpus_parts.append(str(f.raw_value))
        reference_corpus_parts.extend(f.entities)

    raw_reference = " ".join(reference_corpus_parts)
    norm_reference = _normalize_text_for_lookup(raw_reference)

    # Rule 3: Check all numbers, dates, and IDs
    entities = extract_entities_from_sentence(sentence.sentence)

    # Check dates
    for dt in entities["dates"]:
        norm_dt = _normalize_text_for_lookup(dt)
        if norm_dt not in norm_reference and dt not in raw_reference:
            reasons.append(f"Fabricated date: '{dt}' does not appear in any cited fact.")
            ungrounded.append(dt)

    # Check IDs
    for item_id in entities["ids"]:
        norm_id = _normalize_text_for_lookup(item_id)
        if norm_id not in norm_reference and item_id not in raw_reference:
            reasons.append(f"Fabricated ID: '{item_id}' does not appear in any cited fact.")
            ungrounded.append(item_id)

    # Check numbers
    for num in entities["numbers"]:
        # Strip trailing .00 or leading zeros for numeric comparison
        num_variants = [num]
        try:
            val_float = float(num)
            if val_float.is_integer():
                num_variants.append(str(int(val_float)))
        except ValueError:
            pass

        found = any(v in raw_reference or _normalize_text_for_lookup(v) in norm_reference for v in num_variants)
        if not found:
            reasons.append(f"Fabricated number/amount: '{num}' does not appear in any cited fact.")
            ungrounded.append(num)

    if reasons:
        return False, StrippedSentence(
            section=section_name,
            sentence=sentence.sentence,
            cited_fact_ids=sentence.cited_fact_ids,
            reasons=reasons,
            ungrounded_entities=ungrounded,
        )

    return True, None


def verify_rebuttal(draft: RebuttalDraft, fact_set: FactSet) -> tuple[RebuttalDraft, VerifierReport]:
    """Deterministically verify a complete RebuttalDraft against the FactSet.

    Removes any failing sentences from the draft and returns the cleaned draft
    along with a comprehensive VerifierReport. Never silently passes ungrounded claims.

    Args:
        draft: Raw candidate RebuttalDraft.
        fact_set: Authoritative FactSet.

    Returns:
        Tuple of (verified_clean_draft, verifier_report).
    """
    total_sentences = 0
    valid_sentences = 0
    stripped: list[StrippedSentence] = []

    clean_sections: dict[str, list[DraftSentence]] = {
        "summary": [],
        "timeline": [],
        "evidence_list": [],
        "conclusion": [],
    }

    sections = [
        ("summary", draft.summary),
        ("timeline", draft.timeline),
        ("evidence_list", draft.evidence_list),
        ("conclusion", draft.conclusion),
    ]

    for sec_name, sentences in sections:
        for s in sentences:
            total_sentences += 1
            is_valid, fail_info = verify_sentence(s, sec_name, fact_set)
            if is_valid:
                clean_sections[sec_name].append(s)
                valid_sentences += 1
            else:
                assert fail_info is not None
                stripped.append(fail_info)

    clean_draft = RebuttalDraft(
        case_id=draft.case_id,
        dispute_id=draft.dispute_id,
        summary=clean_sections["summary"],
        timeline=clean_sections["timeline"],
        evidence_list=clean_sections["evidence_list"],
        conclusion=clean_sections["conclusion"],
    )

    report = VerifierReport(
        case_id=draft.case_id,
        total_sentences=total_sentences,
        valid_sentences=valid_sentences,
        stripped_count=len(stripped),
        is_clean=len(stripped) == 0,
        stripped_sentences=stripped,
    )

    return clean_draft, report
