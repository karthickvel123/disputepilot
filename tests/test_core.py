"""Comprehensive test suite for the deterministic core modules and edge cases."""

from disputepilot.core.deadlines import UrgencyLevel, calculate_deadline
from disputepilot.core.evidence import (
    CategoryStatus,
    audit_evidence,
    get_requirements_for_class,
)
from disputepilot.core.models import RazorpayEvidence, ReasonClass
from disputepilot.core.reasons import classify_reason
from disputepilot.core.triage import calculate_priority, triage_cases

# ==============================================================================
# 1. Deadlines & Urgency Tests (including overdue & missing respond_by)
# ==============================================================================


def test_deadlines_urgency_tiers_and_reminders() -> None:
    """Verify urgency tiers and reminder calculation at T-48h, T-24h, T-12h."""
    target_respond_by = 1715000000

    # Overdue: now > respond_by
    dl_overdue = calculate_deadline(
        {"id": "disp_001", "respond_by": target_respond_by},
        now=target_respond_by + 3600,
    )
    assert dl_overdue.is_overdue is True
    assert dl_overdue.urgency == UrgencyLevel.OVERDUE
    assert dl_overdue.hours_remaining == -1.0

    # Critical: within 24 hours (e.g. 10 hours remaining)
    dl_critical = calculate_deadline(
        {"id": "disp_002", "respond_by": target_respond_by},
        now=target_respond_by - (10 * 3600),
    )
    assert dl_critical.is_overdue is False
    assert dl_critical.urgency == UrgencyLevel.CRITICAL
    assert dl_critical.hours_remaining == 10.0

    # Soon: between 24h and 48h (e.g. 36 hours remaining)
    dl_soon = calculate_deadline(
        {"id": "disp_003", "respond_by": target_respond_by},
        now=target_respond_by - (36 * 3600),
    )
    assert dl_soon.is_overdue is False
    assert dl_soon.urgency == UrgencyLevel.SOON
    assert dl_soon.hours_remaining == 36.0

    # OK: more than 48 hours remaining (e.g. 72 hours remaining)
    dl_ok = calculate_deadline(
        {"id": "disp_004", "respond_by": target_respond_by},
        now=target_respond_by - (72 * 3600),
    )
    assert dl_ok.is_overdue is False
    assert dl_ok.urgency == UrgencyLevel.OK
    assert dl_ok.hours_remaining == 72.0

    # Verify exact reminder times at T-48h, T-24h, T-12h
    reminders = dl_ok.reminders
    assert reminders["t_minus_48h"] == target_respond_by - (48 * 3600)
    assert reminders["t_minus_24h"] == target_respond_by - (24 * 3600)
    assert reminders["t_minus_12h"] == target_respond_by - (12 * 3600)


def test_deadlines_edge_cases_missing_and_zero_respond_by() -> None:
    """Edge case: verify missing, None, or zero respond_by handled safely."""
    # None respond_by
    dl_none = calculate_deadline({"id": "disp_none", "respond_by": None}, now=1715000000)
    assert dl_none.urgency == UrgencyLevel.UNKNOWN
    assert dl_none.hours_remaining is None
    assert dl_none.is_overdue is False
    assert dl_none.reminders["t_minus_48h"] is None

    # Zero respond_by
    dl_zero = calculate_deadline({"id": "disp_zero", "respond_by": 0}, now=1715000000)
    assert dl_zero.urgency == UrgencyLevel.UNKNOWN
    assert dl_zero.hours_remaining is None
    assert dl_zero.is_overdue is False

    # Negative respond_by
    dl_neg = calculate_deadline({"id": "disp_neg", "respond_by": -100}, now=1715000000)
    assert dl_neg.urgency == UrgencyLevel.UNKNOWN


# ==============================================================================
# 2. Reasons Mapping Tests (including unknown reason & keyword mapping)
# ==============================================================================


