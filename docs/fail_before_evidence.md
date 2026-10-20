# Fail-before / pass-after evidence

Method: `tests/test_economics.py` (22 tests) was run with the original `core/recommend.py`,
`core/recommend.yaml` and `evals/runner.py` swapped in, then with the fixed versions
(`uv run pytest tests/test_economics.py -q -rA`).

| Code | Passed | Failed |
|---|---|---|
| Original | 14 | 8 |
| Fixed | 22 | 0 |

Fail on original code (each guards a confirmed defect):
`test_configured_fee_now_reduces_expected_value` (fee ignored in EV),
`test_cost_model_overrides_effort`, `test_invalid_amount_forces_review_without_estimate`,
`test_probabilities_are_flagged_experimental`, `test_high_value_threshold_forces_review`,
`test_missing_evidence_never_preselects_and_escalates` (escalation accounting),
`test_unknown_ground_truth_label_is_not_silently_mapped_to_other`,
`test_classifier_reports_confusion_matrix_and_abstention`.

The other 14 test the new `core/economics.py` and `evals/splits.py`, which do not exist in the original, so they
document intended behaviour rather than a regression.
