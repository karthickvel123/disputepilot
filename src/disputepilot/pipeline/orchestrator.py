"""End-to-end processing pipeline for dispute cases."""

import json
import os
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from disputepilot.agent.models import EvidenceReport
from disputepilot.agent.orchestrator import EvidenceAgent
from disputepilot.agent.tools import ReadOnlyToolRegistry
from disputepilot.core.models import DisputeCase
from disputepilot.core.recommend import Recommendation, recommend_action
from disputepilot.drafting.drafter import RebuttalDraft, RebuttalDrafter
from disputepilot.drafting.facts import build_fact_set
from disputepilot.drafting.verifier import VerifierReport, verify_rebuttal
from disputepilot.extraction.extractor import ExtractedDocument
from disputepilot.extraction.llm import LLMClient, get_llm_client
from disputepilot.pipeline.audit import record_audit_event
from disputepilot.pipeline.reminders import compute_and_record_reminders
from disputepilot.razorpay.gateway import DisputesGateway, SimGateway


class CaseProcessingResult(BaseModel):
    """Encapsulates the complete result of running the DisputePilot pipeline over a case."""

    case_id: str
    evidence_report: EvidenceReport
    recommendation: Recommendation
    clean_draft: RebuttalDraft
    verifier_report: VerifierReport
    audit_hash: str
    extracted_docs: list[ExtractedDocument] = Field(default_factory=list)


CASE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_]+$")


def _load_case_by_id(case_id: str, data_dir: Path | str = "data/cases") -> DisputeCase:
    """Load a DisputeCase by its case_id from disk."""
    if not case_id or not CASE_ID_PATTERN.match(case_id):
        raise FileNotFoundError(f"Case with ID '{case_id}' not found.")

    path = Path(data_dir)
    target = path / f"{case_id}.json"
    if not target.exists():
        # Search all json files in data_dir
        for p in path.glob("*.json"):
            try:
                with open(p, encoding="utf-8") as f:
                    c = json.load(f)
                    if c.get("case_id") == case_id:
                        return DisputeCase.model_validate(c)
            except (json.JSONDecodeError, OSError, ValueError):
                pass
        raise FileNotFoundError(f"Case with ID '{case_id}' not found in {data_dir}.")

    with open(target, encoding="utf-8") as f:
        return DisputeCase.model_validate(json.load(f))


