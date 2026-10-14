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
