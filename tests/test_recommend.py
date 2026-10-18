"""Unit tests for Phase D heuristic contest-or-accept recommendation engine."""

import json
from pathlib import Path

from disputepilot.core.models import DisputeCase
from disputepilot.core.recommend import (
    HEURISTIC_DISCLAIMER,
    ContestDecision,
    recommend_action,
)
from disputepilot.extraction.cross_checks import CrossCheckFlag, SeverityTier


def load_simulated_cases(data_dir: str = "data/cases") -> list[DisputeCase]:
    """Load simulated cases from disk."""
    path = Path(data_dir)
    cases: list[DisputeCase] = []
    if not path.exists():
        return cases
    for jf in sorted(path.glob("*.json")):
        try:
            with open(jf, encoding="utf-8") as f:
                cases.append(DisputeCase.model_validate(json.load(f)))
        except (json.JSONDecodeError, OSError, ValueError):
            pass
    return cases


def test_missing_required_evidence_gives_needs_evidence() -> None:
    """Missing required evidence categories strictly output NeedsEvidence with no preselection."""
    cases = load_simulated_cases()
    # Find an item_not_received dispute case
    inr_cases = [c for c in cases if c.ground_truth.reason_class.value == "item_not_received"]
    assert inr_cases, "Expected item_not_received cases in simulated data"
    case = inr_cases[0]

    # Explicitly clear required shipping proof
    case.dispute.evidence.shipping_proof = []

    rec = recommend_action(case=case)
    assert rec.decision == ContestDecision.NEEDS_EVIDENCE
    assert rec.preselect_action is None
    assert any("Needs evidence" in r for r in rec.reasons)
    assert any("shipping_proof" in r for r in rec.reasons)
    assert rec.disclaimer == HEURISTIC_DISCLAIMER


def test_high_win_rate_with_positive_ev_recommends_contest() -> None:
    """Strong evidence completeness and high win probability yield Contest."""
    cases = load_simulated_cases()
    case = cases[0]

    # Supply complete evidence
    case.dispute.evidence.shipping_proof = ["doc_pod_1.pdf"]
    case.dispute.evidence.billing_proof = ["doc_invoice_1.pdf"]
    case.dispute.amount = 1000000  # ₹10,000

    rec = recommend_action(case=case, effort_cost_paise=20000)
    assert rec.expected_value_paise > 0
    assert rec.p_win > 0.50
    assert rec.decision == ContestDecision.CONTEST
    if not rec.is_uncertain:
        assert rec.preselect_action == "contest"


def test_critical_cross_check_flag_drops_score_and_recommends_accept() -> None:
    """Severe discrepancy flag drops win probability and recommends Accept."""
    cases = load_simulated_cases()
    case = cases[0]

    # Create dummy evidence report with critical discrepancy flag
    from disputepilot.agent.models import EvidenceReport

    report = EvidenceReport(
        case_id=case.case_id,
        reason_class="item_not_received",
        category_docs={"shipping_proof": ["doc_1"]},
        category_confidence={"shipping_proof": 0.95},
        category_status={"shipping_proof": "partial"},
        cross_check_flags=[
            CrossCheckFlag(
                flag_code="DELIVERY_AFTER_DISPUTE",
                severity=SeverityTier.CRITICAL,
                message="Delivery occurred 3 days after dispute was lodged.",
            )
        ],
        specific_asks={},
        tool_audit_trail=[],
    )

    case.dispute.amount = 50000  # Small amount ₹500
    rec = recommend_action(case=case, evidence_report=report, effort_cost_paise=50000)

    assert rec.decision == ContestDecision.ACCEPT
    assert rec.expected_value_paise <= 0
    assert any("DELIVERY_AFTER_DISPUTE" in r for r in rec.reasons)


def test_uncertain_band_preselects_nothing() -> None:
    """When win probability falls into uncertain band (0.35-0.55), is_uncertain is True and nothing is preselected."""
    cases = load_simulated_cases()
    case = cases[0]

    from disputepilot.agent.models import EvidenceReport

    report = EvidenceReport(
        case_id=case.case_id,
        reason_class="unauthorised",  # prior 0.45
        category_docs={"customer_communication": ["doc_chat"]},
        category_confidence={"customer_communication": 0.8},
        category_status={"customer_communication": "present", "access_activity_log": "partial"},
        cross_check_flags=[],
        specific_asks={},
        tool_audit_trail=[],
    )

    rec = recommend_action(case=case, evidence_report=report)
    if 0.35 <= rec.p_win <= 0.55 or (rec.p_win_high - rec.p_win_low >= 0.30):
        assert rec.is_uncertain is True
        assert rec.preselect_action is None


def test_effort_cost_configuration_alters_expected_value() -> None:
    """Configuring high effort cost reduces EV and shifts decision toward Accept."""
    cases = load_simulated_cases()
    case = cases[0]
    case.dispute.amount = 30000  # ₹300

    # Low effort cost ₹50 (5000 paise)
    rec_low = recommend_action(case=case, effort_cost_paise=5000)

    # High effort cost ₹500 (50000 paise) exceeding dispute amount
    rec_high = recommend_action(case=case, effort_cost_paise=50000)

    assert rec_high.expected_value_paise < rec_low.expected_value_paise
    assert rec_high.expected_value_paise < 0
    assert rec_high.decision == ContestDecision.ACCEPT


def test_unclassified_reason_returns_uncertain_state() -> None:
    """When the reason is unclassified, return Uncertain state, preselect nothing, no 'other' prior."""
    cases = load_simulated_cases()
    case = cases[0]
    case.dispute.reason_code = "UNKNOWN_REASON_CODE_404"

    rec = recommend_action(case=case)
    assert rec.decision == ContestDecision.UNCERTAIN
    assert rec.is_uncertain is True
    assert rec.preselect_action is None
    assert rec.p_win == "n/a"
    assert rec.p_win_low == "n/a"
    assert rec.p_win_high == "n/a"
    assert rec.expected_value_paise == "n/a"
    assert "reason could not be classified" in rec.reasons

    # Also test when EvidenceReport has unclassified reason_class
    from disputepilot.agent.models import EvidenceReport

    report = EvidenceReport(
        case_id=case.case_id,
        reason_class="unclassified",
        category_docs={},
        category_confidence={},
        category_status={},
        cross_check_flags=[],
        specific_asks={},
        tool_audit_trail=[],
    )
    rec_report = recommend_action(case=case, evidence_report=report)
    assert rec_report.decision == ContestDecision.UNCERTAIN
    assert rec_report.is_uncertain is True
    assert rec_report.preselect_action is None
    assert rec_report.p_win == "n/a"
    assert rec_report.p_win_low == "n/a"
    assert rec_report.p_win_high == "n/a"
    assert rec_report.expected_value_paise == "n/a"
    assert "reason could not be classified" in rec_report.reasons