def test_reasons_exact_code_mapping() -> None:
    """Verify standard Razorpay and card network codes map to correct reason class."""
    test_cases = [
        ("13.1", ReasonClass.ITEM_NOT_RECEIVED),
        ("merchandise_not_received", ReasonClass.ITEM_NOT_RECEIVED),
        ("4855", ReasonClass.ITEM_NOT_RECEIVED),
        ("13.3", ReasonClass.NOT_AS_DESCRIBED),
        ("4853", ReasonClass.NOT_AS_DESCRIBED),
        ("10.4", ReasonClass.UNAUTHORISED),
        ("4837", ReasonClass.UNAUTHORISED),
        ("fraud_card_not_present", ReasonClass.UNAUTHORISED),
        ("12.6", ReasonClass.DUPLICATE_CHARGE),
        ("duplicate_processing", ReasonClass.DUPLICATE_CHARGE),
        ("13.7", ReasonClass.SUBSCRIPTION_CANCELLED),
        ("cancelled_recurring", ReasonClass.SUBSCRIPTION_CANCELLED),
        ("13.6", ReasonClass.REFUND_NOT_RECEIVED),
        ("credit_not_processed", ReasonClass.REFUND_NOT_RECEIVED),
        ("general_inquiry", ReasonClass.OTHER),
        ("retrieval_request", ReasonClass.OTHER),
    ]

    for code, expected_class in test_cases:
        match = classify_reason(code)
        assert match.reason_class == expected_class
        assert "exact_code" in match.rule_matched


def test_reasons_keyword_mapping() -> None:
    """Verify free-text descriptions map to the appropriate reason class."""
    keyword_cases = [
        ("Customer states package was not received after 2 weeks", ReasonClass.ITEM_NOT_RECEIVED),
        ("Item arrived damaged and defective from transit", ReasonClass.NOT_AS_DESCRIBED),
        ("Cardholder reported unauthorized fraud transaction", ReasonClass.UNAUTHORISED),
        ("Cardholder was charged twice for a single order", ReasonClass.DUPLICATE_CHARGE),
        ("Subscription cancelled prior to renewal billing", ReasonClass.SUBSCRIPTION_CANCELLED),
        ("Customer claims refund missing from bank statement", ReasonClass.REFUND_NOT_RECEIVED),
        ("General clarification requested on invoice", ReasonClass.OTHER),
    ]

    for text, expected_class in keyword_cases:
        match = classify_reason(text)
        assert match.reason_class == expected_class
        assert "keyword" in match.rule_matched


def test_reasons_edge_case_unknown_and_empty() -> None:
    """Edge case: unknown reason strings, empty string, and None."""
    # Unknown reason code without LLM
    unknown = classify_reason("XYZ_RANDOM_CODE_9999")
    assert unknown.reason_class == ReasonClass.UNCLASSIFIED
    assert unknown.needs_review is True
    assert "unclassified" in unknown.rule_matched

    # Empty string
    empty = classify_reason("   ")
    assert empty.reason_class == ReasonClass.UNCLASSIFIED
    assert empty.needs_review is True
    assert empty.rule_matched == "empty_reason"

    # None
    none_match = classify_reason(None)
    assert none_match.reason_class == ReasonClass.UNCLASSIFIED
    assert none_match.needs_review is True
    assert none_match.rule_matched == "empty_reason"


def test_reasons_llm_classification_success() -> None:
    """Test LLM classification fallback with high confidence."""
    class MockLLM:
        def generate_json(
            self,
            system: str,
            user: str,
            json_schema: object,
            case_id: str | None = None,
            stage: str | None = None,
        ) -> dict[str, object]:
            return {
                "reason_class": "item_not_received",
                "confidence": 0.88,
                "quote": "parcel gayab ho gaya",
            }

    match = classify_reason("parcel gayab ho gaya", llm_client=MockLLM())
    assert match.reason_class == ReasonClass.ITEM_NOT_RECEIVED
    assert match.confidence == 0.88
    assert match.quote == "parcel gayab ho gaya"
    assert match.needs_review is False
    assert match.rule_matched == "llm:item_not_received"


