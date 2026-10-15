"""Tests for the DisputePilot empirical evaluation harness."""

from pathlib import Path

from disputepilot.evals.runner import run_evaluation


def test_evaluation_runner_subset(tmp_path: Path) -> None:
    """Verify that the evaluation harness runs cleanly and generates report and results."""
    cases_dir = Path("data/cases")
    drafts_dir = tmp_path / "drafts"
    output_dir = tmp_path / "evals"

    results = run_evaluation(
        cases_dir=cases_dir,
        drafts_dir=drafts_dir,
        output_dir=output_dir,
        max_cases=10,
    )

    # 1. Output files created
    assert (output_dir / "results.json").exists()
    assert (output_dir / "report.md").exists()

    # 2. Check structure of returned metrics
    assert results["cases_evaluated"] == 10
    assert "reason_classifier" in results
    assert "macro_f1" in results["reason_classifier"]
    assert 0.0 <= results["reason_classifier"]["macro_f1"] <= 1.0

    # 3. Extraction & Evidence
    assert "extraction_accuracy" in results
    assert 0.0 <= results["extraction_accuracy"] <= 1.0
    assert "evidence_agent" in results
    assert "missing_recall" in results["evidence_agent"]

    # 4. Zero fabricated claims non-negotiable guarantee
    assert results["draft_faithfulness"]["fabricated_claims_in_clean_drafts"] == 0

    # 5. Adversarial safety
    assert "adversarial_safety" in results
    assert results["adversarial_safety"]["card_numbers_leaked"] == 0

    # 6. Recommendation and Calibration
    assert "recommendation_quality" in results
    assert "calibration_bins" in results["recommendation_quality"]
    assert len(results["recommendation_quality"]["calibration_bins"]) == 5

    # 7. Financial recovery metrics
    fin = results["financial_value_recovery_inr"]
    assert "disputepilot_policy_inr" in fin
    assert "contest_everything_inr" in fin
    assert "accept_everything_inr" in fin
    assert fin["accept_everything_inr"] == 0.0

    # 8. Report content contains disclaimer
    report_content = (output_dir / "report.md").read_text(encoding="utf-8")
    assert "Synthetic Data Notice" in report_content
    assert "Reason Code Classification" in report_content
    assert "Financial Value Recovery Analysis" in report_content


# ==============================================================================
# Quota-Aware & Budget-Limited Real LLM Eval Tests (Offline)
# ==============================================================================

