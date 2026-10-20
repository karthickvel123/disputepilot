"""Regression tests for the economic model, policy comparison and eval-metric fixes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from disputepilot.core.economics import (
    CaseRecord,
    CostModel,
    base_rate_brier,
    break_even_contest_effort,
    break_even_p_win,
    brier_score,
    compare_policies,
    expected_net_advantage_of_contest,
    log_loss,
)
from disputepilot.core.models import DisputeCase
from disputepilot.core.recommend import ContestDecision, recommend_action
from disputepilot.evals.runner import evaluate_reason_classifier


def _cases(n: int = 20) -> list[DisputeCase]:
    out = []
    for jf in sorted(Path("data/cases").glob("*.json"))[: n * 3]:
        try:
            out.append(DisputeCase.model_validate(json.loads(jf.read_text(encoding="utf-8"))))
        except ValueError:
            continue
        if len(out) >= n:
            break
    return out


# ------------------------------------------------------------------ formula


def test_ev_formula_fee_on_loss() -> None:
    cm = CostModel(fee_inr=50, contest_effort_inr=100)
    # 0.5*(1000-100) + 0.5*(-100-50) = 375
    assert expected_net_advantage_of_contest(0.5, 1000, cm) == pytest.approx(375.0)


def test_ev_formula_fee_on_every_contest_is_not_double_counted() -> None:
    cm = CostModel(fee_inr=50, fee_trigger="contest", contest_effort_inr=100)
    # win: 1000-100-50 ; lose: -100-50 ; p=0.5 -> 0.5*850 + 0.5*(-150) = 350
    assert expected_net_advantage_of_contest(0.5, 1000, cm) == pytest.approx(350.0)


def test_ev_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        expected_net_advantage_of_contest(1.2, 100, CostModel())
    with pytest.raises(ValueError):
        expected_net_advantage_of_contest(0.5, -1, CostModel())
    with pytest.raises(ValueError):
        CostModel(fee_inr=-1)


def test_break_even_p_win_matches_zero_ev() -> None:
    cm = CostModel(fee_inr=50, contest_effort_inr=100)
    p = break_even_p_win(1000, cm)
    assert p is not None
    assert expected_net_advantage_of_contest(p, 1000, cm) == pytest.approx(0.0, abs=1e-9)


def test_amount_smaller_than_costs_never_positive_ev() -> None:
    cm = CostModel(contest_effort_inr=500)
    assert expected_net_advantage_of_contest(1.0, 100, cm) < 0


# ------------------------------------------------------- policy comparison


def _records() -> list[CaseRecord]:
    return [
        CaseRecord("a", 1000.0, True),
        CaseRecord("b", 2000.0, False),
        CaseRecord("c", 500.0, True),
        CaseRecord("d", 800.0, False),
    ]


def test_zero_cost_makes_contest_all_unbeatable() -> None:
    """Root cause of the legacy negative uplift: with zero costs nothing can beat contest-all."""
    recs = _records()
    out = compare_policies(recs, {}, CostModel())
    assert out["policies"]["oracle_upper_bound"]["uplift_vs_contest_all_inr"] == 0
    assert out["policies"]["accept_all"]["uplift_vs_contest_all_inr"] < 0


def test_oracle_beats_contest_all_when_contesting_costs_money() -> None:
    out = compare_policies(_records(), {}, CostModel(contest_effort_inr=100, fee_inr=50))
    assert out["policies"]["oracle_upper_bound"]["uplift_vs_contest_all_inr"] > 0


def test_policies_must_cover_identical_cases() -> None:
    recs = _records()
    with pytest.raises(ValueError):
        compare_policies(recs, {"p": {"a": "contest", "b": "accept"}}, CostModel())


def test_duplicate_case_ids_rejected() -> None:
    with pytest.raises(ValueError):
        compare_policies([CaseRecord("x", 1.0, True), CaseRecord("x", 2.0, False)], {}, CostModel())


def test_escalations_are_counted_and_cost_review_time() -> None:
    recs = _records()
    cm = CostModel(review_cost_inr=10)
    pol = {r.case_id: "escalate" for r in recs}
    res = compare_policies(recs, {"p": pol}, cm, resolution="accept")["policies"]["p"]
    assert res["n_escalated"] == 4 and res["n_contested"] == 0
    assert res["net_value_inr_simulated"] == pytest.approx(-40.0)
    assert res["operational_costs_inr"] == pytest.approx(40.0)
    assert res["missed_opportunities"] == 2  # two winnable cases never contested


def test_break_even_effort_is_where_uplift_crosses_zero() -> None:
    recs = _records()
    # policy contests only the winnable ones except it wrongly skips "c"
    pol = {"a": "contest", "b": "accept", "c": "accept", "d": "accept"}
    be = break_even_contest_effort(recs, pol, CostModel())
    assert be is not None
    at = compare_policies(recs, {"p": pol}, CostModel(contest_effort_inr=be))
    assert at["policies"]["p"]["uplift_vs_contest_all_inr"] == pytest.approx(0.0, abs=0.05)


# ---------------------------------------------------- recommender behaviour


def test_configured_fee_now_reduces_expected_value(tmp_path: Path) -> None:
    """Regression: fee_per_dispute_paise was configured but never applied to EV."""
    case = _cases(1)[0]
    base_cfg = yaml.safe_load(
        (Path("src/disputepilot/core/recommend.yaml")).read_text(encoding="utf-8")
    )
    cfg = {**base_cfg, "fee_per_dispute_paise": 50_000}
    path = tmp_path / "fee.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    free = recommend_action(case)
    fee = recommend_action(case, config_path=path)
    if isinstance(free.expected_value_paise, int):
        assert fee.expected_value_paise < free.expected_value_paise


def test_cost_model_overrides_effort() -> None:
    case = _cases(1)[0]
    a = recommend_action(case, cost_model=CostModel())
    b = recommend_action(case, cost_model=CostModel(contest_effort_inr=100))
    if isinstance(a.expected_value_paise, int):
        assert b.expected_value_paise == a.expected_value_paise - 10_000


def test_invalid_amount_forces_review_without_estimate() -> None:
    case = _cases(1)[0]
    case.dispute.amount = 0
    rec = recommend_action(case)
    assert rec.decision == ContestDecision.UNCERTAIN
    assert rec.expected_value_paise == "n/a"
    assert rec.preselect_action is None and rec.requires_human_review


def test_probabilities_are_flagged_experimental() -> None:
    rec = recommend_action(_cases(1)[0])
    assert rec.p_win_status == "experimental_uncalibrated"
    assert rec.value_status == "simulated_assumptions"


def test_high_value_threshold_forces_review(tmp_path: Path) -> None:
    case = _cases(1)[0]
    cfg = yaml.safe_load(Path("src/disputepilot/core/recommend.yaml").read_text(encoding="utf-8"))
    cfg["high_value_review_threshold_paise"] = 1
    path = tmp_path / "hv.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    rec = recommend_action(case, config_path=path)
    if rec.decision != ContestDecision.UNCERTAIN:
        assert rec.preselect_action is None and rec.requires_human_review


def test_missing_evidence_never_preselects_and_escalates() -> None:
    for case in _cases(40):
        case.dispute.evidence.shipping_proof = []
        rec = recommend_action(case)
        if rec.decision == ContestDecision.NEEDS_EVIDENCE:
            from disputepilot.evals.runner import _bucket

            assert rec.preselect_action is None
            assert _bucket(rec) == "escalate"
            return
    pytest.skip("no case in fixtures required shipping proof")


# ---------------------------------------------------- classifier metric fixes


def test_unknown_ground_truth_label_is_not_silently_mapped_to_other() -> None:
    case = _cases(1)[0]
    case.ground_truth.reason_class = "totally_made_up"  # type: ignore[assignment]
    with pytest.raises(ValueError, match="not a supported ReasonClass"):
        evaluate_reason_classifier([case])


def test_classifier_reports_confusion_matrix_and_abstention() -> None:
    metrics = evaluate_reason_classifier(_cases(10))
    assert {"confusion_matrix", "coverage", "abstained_unclassified"} <= set(metrics)
    assert sum(sum(v.values()) for v in metrics["confusion_matrix"].values()) == 10


# ------------------------------------------------------ probability metrics


def test_brier_logloss_known_values() -> None:
    pairs = [(1.0, True), (0.0, False)]
    assert brier_score(pairs) == 0.0
    assert brier_score([(0.5, True), (0.5, False)]) == 0.25
    assert log_loss([(0.5, True)]) == pytest.approx(0.6931, abs=1e-4)
    assert base_rate_brier([(0.9, True), (0.1, False)]) == 0.25
    assert brier_score([]) is None


# ------------------------------------------------------------------- splits


def test_split_is_deterministic_disjoint_and_complete() -> None:
    from disputepilot.evals.splits import leakage_report, three_way_split

    cases = _cases(30)
    a = three_way_split(cases, seed=7)
    b = three_way_split(list(reversed(cases)), seed=7)
    assert {k: [c.case_id for c in v] for k, v in a.items()} == {
        k: [c.case_id for c in v] for k, v in b.items()
    }
    rep = leakage_report(a)
    assert rep["case_id_overlap"] == [] and rep["total"] == len(cases)


def test_group_aware_split_has_no_reason_text_leakage() -> None:
    from disputepilot.evals.runner import _load_cases_from_dir
    from disputepilot.evals.splits import leakage_report, three_way_split

    for d in ("data/cases", "data/cases_messy"):
        rep = leakage_report(three_way_split(_load_cases_from_dir(d), seed=42))
        assert rep["reason_text_shared_across_splits"] == 0
        assert rep["case_id_overlap"] == []