def test_reasons_llm_classification_low_confidence_or_unclassified() -> None:
    """Test LLM classification rejection when confidence < 0.6 or unclassified."""
    class LowConfLLM:
        def generate_json(
            self,
            system: str,
            user: str,
            json_schema: object,
            case_id: str | None = None,
            stage: str | None = None,
        ) -> dict[str, object]:
            return {
                "reason_class": "unauthorised",
                "confidence": 0.45,
                "quote": "maybe fraud",
            }

    match_low = classify_reason("some weird reason", llm_client=LowConfLLM())
    assert match_low.reason_class == ReasonClass.UNCLASSIFIED
    assert match_low.needs_review is True

    class UnclassifiedLLM:
        def generate_json(
            self,
            system: str,
            user: str,
            json_schema: object,
            case_id: str | None = None,
            stage: str | None = None,
        ) -> dict[str, object]:
            return {
                "reason_class": "unclassified",
                "confidence": 0.95,
                "quote": "unclear",
            }

    match_unclass = classify_reason("completely bizarre claim", llm_client=UnclassifiedLLM())
    assert match_unclass.reason_class == ReasonClass.UNCLASSIFIED
    assert match_unclass.needs_review is True

    class FailingLLM:
        def generate_json(
            self,
            system: str,
            user: str,
            json_schema: object,
            case_id: str | None = None,
            stage: str | None = None,
        ) -> dict[str, object]:
            raise RuntimeError("API timeout")

    match_fail = classify_reason("failed call", llm_client=FailingLLM())
    assert match_fail.reason_class == ReasonClass.UNCLASSIFIED
    assert match_fail.needs_review is True
    assert match_fail.rule_matched == "unclassified:llm_unavailable"


# ==============================================================================
# 3. Requirements & Evidence Audit Tests (including empty evidence & partial)
# ==============================================================================


def test_requirements_roles_per_reason_class() -> None:
    """Verify required, helpful, and irrelevant categories per class."""
    inr_reqs = get_requirements_for_class(ReasonClass.ITEM_NOT_RECEIVED)
    assert "shipping_proof" in inr_reqs["required"]
    assert "billing_proof" in inr_reqs["helpful"]
    assert "cancellation_proof" in inr_reqs["irrelevant"]

    sub_reqs = get_requirements_for_class(ReasonClass.SUBSCRIPTION_CANCELLED)
    assert "refund_cancellation_policy" in sub_reqs["required"]
    assert "access_activity_log" in sub_reqs["helpful"]
    assert "shipping_proof" in sub_reqs["irrelevant"]

    rfnd_reqs = get_requirements_for_class(ReasonClass.REFUND_NOT_RECEIVED)
    assert "refund_confirmation" in rfnd_reqs["required"]


def test_evidence_audit_present_missing_partial() -> None:
    """Verify audit returns present, missing, or partial per category."""
    # Complete required evidence
    audit_complete = audit_evidence(
        reason_class=ReasonClass.ITEM_NOT_RECEIVED,
        available_evidence=["shipping_proof", "billing_proof"],
    )
    assert audit_complete.categories["shipping_proof"].status == CategoryStatus.PRESENT
    assert audit_complete.categories["billing_proof"].status == CategoryStatus.PRESENT
    assert audit_complete.categories["customer_communication"].status == CategoryStatus.MISSING
    assert audit_complete.required_satisfied is True

    # Missing required evidence
    audit_missing = audit_evidence(
        reason_class=ReasonClass.ITEM_NOT_RECEIVED,
        available_evidence=["billing_proof"],  # shipping_proof missing
    )
    assert audit_missing.categories["shipping_proof"].status == CategoryStatus.MISSING
    assert audit_missing.required_satisfied is False

    # Partial evidence (empty document string reference)
    audit_partial = audit_evidence(
        reason_class=ReasonClass.ITEM_NOT_RECEIVED,
        available_evidence={"shipping_proof": [""]},
    )
    assert audit_partial.categories["shipping_proof"].status == CategoryStatus.PARTIAL
    assert audit_partial.required_satisfied is False


