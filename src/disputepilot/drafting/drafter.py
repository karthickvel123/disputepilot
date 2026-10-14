"""LLM-backed rebuttal drafter generating citation-backed defense narratives."""

import logging
from typing import Any

from pydantic import BaseModel, Field

from disputepilot.core.models import DisputeCase
from disputepilot.drafting.facts import FactSet
from disputepilot.extraction.llm import LLMClient, get_llm_client

logger = logging.getLogger("disputepilot.drafting.drafter")


class DraftSentence(BaseModel):
    """An individual sentence in the rebuttal citing the facts that ground it."""

    sentence: str
    cited_fact_ids: list[str] = Field(default_factory=list)


class RebuttalDraft(BaseModel):
    """Structured, citation-grounded rebuttal draft."""

    case_id: str
    dispute_id: str
    summary: list[DraftSentence] = Field(default_factory=list)
    timeline: list[DraftSentence] = Field(default_factory=list)
    evidence_list: list[DraftSentence] = Field(default_factory=list)
    conclusion: list[DraftSentence] = Field(default_factory=list)

    def all_sentences(self) -> list[DraftSentence]:
        """Return all sentences across all sections."""
        return self.summary + self.timeline + self.evidence_list + self.conclusion

    def to_markdown(self) -> str:
        """Render complete rebuttal draft into a clean, structured Markdown letter."""
        lines: list[str] = [
            f"# Dispute Contest Rebuttal: {self.dispute_id}",
            f"**Case Reference**: {self.case_id}\n",
            "## Summary",
        ]
        for s in self.summary:
            citations = " " + " ".join(f"[{fid}]" for fid in s.cited_fact_ids) if s.cited_fact_ids else ""
            lines.append(f"- {s.sentence}{citations}")

        lines.append("\n## Timeline of Events")
        for s in self.timeline:
            citations = " " + " ".join(f"[{fid}]" for fid in s.cited_fact_ids) if s.cited_fact_ids else ""
            lines.append(f"- {s.sentence}{citations}")

        lines.append("\n## Evidence Submitted")
        for s in self.evidence_list:
            citations = " " + " ".join(f"[{fid}]" for fid in s.cited_fact_ids) if s.cited_fact_ids else ""
            lines.append(f"- {s.sentence}{citations}")

        lines.append("\n## Conclusion & Requested Action")
        for s in self.conclusion:
            citations = " " + " ".join(f"[{fid}]" for fid in s.cited_fact_ids) if s.cited_fact_ids else ""
            lines.append(f"- {s.sentence}{citations}")

        return "\n".join(lines)


SYSTEM_DRAFTING_PROMPT = """You are an expert legal drafter preparing formal payment dispute contest rebuttals for card networks and Razorpay.
CRITICAL NON-NEGOTIABLE GROUNDING RULES:
1. You may write ONLY using the verified facts provided in the Available Facts list.
2. Every sentence MUST include a 'cited_fact_ids' list citing the exact fact_id(s) that support all numbers, dates, IDs, and assertions in that sentence.
3. NEVER invent, extrapolate, or hallucinate dates, amounts, courier names, tracking IDs, or order numbers.
4. If a fact is not in the list, DO NOT MENTION IT.
5. Follow the fixed section template:
   - 'summary': High-level dispute contest assertion.
   - 'timeline': Chronological sequence of order creation, fulfillment, and dispute.
   - 'evidence_list': Description of verified documents attached.
   - 'conclusion': Clear demand for dispute reversal with reference to disputed amount and dispute ID.
"""