def process_case(
    case_id: str,
    gateway: DisputesGateway | None = None,
    llm_client: LLMClient | None = None,
    now: int | None = None,
    data_dir: Path | str = "data/cases",
    drafts_dir: Path | str = "data/drafts",
    audit_db_path: Path | str = "data/audit.db",
    reminders_db_path: Path | str = "data/reminders.db",
    rule_only_reasons: bool = False,
    case: DisputeCase | None = None,
    push_draft: bool = True,
) -> CaseProcessingResult:
    """Execute the end-to-end DisputePilot processing pipeline for a single dispute case.

    Pipeline stages:
    1. Ingestion: Load case and initialize read-only tool registry.
    2. Extraction & Cross-Checks: Run bounded EvidenceAgent to audit evidence and detect discrepancies.
    3. Recommendation: Compute win probability (p_win), EV, and Contest/Accept/NeedsEvidence decision.
    4. Drafting: Assemble verified FactSet and draft citation-grounded rebuttal letter.
    5. Verification: Deterministically audit rebuttal draft, stripping fabricated or ungrounded claims.
    6. Audit Logging: Record tamper-evident cryptographic hash chain event in SQLite.
    7. Reminders: Compute and record T-48h, T-24h, T-12h reminders in SQLite.
    8. Draft Saving: Save draft to disk and optionally call gateway contest(action='draft').

    CRITICAL SAFETY GUARANTEE:
    This function NEVER calls accept or submit on any gateway.

    Args:
        case_id: Target dispute case ID.
        gateway: Optional DisputesGateway instance (default SimGateway).
        llm_client: Optional LLM client (defaults to offline FakeLLMClient if unset).
        now: Injectable unix timestamp.
        data_dir: Cases storage directory.
        drafts_dir: Output drafts directory.
        audit_db_path: Path to audit log SQLite database.
        reminders_db_path: Path to reminders SQLite database.
        rule_only_reasons: If True, EvidenceAgent only classifies reasons using deterministic rules.
        case: Pre-loaded case (live mode). When omitted the case is read from ``data_dir``.
        push_draft: If True, also save the draft to the gateway (action="draft"). Live mode passes
            False so that merely viewing a case never writes to Razorpay.

    Returns:
        CaseProcessingResult instance containing all pipeline artifacts.
    """
    base_data = Path(os.environ.get("DATA_DIR", "data"))
    if str(data_dir) == "data/cases" and os.environ.get("DATA_DIR"):
        data_dir = base_data / "cases"
    if str(drafts_dir) == "data/drafts" and os.environ.get("DATA_DIR"):
        drafts_dir = base_data / "drafts"
    if str(audit_db_path) == "data/audit.db" and os.environ.get("DATA_DIR"):
        audit_db_path = base_data / "audit.db"
    if str(reminders_db_path) == "data/reminders.db" and os.environ.get("DATA_DIR"):
        reminders_db_path = base_data / "reminders.db"

    client = llm_client or get_llm_client()
    gw = gateway or SimGateway(data_dir=Path(data_dir), drafts_dir=Path(drafts_dir))

    # 1. Load case
    if case is None:
        case = _load_case_by_id(case_id, data_dir=data_dir)

    # 2. Evidence Agent Audit
    registry = ReadOnlyToolRegistry(case=case, llm_client=client)
    agent = EvidenceAgent(tool_registry=registry, llm_client=client, rule_only_reasons=rule_only_reasons)
    evidence_report = agent.audit_case(case_id)

    # 3. Recommendation Engine
    recommendation = recommend_action(case=case, evidence_report=evidence_report)

    # 4. Assemble Verified FactSet and Draft Rebuttal
    # Retrieve extracted documents cached in tool registry
    extracted_docs: list[ExtractedDocument] = list(registry._extracted_cache.values())
    facts = build_fact_set(case=case, extracted_docs=extracted_docs)

    drafter = RebuttalDrafter(llm_client=client)
    raw_draft = drafter.draft(case=case, facts=facts)

    # 5. Deterministic Verification
    clean_draft, verifier_report = verify_rebuttal(draft=raw_draft, fact_set=facts)

    # 6. Audit Logging
    audit_details: dict[str, Any] = {
        "dispute_id": case.dispute.id,
        "recommendation": recommendation.model_dump(),
        "is_clean": verifier_report.is_clean,
        "stripped_count": verifier_report.stripped_count,
        "evidence_categories": list(evidence_report.category_status.keys()),
    }
    audit_hash = record_audit_event(
        case_id=case_id,
        action="processed",
        actor="pipeline",
        details=audit_details,
        timestamp=now,
        db_path=audit_db_path,
    )

    # 7. Compute Reminders
    compute_and_record_reminders(case=case, now=now, db_path=reminders_db_path)

    # 8. Save Draft via Gateway (strictly action="draft", NEVER submit or accept)
    if push_draft:
        gw.contest_dispute(
            dispute_id=case.dispute.id,
            action="draft",  # Only "draft" allowed here, never submit
            summary=clean_draft.to_markdown(),
        )

    # Save full processed result to drafts directory
    out_dir = Path(drafts_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result = CaseProcessingResult(
        case_id=case_id,
        evidence_report=evidence_report,
        recommendation=recommendation,
        clean_draft=clean_draft,
        verifier_report=verifier_report,
        audit_hash=audit_hash,
        extracted_docs=extracted_docs,
    )
    with open(out_dir / f"{case_id}_result.json", "w", encoding="utf-8") as f:
        f.write(result.model_dump_json(indent=2))

    return result
