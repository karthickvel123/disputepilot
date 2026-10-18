"""Adversarial eval: dataset integrity, metric arithmetic, and a no-regression ratchet.

The ratchet pins today's measured failures (evals/adversarial/baseline.json). It does NOT claim the
classifier is good - it prevents it getting worse and makes improvements show up as lowered numbers.
"""

import hashlib
import json
from pathlib import Path

from disputepilot.core.reasons import classify_reason
from disputepilot.evals.adversarial import (
    ABSTAIN,
    evaluate_injection,
    evaluate_reasons,
    evaluate_regression,
    load_cases,
)
from disputepilot.safety.untrusted import detect_injection

CLASSES = {"item_not_received", "not_as_described", "unauthorised", "duplicate_charge",
           "subscription_cancelled", "refund_not_received", "other"}
BASELINE = json.loads(Path("evals/adversarial/baseline.json").read_text(encoding="utf-8"))


def _rules(text):
    m = classify_reason(text)
    return m.reason_class.value, m.needs_review


def test_dataset_is_well_formed() -> None:
    cases = load_cases()
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids))
    for c in cases:
        assert c["suite"] in {"reason", "injection"}
        if c["suite"] == "reason":
            assert c["ideal"] == "abstain" or c["ideal"] in CLASSES
            assert set(c["acceptable"]) <= CLASSES
            if c["ideal"] != "abstain":
                assert c["ideal"] in c["acceptable"]
        else:
            assert isinstance(c["expect_flag"], bool)


def test_metric_arithmetic_with_a_stub_classifier() -> None:
    cases = [
        {"id": "a", "suite": "reason", "category": "x", "text": "t1", "ideal": "duplicate_charge", "acceptable": ["duplicate_charge"]},
        {"id": "b", "suite": "reason", "category": "x", "text": "t2", "ideal": "duplicate_charge", "acceptable": ["duplicate_charge"]},
        {"id": "c", "suite": "reason", "category": "x", "text": "t3", "ideal": "duplicate_charge", "acceptable": ["duplicate_charge"]},
        {"id": "d", "suite": "reason", "category": "x", "text": "boom", "ideal": "duplicate_charge", "acceptable": ["duplicate_charge"]},
    ]
    answers = {"t1": ("duplicate_charge", False), "t2": ("other", False), "t3": (ABSTAIN, True)}

    def stub(text):
        if text == "boom":
            raise RuntimeError("x")
        return answers[text]

    r = evaluate_reasons(cases, stub)["x"]
    assert (r["n"], r["coverage"], r["accuracy_answered"], r["wrong_answer_count"], r["abstain"], r["crashes"]) == (4, 0.5, 0.5, 1, 0.25, 1)


def test_no_crashes_on_any_input() -> None:
    res = evaluate_reasons(load_cases(), _rules)
    assert sum(r["crashes"] for r in res.values()) == 0


def test_canonical_phrasing_stays_correct() -> None:
    control = evaluate_reasons(load_cases(), _rules)["control"]
    assert control["wrong_answer_count"] == 0 and control["accuracy_answered"] == 1.0


def test_confident_wrong_answers_do_not_exceed_baseline() -> None:
    res = evaluate_reasons(load_cases(), _rules)
    for cat, limit in BASELINE["reason_wrong_answer_count"].items():
        assert res[cat]["wrong_answer_count"] <= limit, f"{cat}: {res[cat]['wrong_answer_count']} > baseline {limit}"


def test_ambiguous_cases_are_not_answered_more_often_than_baseline() -> None:
    res = evaluate_reasons(load_cases(), _rules)
    assert res["ambiguous"]["ambiguous_answered"] <= BASELINE["reason_ambiguous_answered_max"]


def test_injection_detector_does_not_regress() -> None:
    res = evaluate_injection(load_cases(), detect_injection)
    assert res["canonical"]["flag_rate"] == 1.0
    assert len(res["evasive"]["missed"]) <= BASELINE["injection_evasive_missed"]
    assert len(res["benign"]["false_positives"]) <= BASELINE["injection_benign_false_positives"]


def test_baseline_cases_are_unchanged() -> None:
    """The 104 original cases and their expected outcomes must not be edited to make results look better."""
    digest = hashlib.sha256(Path("evals/adversarial/cases.jsonl").read_bytes()).hexdigest()
    assert digest == BASELINE["cases_sha256"]


def test_every_regression_case_passes_its_requirement() -> None:
    cases = load_cases(Path("evals/adversarial/regression_cases.jsonl"))
    assert {c["fix"] for c in cases} >= {"whole_word", "negation", "longest_match", "conflict", "code_mixed", "inflection", "multi_issue", "spelling_variant", "no_regression"}
    for fix, r in evaluate_regression(cases, _rules).items():
        assert r["failures"] == [], f"{fix}: {r['failures']}"


def test_keyword_traps_have_no_confident_wrong_answers() -> None:
    assert evaluate_reasons(load_cases(), _rules)["keyword_trap"]["wrong_answer_count"] == 0