class RebuttalDrafter:
    """Orchestrates LLM rebuttal drafting adhering to strict factual citations."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm = llm_client or get_llm_client()

    def draft(self, case: DisputeCase, facts: FactSet) -> RebuttalDraft:
        """Generate a structured rebuttal draft citing verified facts.

        Args:
            case: DisputeCase being contested.
            facts: FactSet containing verified facts from API and extracted documents.

        Returns:
            Structured RebuttalDraft.
        """
        # Build structured fact list for LLM prompt
        facts_prompt_lines = [f"- [{f.fact_id}]: {f.text} (Source: {f.source})" for f in facts.facts]
        user_prompt = (
            f"Case ID: {case.case_id}\n"
            f"Dispute ID: {case.dispute.id}\n"
            f"Payment ID: {case.dispute.payment_id}\n\n"
            f"Available Facts:\n" + "\n".join(facts_prompt_lines) + "\n\n"
            "Draft a formal rebuttal contest letter conforming to the schema."
        )

        schema = {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "sentence": {"type": "string"},
                            "cited_fact_ids": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["sentence", "cited_fact_ids"],
                    },
                },
                "timeline": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "sentence": {"type": "string"},
                            "cited_fact_ids": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["sentence", "cited_fact_ids"],
                    },
                },
                "evidence_list": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "sentence": {"type": "string"},
                            "cited_fact_ids": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["sentence", "cited_fact_ids"],
                    },
                },
                "conclusion": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "sentence": {"type": "string"},
                            "cited_fact_ids": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["sentence", "cited_fact_ids"],
                    },
                },
            },
            "required": ["summary", "timeline", "evidence_list", "conclusion"],
        }

        try:
            raw_res = self.llm.generate_json(
                system=SYSTEM_DRAFTING_PROMPT,
                user=user_prompt,
                json_schema=schema,
            )
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            logger.error("LLM rebuttal drafting failed: %s", exc)
            raw_res = {}

        def parse_section(sec_data: Any) -> list[DraftSentence]:
            if not isinstance(sec_data, list):
                return []
            sentences: list[DraftSentence] = []
            for item in sec_data:
                if isinstance(item, dict) and "sentence" in item:
                    sentences.append(
                        DraftSentence(
                            sentence=item["sentence"].strip(),
                            cited_fact_ids=[str(f) for f in item.get("cited_fact_ids", [])],
                        )
                    )
            return sentences

        summary = parse_section(raw_res.get("summary"))
        timeline = parse_section(raw_res.get("timeline"))
        evidence_list = parse_section(raw_res.get("evidence_list"))
        conclusion = parse_section(raw_res.get("conclusion"))

        # If LLM returned empty or malformed draft, build safe deterministic baseline draft
        if not (summary or timeline or evidence_list or conclusion):
            summary = self._fallback_summary(facts)
            timeline = self._fallback_timeline(facts)
            evidence_list = self._fallback_evidence(facts)
            conclusion = self._fallback_conclusion(facts)

        return RebuttalDraft(
            case_id=case.case_id,
            dispute_id=case.dispute.id,
            summary=summary,
            timeline=timeline,
            evidence_list=evidence_list,
            conclusion=conclusion,
        )

    def _fallback_summary(self, facts: FactSet) -> list[DraftSentence]:
        sentences: list[DraftSentence] = []
        f_ord = facts.get_fact("fact_order_id")
        f_name = facts.get_fact("fact_customer_name")
        f_amt = facts.get_fact("fact_dispute_amount")
        f_disp = facts.get_fact("fact_dispute_id")

        if f_disp and f_amt:
            sentences.append(
                DraftSentence(
                    sentence=f"We formally contest dispute {f_disp.raw_value} regarding transaction of {f_amt.raw_value} paise.",
                    cited_fact_ids=["fact_dispute_id", "fact_dispute_amount"],
                )
            )
        if f_ord and f_name:
            sentences.append(
                DraftSentence(
                    sentence=f"The order {f_ord.raw_value} was lawfully placed and fulfilled for customer {f_name.raw_value}.",
                    cited_fact_ids=["fact_order_id", "fact_customer_name"],
                )
            )
        return sentences

    def _fallback_timeline(self, facts: FactSet) -> list[DraftSentence]:
        sentences: list[DraftSentence] = []
        f_ord_created = facts.get_fact("fact_order_created_at")
        if f_ord_created:
            sentences.append(
                DraftSentence(
                    sentence=f"Order was confirmed on epoch timestamp {f_ord_created.raw_value}.",
                    cited_fact_ids=["fact_order_created_at"],
                )
            )
        f_del = facts.get_fact("fact_order_delivered_at")
        if f_del:
            sentences.append(
                DraftSentence(
                    sentence=f"Courier delivery was completed on epoch timestamp {f_del.raw_value}.",
                    cited_fact_ids=["fact_order_delivered_at"],
                )
            )
        f_disp_created = facts.get_fact("fact_dispute_created_at")
        if f_disp_created:
            sentences.append(
                DraftSentence(
                    sentence=f"Dispute was received on epoch timestamp {f_disp_created.raw_value}.",
                    cited_fact_ids=["fact_dispute_created_at"],
                )
            )
        return sentences

    def _fallback_evidence(self, facts: FactSet) -> list[DraftSentence]:
        sentences: list[DraftSentence] = []
        f_trk = facts.get_fact("fact_tracking_number")
        if f_trk:
            sentences.append(
                DraftSentence(
                    sentence=f"Shipment was dispatched with courier tracking AWB {f_trk.raw_value}.",
                    cited_fact_ids=["fact_tracking_number"],
                )
            )
        # Add doc-based facts
        for f in facts.facts:
            if f.fact_id.startswith("fact_doc_") and "pod_status" in f.fact_id:
                sentences.append(
                    DraftSentence(
                        sentence=f"Carrier delivery documentation confirms delivery status as {f.raw_value}.",
                        cited_fact_ids=[f.fact_id],
                    )
                )
            elif f.fact_id.startswith("fact_doc_") and "invoice_number" in f.fact_id:
                sentences.append(
                    DraftSentence(
                        sentence=f"Tax invoice was issued with invoice number {f.raw_value}.",
                        cited_fact_ids=[f.fact_id],
                    )
                )
        return sentences

    def _fallback_conclusion(self, facts: FactSet) -> list[DraftSentence]:
        f_disp = facts.get_fact("fact_dispute_id")
        f_amt = facts.get_fact("fact_dispute_amount")
        if f_disp and f_amt:
            return [
                DraftSentence(
                    sentence=f"In conclusion, merchant has fully fulfilled terms of service for dispute {f_disp.raw_value} and requests immediate reversal of {f_amt.raw_value} paise.",
                    cited_fact_ids=["fact_dispute_id", "fact_dispute_amount"],
                )
            ]
        return [
            DraftSentence(
                sentence="Merchant requests dispute dismissal and credit restoration.",
                cited_fact_ids=[],
            )
        ]
