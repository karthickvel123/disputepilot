# Decision Policy Results (Phase 9)

## Summary
- **Uplift vs contest-all is negative or inconclusive. It is not positive.** The original negative figure was
  mostly a consequence of zero-cost assumptions (contest-all cannot be beaten at zero cost, even by a perfect
  oracle). Under illustrative non-zero costs the heuristic still trails contest-all on the clean holdout.
  Thresholds were **not** tuned.
- Real bugs fixed: configured dispute fee ignored in EV; escalations hidden as accepts; silent `other`
  label fallback in the classifier metric; stale README figures.
- Nothing here is observed revenue. Labels are simulator-derived; costs below are **illustrative assumptions**,
  not Razorpay fee schedules.
- Tests: run `uv run pytest -q` locally for the current result.

## 1. Original baseline (same commands, reproduced)
| Slice | n | Contest-all ₹ | Policy ₹ | Uplift ₹ |
|---|---|---|---|---|
| Clean holdout | 45 | 188,778 | 116,783 | −71,995 |
| Messy, rules-only | 100 | 154,872 | 22,499 | −132,373 |
| Messy, rules + fake LLM | 100 | 154,872 | 135,678 | −19,194 |

## 2–3. Changes and files
`core/economics.py` (new: cost model, EV, policy comparison, bootstrap CI, break-even, Brier/log-loss) ·
`core/recommend.py` + `recommend.yaml` (EV via shared model, fee/review/high-value config, status fields,
invalid-amount guard) · `evals/runner.py` (policy comparison per cost scenario, confusion matrix, abstention,
Brier, no silent `other`) · `evals/splits.py` (new) · `tests/test_economics.py` (new, 21 tests) ·
`README.md` (stale numbers) · `docs/` (these reports). Legacy result keys are unchanged, so original metrics
reproduce exactly (zero-cost decisions are identical).

## 4–5. Policy comparison, identical cases (clean holdout n=45, simulated outcomes)
Net ₹ per scenario; C/A/E = contested/accepted/escalated. "Escalated" assumed resolved by a human as *accept*
(conservative); resolving as *contest* is in `evals/results.json`.

| Policy | C/A/E | Zero cost | Effort ₹200, review ₹100 | + fee ₹500 on loss |
|---|---|---|---|---|
| Contest-all | 45/0/0 | 188,778 | 179,778 | 166,278 |
| Accept-all | 0/45/0 | 0 | 0 | 0 |
| Heuristic, decision as-is | 17/28/0 | 116,783 | 113,383 | 112,383 |
| Heuristic with escalation | 9/1/35 | 78,388 | 73,088 | 73,088 |
| Oracle (upper bound, not deployable) | 18/27/0 | 188,778 | 185,178 | 185,178 |

Heuristic-as-is uplift vs contest-all: −71,995 / −66,395 / −53,895 (per-case-mean 95% bootstrap CIs include 0
only in the two non-zero-cost scenarios; totals in `results.json`). Break-even contest effort where
heuristic-as-is equals contest-all: about **₹2,571 per contest** (zero other costs). Below that, contesting
everything wins on this data. Messy set: rules-only escalates 100/100 (94% abstain), so it is just a review
queue; rules+fake-LLM as-is is −₹19,194 at zero cost, −₹7,594 and +₹18,406 (CI includes 0) in the other
scenarios, so **inconclusive** and tied to the fake LLM.

## 6. Classification (identical cases, `evals/results.json`)
Clean holdout: accuracy/macro-F1 100%, but templated text (27 distinct reasons/150 cases) makes this
in-distribution. Messy rules-only: accuracy 6%, macro-F1 9.8%, abstention 94, coverage 6%. Full per-class
tables and confusion matrices are in `results.json` (`reason_classifier`). Real-LLM comparison **not run**
(no API key); the earlier 15/16 Gemini result is not evidence of production reliability.

## 7. Uncertainty and limitations
Labels are simulator rules; the heuristic reads the same evidence, so results are circular. Small n
(45/100); CIs are bootstrap over cases (seed 42), per-case means. Cost scenarios are invented for sensitivity,
not measured. No validation split is used by the runner's headline numbers (`splits.py` is available).
Brier: holdout 0.0948 vs base-rate 0.24 (circular); messy+fake-LLM 0.2269 vs 0.2034 (worse than base rate).

## 8. Security/integration actually performed
Existing suites re-run: 60 passed (approval-hash binding, replay, concurrency, webhook signature, injection
fencing, card scanning). Not performed: any live Razorpay test-mode call.

## 9–10. Unverified / blockers
Unverified: real Razorpay dispute/upload/accept behaviour, timeouts, idempotency on the live API, real LLM
accuracy. Not done: expanded labelled classification set with adversarial/malformed examples, a
validation-based threshold review, a pytest per-defect fail-before demonstration (new tests fail on the original
code only at collection because the new symbols do not exist).
**Next steps for you:** (1) enter real dispute fee, review and labour costs in `recommend.yaml`;
(2) export labelled historical outcomes to calibrate `p_win` (Brier/log-loss now computed); (3) run
`uv run python -m disputepilot.evals.runner --real-llm` with your key; (4) run `scripts/smoke_razorpay.py` in test mode.

## Update: leakage, rules experiment, fail-before
**Leakage fixed.** `three_way_split` is now group-aware: identical normalised reason texts stay in one split.
Seed 42: clean 77/34/39 and messy 55/15/30 (dev/validation/held-out); case-ID overlap 0, shared reason texts 0
(was 25 and 24). Test: `test_group_aware_split_has_no_reason_text_leakage`.

**Rules-coverage experiment (rules-only, messy set, group-aware split).** Baseline: dev 10.9%, validation 0%,
held-out 0% accuracy, 0 confidently wrong. I added 40 English/typo keyword phrases drawn from dev only. Dev rose
to 47.3% but validation stayed at 0/15, so the gain did not transfer. Diagnosis: 11/15 validation and 13/30
held-out cases are code-mixed text, which the rules skip by design (safer than guessing), and the rest have
phrasing no keyword anticipates. **I reverted the keywords** because there is no validated benefit and unvalidated
rules add false-positive risk. The held-out split was not used for tuning. Only the LLM fallback can address
code-mixed text; it needs your API key (`--real-llm`). Reproduce with `scripts/eval_rules_splits.py`.

**Fail-before evidence:** see `docs/fail_before_evidence.md` (8 of 22 new tests fail on the original code, all pass now).