def test_real_llm_eval_offline_budget_limit(tmp_path: Path) -> None:
    """Runner prints estimated calls and refuses to proceed past --max-calls limit."""
    from typing import Any

    from disputepilot.evals.runner import _load_cases_from_dir, run_real_llm_eval

    cases = _load_cases_from_dir("data/cases_messy", max_cases=5)
    log_file = tmp_path / "real_llm_outputs.jsonl"

    class FailingClient:
        def generate_json(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            raise AssertionError("Client should never be invoked when budget limit is exceeded!")

    # Target requires > 0 calls, but limit is 0
    res = run_real_llm_eval(
        messy_cases=cases,
        outputs_log=log_file,
        n=5,
        max_calls=0,
        stage="classification",
        custom_client=FailingClient(),
    )

    assert res["classification"]["status"] == "NOT RUN"
    assert res["classification"]["completed_k"] == 0
    assert res["status"] == "NOT RUN"


def test_real_llm_eval_offline_daily_quota_stop(tmp_path: Path) -> None:
    """Per-day quota error stops run immediately with no retries and records partial progress."""
    from typing import Any

    from disputepilot.evals.runner import _load_cases_from_dir, run_real_llm_eval
    from disputepilot.extraction.llm import GeminiDailyQuotaError

    cases = _load_cases_from_dir("data/cases_messy", max_cases=10)
    log_file = tmp_path / "real_llm_outputs.jsonl"

    class DailyQuotaMockClient:
        def __init__(self) -> None:
            self.call_count = 0

        def generate_json(
            self,
            system: str,
            user: str,
            json_schema: Any,
            case_id: str | None = None,
            stage: str | None = None,
            **kwargs: Any,
        ) -> dict[str, Any]:
            self.call_count += 1
            if self.call_count > 1:
                # Raise daily quota error on call 2
                raise GeminiDailyQuotaError("ResourceExhausted: GenerateRequestsPerDay limit exceeded")
            return {
                "reason_class": "item_not_received",
                "confidence": 0.95,
                "quote": "parcel gayab",
            }

    mock_client = DailyQuotaMockClient()
    res = run_real_llm_eval(
        messy_cases=cases,
        outputs_log=log_file,
        n=5,
        max_calls=20,
        stage="classification",
        custom_client=mock_client,
    )

    # 1. Stopped by daily quota
    assert res["stopped_by_quota"] is True
    assert mock_client.call_count == 2  # Attempted 1 (succeeded), attempted 2 (failed), stopped immediately!

    # 2. Status is explicitly labelled PARTIAL with k of n and stopped by quota
    cls_status = res["classification"]["status"]
    assert "PARTIAL:" in cls_status
    assert "stopped by quota" in cls_status
    assert res["classification"]["completed_k"] == 1
    assert res["classification"]["accuracy"] is not None

    # 3. Overall status is never presented as full run
    assert "PARTIAL" in res["status"]
    assert "stopped by quota" in res["status"]


def test_real_llm_eval_offline_checkpoint_skip(tmp_path: Path) -> None:
    """Completed cases logged to real_llm_outputs.jsonl are skipped on rerun."""
    import json
    from typing import Any

    from disputepilot.evals.runner import _load_cases_from_dir, run_real_llm_eval

    cases = _load_cases_from_dir("data/cases_messy", max_cases=5)
    log_file = tmp_path / "real_llm_outputs.jsonl"

    unclassified_cases = [c for c in cases if c.ground_truth.reason_class != "not_as_described"]
    first_case = unclassified_cases[0]

    # Pre-populate checkpoint log with completion for first_case
    checkpoint_entry = {
        "timestamp": 123456789.0,
        "case_id": first_case.case_id,
        "stage": "classification",
        "status": "completed",
        "parsed_response": {
            "reason_class": first_case.ground_truth.reason_class,
            "confidence": 0.99,
            "quote": "verified",
        },
    }
    log_file.write_text(json.dumps(checkpoint_entry) + "\n", encoding="utf-8")

    class TrackerClient:
        def __init__(self) -> None:
            self.invoked_cases: list[str] = []

        def generate_json(
            self,
            system: str,
            user: str,
            json_schema: Any,
            case_id: str | None = None,
            stage: str | None = None,
            **kwargs: Any,
        ) -> dict[str, Any]:
            if case_id:
                self.invoked_cases.append(case_id)
            return {
                "reason_class": "other",
                "confidence": 0.8,
                "quote": "test",
            }

    tracker = TrackerClient()
    res = run_real_llm_eval(
        messy_cases=unclassified_cases[:2],
        outputs_log=log_file,
        n=2,
        max_calls=10,
        stage="classification",
        custom_client=tracker,
    )

    # First case was loaded from checkpoint, NOT called on client!
    assert first_case.case_id not in tracker.invoked_cases
    assert res["classification"]["completed_k"] >= 1


def test_real_llm_eval_offline_not_run_when_nothing_completed(tmp_path: Path) -> None:
    """If run stops before anything completes, report states NOT RUN."""
    from typing import Any

    from disputepilot.evals.runner import _load_cases_from_dir, run_real_llm_eval
    from disputepilot.extraction.llm import GeminiDailyQuotaError

    cases = _load_cases_from_dir("data/cases_messy", max_cases=5)
    log_file = tmp_path / "real_llm_outputs.jsonl"

    class InstantFailClient:
        def generate_json(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            raise GeminiDailyQuotaError("PerDay quota exceeded at call 1")

    res = run_real_llm_eval(
        messy_cases=cases,
        outputs_log=log_file,
        n=3,
        max_calls=10,
        stage="classification",
        custom_client=InstantFailClient(),
    )

    assert res["classification"]["status"] == "NOT RUN"
    assert res["classification"]["completed_k"] == 0
    assert res["status"] == "NOT RUN"


def test_score_real_llm_records_matching_and_confidence_stats(tmp_path: Path) -> None:
    """Test offline scoring of real-LLM records by case_id with confidence distribution and misses."""
    import json

    from disputepilot.evals.runner import _load_cases_from_dir, score_real_llm_records

    cases = _load_cases_from_dir("data/cases_messy", max_cases=5)
    case1, case2, case3 = cases[0], cases[1], cases[2]

    log_file = tmp_path / "real_llm_outputs.jsonl"
    entries = [
        # Correct answer with 0.95 confidence
        {
            "case_id": case1.case_id,
            "stage": "classification",
            "parsed_response": {
                "reason_class": case1.ground_truth.reason_class.value,
                "confidence": 0.95,
            },
        },
        # Misclassification with 0.40 confidence (below threshold)
        {
            "case_id": case2.case_id,
            "stage": "classification",
            "parsed_response": {
                "reason_class": "unauthorised" if case2.ground_truth.reason_class.value != "unauthorised" else "duplicate_charge",
                "confidence": 0.40,
            },
        },
        # Correct answer with 1.00 confidence
        {
            "case_id": case3.case_id,
            "stage": "classification",
            "parsed_response": {
                "reason_class": case3.ground_truth.reason_class.value,
                "confidence": 1.0,
            },
        },
    ]
    log_file.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")

    scored = score_real_llm_records(log_file, cases)

    # Scored records: k=3, 2 correct, 1 miss
    cls_metrics = scored["classification"]
    assert cls_metrics["completed_k"] == 3
    assert cls_metrics["correct_count"] == 2
    assert cls_metrics["accuracy"] == round(2 / 3, 4)

    # Misses list
    assert len(cls_metrics["misses"]) == 1
    miss = cls_metrics["misses"][0]
    assert miss["case_id"] == case2.case_id
    assert miss["true_label"] == case2.ground_truth.reason_class.value
    assert miss["confidence"] == 0.40

    # Confidence distribution & below 0.6 threshold count
    conf_dist = cls_metrics["confidence_distribution"]
    assert conf_dist[1.0] == 1
    assert conf_dist[0.95] == 1
    assert conf_dist[0.4] == 1
    assert cls_metrics["below_threshold_count"] == 1

    # Status
    assert scored["status"] == "PARTIAL (classification 3 cases, extraction NOT RUN)"


def test_score_real_llm_records_backfill_older_records(tmp_path: Path) -> None:
    """Test that older records without case_id are matched by reason text and case_id is backfilled into file."""
    import json

    from disputepilot.evals.runner import _load_cases_from_dir, score_real_llm_records

    cases = _load_cases_from_dir("data/cases_messy", max_cases=5)
    target_case = cases[0]
    reason_text = target_case.dispute.reason_code

    log_file = tmp_path / "real_llm_outputs.jsonl"
    # Older record without case_id, stage, or status
    older_entry = {
        "timestamp": 123456789.0,
        "prompt": {
            "system": "Classify",
            "user": f"Dispute reason text to classify:\n<<<DISPUTE_REASON>>>\n{reason_text}\n<<<END_DISPUTE_REASON>>>",
        },
        "parsed_response": {
            "reason_class": target_case.ground_truth.reason_class.value,
            "confidence": 0.9,
        },
    }
    log_file.write_text(json.dumps(older_entry) + "\n", encoding="utf-8")

    scored = score_real_llm_records(log_file, cases)

    assert scored["classification"]["completed_k"] == 1
    assert scored["classification"]["correct_count"] == 1
    assert scored["classification"]["accuracy"] == 1.0

    # Verify backfill into file
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    updated_entry = json.loads(lines[0])
    assert updated_entry["case_id"] == target_case.case_id
    assert updated_entry["stage"] == "classification"
    assert updated_entry["status"] == "completed"