def test_evidence_edge_case_empty_evidence() -> None:
    """Edge case: empty evidence list, empty dict, or None."""
    # None
    audit_none = audit_evidence(reason_class=ReasonClass.ITEM_NOT_RECEIVED, available_evidence=None)
    assert audit_none.required_satisfied is False
    assert len(audit_none.present_categories) == 0
    assert audit_none.categories["shipping_proof"].status == CategoryStatus.MISSING

    # Empty list
    audit_empty_list = audit_evidence(reason_class=ReasonClass.ITEM_NOT_RECEIVED, available_evidence=[])
    assert audit_empty_list.required_satisfied is False
    assert audit_empty_list.categories["shipping_proof"].status == CategoryStatus.MISSING

    # Empty RazorpayEvidence model
    empty_ev_model = RazorpayEvidence()
    audit_model = audit_evidence(reason_class=ReasonClass.UNAUTHORISED, available_evidence=empty_ev_model)
    assert audit_model.required_satisfied is False
    assert audit_model.categories["billing_proof"].status == CategoryStatus.MISSING


# ==============================================================================
# 4. Triage & Priority Ranking Tests
# ==============================================================================


def test_triage_priority_calculation() -> None:
    """Verify priority formula: priority = (amount * p_win) / effort."""
    # 500000 paise (₹5,000), p_win = 0.70, effort = 1.0 -> 350000.0
    p1 = calculate_priority(amount_paise=500000, p_win=0.70, effort=1.0)
    assert p1 == 350000.0

    # 500000 paise, p_win = 0.50, effort = 2.0 -> 125000.0
    p2 = calculate_priority(amount_paise=500000, p_win=0.50, effort=2.0)
    assert p2 == 125000.0

    assert p1 > p2


def test_triage_worklist_ranking_and_tie_breaking() -> None:
    """Verify triage ranks cases in descending order of priority with deadline tie-breaking."""
    cases = [
        {
            "id": "disp_low_amount",
            "dispute": {"id": "disp_low_amount", "amount": 100000, "reason_code": "13.1", "respond_by": 1715050000},
        },
        {
            "id": "disp_high_amount",
            "dispute": {"id": "disp_high_amount", "amount": 900000, "reason_code": "13.1", "respond_by": 1715090000},
        },
        # Two cases with identical priority score: earlier deadline should rank higher
        {
            "id": "disp_tie_late_deadline",
            "dispute": {"id": "disp_tie_late_deadline", "amount": 300000, "reason_code": "13.1", "respond_by": 1715080000},
        },
        {
            "id": "disp_tie_early_deadline",
            "dispute": {"id": "disp_tie_early_deadline", "amount": 300000, "reason_code": "13.1", "respond_by": 1715020000},
        },
    ]

    worklist = triage_cases(cases, now=1715000000)

    assert len(worklist) == 4
    # Highest amount with same p_win and effort should be rank 1
    assert worklist[0].case_id == "disp_high_amount"
    assert worklist[0].rank == 1

    # Tie-break check: earlier deadline (1715020000) must rank before later deadline (1715080000)
    assert worklist[1].case_id == "disp_tie_early_deadline"
    assert worklist[2].case_id == "disp_tie_late_deadline"

    # Lowest amount should be rank 4
    assert worklist[3].case_id == "disp_low_amount"
    assert worklist[3].rank == 4


def test_triage_custom_weights() -> None:
    """Verify custom p_win and effort mappings alter triage ranking."""
    cases = [
        {
            "id": "disp_inr",
            "dispute": {"id": "disp_inr", "amount": 500000, "reason_code": "13.1", "respond_by": 1715050000},
        },
        {
            "id": "disp_fraud",
            "dispute": {"id": "disp_fraud", "amount": 500000, "reason_code": "10.4", "respond_by": 1715050000},
        },
    ]

    # Custom weights where fraud has higher p_win / effort ratio
    custom_p_win = {ReasonClass.ITEM_NOT_RECEIVED: 0.2, ReasonClass.UNAUTHORISED: 0.9}
    custom_effort = {ReasonClass.ITEM_NOT_RECEIVED: 1.0, ReasonClass.UNAUTHORISED: 1.0}

    worklist = triage_cases(cases, p_win_map=custom_p_win, effort_map=custom_effort)
    assert worklist[0].case_id == "disp_fraud"
    assert worklist[1].case_id == "disp_inr"
