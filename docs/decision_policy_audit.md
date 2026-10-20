# Decision Policy Audit (Phases 1–2, 4–7)

All money figures are **simulated**. Outcomes ("winnable") come from the simulator rule
`sim/rules.py::evaluate_winnability`, not from observed merchant or bank results.

## Baseline reproduced (before any edit)
| Command | Result |
|---|---|
| `uv sync && uv run pytest -q` | 214 passed |
| `uv run python -m disputepilot.evals.runner --output-dir <tmp>` | clean holdout (n=45): contest-all ₹188,778, policy ₹116,783, uplift −₹71,995; messy rules-only (n=100): policy ₹22,499, uplift −₹132,373; messy rules-only accuracy 6% |

README discrepancy found: it listed messy figures ₹26,999 / −₹127,873 / macro-F1 9.33%; the rerun gives
₹22,499 / −₹132,373 / 9.80%. README corrected.

## Pipeline trace
Ingest (`safety/ingest.py`, card scan, injection fencing) → extraction (`extraction/`) → cross-checks →
classification (`core/reasons.py`, keyword rules, optional LLM) → evidence audit (`core/evidence.py`) →
heuristic `p_win` and EV (`core/recommend.py`) → decision → human approval token bound to payload hash
(`razorpay/approval.py`) → gateway (`razorpay/gateway.py`) → audit log (`pipeline/audit.py`).

## Root cause of negative uplift (established)
| # | Finding | Class |
|---|---|---|
| 1 | With fee = effort = ₹0, contesting an unwinnable case is free, so contest-all weakly dominates every policy. Oracle uplift = 0 at zero cost (test `test_zero_cost_makes_contest_all_unbeatable`). Negative uplift was guaranteed by the assumptions. | Unrealistic assumption |
| 2 | `fee_per_dispute_paise` existed in `recommend.yaml` but was **never read**; EV was `p·amount − effort`. | Confirmed bug (fixed) |
| 3 | Runner counted `uncertain` / `needs_evidence` as silent accepts with no review cost; escalations were invisible. | Confirmed accounting gap (fixed) |
| 4 | Fee was charged in the runner only on losses, while the recommender ignored it; no shared definition. | Inconsistency (fixed: `core/economics.py`) |
| 5 | `p_win < 0.35` forces *accept* even when EV > 0, so at zero cost the policy forgoes positive-EV contests. | Policy design, **not changed** (would be threshold tuning) |
| 6 | Win labels are a deterministic function of the same evidence the heuristic reads, so accuracy/Brier on the sim are circular. | Missing evidence |

## Classification (6% rules-only)
Genuine limitation of keyword rules on Hinglish/messy text: 94 of 100 cases abstain (`unclassified`); 6 correct.
Not a label-mapping bug in the current code. Latent bug fixed: unknown ground-truth labels silently became
`other`; they now raise. The earlier 17%→6% drop is explained by the removed silent `other` fallback (README).
Added to metrics: confusion matrix, abstention count, coverage, accuracy on answered.
The fake-LLM figure (85%) uses generator vocabulary and is a wiring check only. No real LLM was run here
(no API key); not fabricated.

## Splits and leakage
Existing runner: 70/30 random split only; no validation set. Added `evals/splits.py` (seeded, stratified
dev/validation/held-out). Leakage check (seed 42): case-ID overlap 0, but **text leakage is high**: clean set has
27 distinct reason texts over 150 cases (25 appear in >1 split); messy 46 distinct over 100 (24 shared). Templated
data means held-out accuracy overstates generalisation.

## Win probabilities
Heuristic weights are hand-set; no labelled real outcomes exist. `Recommendation` now carries
`p_win_status="experimental_uncalibrated"`, `value_status="simulated_assumptions"`, `requires_human_review`.
Brier/log-loss added to evals: clean holdout Brier 0.0948 vs base-rate 0.24 (circular labels, not evidence of
real calibration); messy rules+fake-LLM Brier 0.2269 **worse than** base rate 0.2034.

## Safeguards added (no approval/security weakening)
Invalid or non-positive amount → `UNCERTAIN`, no estimate. Optional `high_value_review_threshold_paise`
(default off). Existing: missing required evidence → `needs_evidence`; cross-check flags widen the interval and
force review; unclassified → `UNCERTAIN`.

## Security / integration (Phase 7)
Existing tests re-run: `test_razorpay`, `test_security_concurrency`, `test_webhook_security`,
`test_auth_security_hardening`, `test_adversarial_eval`, `test_safety` → 60 passed (token bound to payload hash,
replay, concurrency, webhook signature, injection fencing, card scanning). **Unverified:** live Razorpay test-mode
calls (no credentials), document-upload and accept endpoints against the real API, real timeouts/idempotency.
No new endpoints were invented.
