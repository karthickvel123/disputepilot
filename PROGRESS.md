# DisputePilot Implementation Progress

DisputePilot helps Razorpay merchants respond to payment disputes (chargebacks).
This document tracks implementation progress across all development phases.

## Phase Overview
- [x] Phase A: Document extraction (`src/disputepilot/extraction/`)
- [x] Phase B: Evidence agent (`src/disputepilot/agent/`)
- [x] Phase C: Rebuttal drafter and verifier (`src/disputepilot/drafting/`)
- [x] Phase D: Recommendation (`src/disputepilot/core/recommend.py`)
- [x] Phase E: Pipeline, approval and audit (`src/disputepilot/pipeline/`)
- [ ] Phase F: Web app (`src/disputepilot/web/`)
- [ ] Phase G: Evaluation (`src/disputepilot/evals/`)
- [ ] Phase H: Documentation (`README.md`, `docs/ARCHITECTURE.md`, `DEMO.md`)

---

### Phase A: Document Extraction
- **Files Added**:
  - `src/disputepilot/extraction/llm.py`: `LLMClient` protocol, `GeminiClient` (using `google-genai`), and `FakeLLMClient` for deterministic offline testing.
  - `src/disputepilot/extraction/schemas.py`: Strict Pydantic models (`extra="forbid"`) for `DeliveryProof`, `Invoice`, `ChatTranscript`, `CancellationPolicy` with `ExtractedField[T]` holding value, verbatim source quote, and confidence.
  - `src/disputepilot/extraction/extractor.py`: Pipeline running safe document ingestion -> untrusted boundary wrapping -> structured LLM extraction -> schema validation -> verbatim source quote verification (dropping unquoted/fabricated fields).
  - `src/disputepilot/extraction/cross_checks.py`: Deterministic discrepancy audits with severity tiers: delivery date after dispute date, invoice amount vs dispute amount mismatch, delivery address vs shipping address token overlap, and unmentioned refund records.
  - `src/disputepilot/extraction/__init__.py`: Public exports.
  - `tests/test_extraction.py`: 7 tests covering extra key validation, quote dropping, prompt injection resilience, and each cross-check flag.
- **Tests Added**: 7 tests in `test_extraction.py` (total suite: 53 tests passing).
- **Assumed / Not Done**:
  - Live Gemini API calls require `LLM_API_KEY` or `GEMINI_API_KEY`; in default/test mode `FakeLLMClient` provides deterministic offline responses.
  - Address comparison uses token set intersection (Jaccard similarity threshold 0.5) with basic stopword filtering.

---

### Phase B: Evidence Agent
- **Files Added**:
  - `src/disputepilot/agent/tools.py`: Read-only tool registry (`ReadOnlyToolRegistry`) strictly enforcing `ALLOWLISTED_TOOLS` (`get_dispute`, `get_order`, `get_refund`, `list_documents`, `get_extracted_doc`). Any other tool name or write action raises `PermissionError`.
  - `src/disputepilot/agent/models.py`: Pydantic data model `EvidenceReport` containing dispute id, reason class, document categories with average confidences, present/missing/partial evidence statuses, cross-check discrepancy flags, actionable specific asks, and tool call audit trail.
  - `src/disputepilot/agent/orchestrator.py`: Bounded orchestrator `EvidenceAgent` with step limits, deterministic fallback classification, cross-check evaluation, and tailored merchant requests for missing items.
  - `src/disputepilot/agent/__init__.py`: Public exports.
  - `tests/test_agent.py`: 4 tests verifying malicious document tool immunity, step limit halting, tailored merchant missing asks, and full end-to-end evidence audit.
- **Tests Added**: 4 tests in `test_agent.py` (total suite: 57 tests passing).
- **Assumed / Not Done**:
  - Agent uses deterministic mapping for known doc types with LLM classification fallback.
---

### Phase C: Rebuttal Drafter and Verifier
- **Files Added**:
  - `src/disputepilot/drafting/facts.py`: Data models `Fact` and `FactSet`, with `build_fact_set()` extracting verified facts and entity references from case API records (dispute, order, refund) and verified surviving document fields.
  - `src/disputepilot/drafting/drafter.py`: `RebuttalDraft`, `DraftSentence`, and `RebuttalDrafter` generating four-section structured rebuttals (Summary, Timeline, Evidence Submitted, Conclusion) with mandatory citations and safe fallback.
  - `src/disputepilot/drafting/verifier.py`: Deterministic claim and entity verifier (`verify_sentence`, `verify_rebuttal`) that audits every cited fact ID, checks every number, date, and domain ID against cited facts, strips ungrounded or fabricated sentences, and generates a detailed `VerifierReport`. Zero fabricated claims survive.
  - `src/disputepilot/drafting/__init__.py`: Public exports.
  - `tests/test_drafting.py`: 6 tests covering clean drafts, stripping invented delivery dates, stripping sentences with missing citations, invalid citations, fabricated numbers/AWBs, and end-to-end drafting from case facts.
- **Tests Added**: 6 tests in `test_drafting.py` (total suite: 63 tests passing).
- **Assumed / Not Done**:
  - Verification extracts ISO and text dates, alphanumeric IDs, and numbers/amounts, checking presence against normalized text and entity representations of cited facts.

---

### Phase D: Recommendation Engine
- **Files Added**:
  - `src/disputepilot/core/recommend.yaml`: Transparent heuristic weights for reason-class priors, evidence completeness bonuses/penalties, cross-check penalties, delivery boost, effort cost (paise), and uncertainty thresholds.
  - `src/disputepilot/core/recommend.py`: Heuristic recommendation engine computing `p_win` with uncertainty interval (`p_win_low`, `p_win_high`), expected value (`EV = p_win * amount - effort_cost`), and outputting `ContestDecision` (`CONTEST`, `ACCEPT`, `NEEDS_EVIDENCE`). Preselects nothing when uncertain (0.35–0.55) or when required evidence is missing. Labelled with synthetic data disclaimer.
  - `src/disputepilot/core/__init__.py`: Exported `ContestDecision`, `HEURISTIC_DISCLAIMER`, `Recommendation`, `recommend_action`.
  - `tests/test_recommend.py`: 5 tests covering missing required evidence triggering `NeedsEvidence`, high win rate with positive EV recommending `Contest`, critical discrepancies triggering `Accept`, uncertain band suppressing preselection, and effort cost configuration altering EV.
- **Tests Added**: 5 tests in `test_recommend.py` (total suite: 68 tests passing).
- **Assumed / Not Done**:
  - Baseline uses transparent deterministic heuristic weights calibrated on synthetic data, not a machine learning classifier.

---

### Phase E: Pipeline, Approval, and Audit
- **Files Added / Modified**:
  - `src/disputepilot/razorpay/approval.py`: Extended `ApprovalService` with default 30-minute token TTL (`token_ttl_seconds=1800`), mandatory named human reviewer check, single-use enforcement, and exact payload hash binding.
  - `src/disputepilot/pipeline/audit.py`: Append-only SQLite audit log (`audit_log`) computing cryptographic SHA-256 hash chains across entries (`compute_entry_hash`). Provided `verify_audit_trail()` to detect tampering, modification, or record deletion.
  - `src/disputepilot/pipeline/reminders.py`: Computes merchant response deadline reminders at T-48h, T-24h, and T-12h; persists them in SQLite table `reminders` without sending external network notifications.
  - `src/disputepilot/pipeline/orchestrator.py`: Implemented `process_case(case_id)` pipeline (ingest -> extract -> cross-check -> evidence report -> recommendation -> draft -> verify -> audit log -> reminders -> draft save). Strictly never calls `accept` or `submit`.
  - `src/disputepilot/pipeline/__init__.py`: Public exports.
  - `tests/test_pipeline.py`: 5 tests covering safety guarantees (pipeline never calls accept or submit), expired token rejection, named reviewer requirement, tamper detection in cryptographic audit chain, and reminder persistence.
- **Tests Added**: 5 tests in `test_pipeline.py` (total suite: 73 tests passing).
- **Assumed / Not Done**:
  - Reminders are recorded to SQLite table for inspection; external dispatch (email/Slack/SMS) is deliberately not implemented.

---

### Phase F: Web Application
- **Files Added / Modified**:
  - `src/disputepilot/web/static/style.css`: Clean dark theme styles, responsive cards, typography, badge colors, and citation pills.
  - `src/disputepilot/web/templates/base.html`: Common layout, brand header, navigation, and flash alert containers.
  - `src/disputepilot/web/templates/worklist.html`: Prioritized worklist table displaying case rank, amount, deadline urgency, reason class, recommendation badge, and uncertain status.
  - `src/disputepilot/web/templates/case_detail.html`: Full merchant dispute review console with dispute & order records, evidence checklist, discrepancy warnings, prompt injection alerts, recommendation card, verified citation-grounded draft, verifier report card, and reviewer action forms.
  - `src/disputepilot/web/templates/confirm_submit.html`: Submission review modal displaying exact contest payload JSON and cryptographically bound SHA-256 hash.
  - `src/disputepilot/web/app.py`: FastAPI web app mounting static files, templates, Razorpay webhook (`/webhook/razorpay`), worklist (`GET /`, `GET /cases`), case review (`GET /cases/{case_id}`), save draft (`POST /cases/{case_id}/save-draft`), confirm submission (`GET /cases/{case_id}/confirm-submit`), contest submission (`POST /cases/{case_id}/submit`), dispute acceptance (`POST /cases/{case_id}/accept` with typed amount check), and evidence requests (`POST /cases/{case_id}/needs-evidence`). Zero third-party multipart dependencies (uses standard `urllib.parse`).
  - `src/disputepilot/web/__init__.py`: Public export of `app`.
  - `tests/test_web.py`: 11 tests covering worklist rendering, case detail page, 404 handling, confirm-submit approval token issuance, rejection of submissions without approval token, rejection of tampered payload hashes, successful submission with valid token, typed amount verification on accept, missing reviewer rejection, draft saving, and needs-evidence flagging.
- **Tests Added**: 11 tests in `test_web.py` (total suite: 84 tests passing).
- **Assumed / Not Done**:
  - Web UI runs locally on FastAPI/Uvicorn without external CDN dependencies.

---

### Phase G: Evaluation
- **Files Added / Modified**:
  - `src/disputepilot/evals/runner.py`: Empirical evaluation harness executing end-to-end processing across all 150 simulated dispute cases. Computes reason classifier macro-F1 (100.0%), field extraction accuracy (100.0%), missing evidence recall (99.28%), draft grounding faithfulness (100.0%), zero-hallucination guarantee verification (0 fabricated claims in clean drafts), prompt injection containment rate (100.0%), card number leak audits (0 leaks), decision accuracy vs ground truth winnable (86.0%), calibration curve across 5 probability bins, and financial recovery value analysis (₹467,633 net recovered; 73 unwinnable disputes prevented from contesting).
  - `src/disputepilot/evals/__init__.py`: Public export of `run_evaluation`.
  - `Makefile`: Added `eval: uv run python -m disputepilot.evals.runner` target.
  - `evals/results.json`: Complete machine-readable evaluation metrics across all 150 cases.
  - `evals/report.md`: Markdown summary report with tables, calibration analysis, and synthetic data disclaimer.
  - `tests/test_evals.py`: 1 comprehensive test verifying evaluation harness runs cleanly and produces all metrics.
- **Tests Added**: 1 test in `test_evals.py` (total suite: 85 tests passing).
- **Assumed / Not Done**:
  - Baseline uses heuristic weights calibrated on synthetic data; real LLM runs when `LLM_API_KEY` is supplied.

---

### Phase H: Documentation and Final Polish
- **Files Added / Modified**:
  - `README.md`: Project summary in 3 sentences, 5-command quickstart, Mermaid architecture diagram, safety design matrix covering the 4 core non-negotiables, PCI-DSS compliance specifications, empirical evaluation results summary, production readiness checklist, and prominent synthetic data notice.
  - `docs/ARCHITECTURE.md`: Comprehensive 1-page architectural specification detailing the linear pipeline, dual-gateway abstraction, bounded read-only Evidence Agent, fact-set assembly, deterministic verifier, recommendation math, calibration, and cryptographic tamper-evident audit logging.
  - `DEMO.md`: A 5-minute walkthrough script with exact case IDs and verification steps:
    1. Winnable case with full evidence (`disp_0001_hbrpoi`)
    2. Missing-evidence case (`disp_0002_r3xkxw`)
    3. Adversarial prompt injection neutralization (`disp_0004_9ooaed`)
    4. Sensitive card number redaction (`disp_0008_6hymqc`)
    5. Approval token enforcement & tampered hash rejection (`disp_0001_hbrpoi`)
  - `Makefile`: Configured with `test`, `lint`, `run`, and `eval` targets.
- **Verification**:
  - `uv run pytest`: 85 passing tests (100% pass rate).
  - `uv run ruff check .`: Clean, zero lint errors.
  - `uv run python -m disputepilot.evals.runner`: Clean execution over all 150 simulated cases.
- **Assumed / Not Done**:
---

### Phase I: Honest Evaluation & Hardening
- **Files Added / Modified**:
  - `src/disputepilot/sim/messy.py`: Implemented `MessyCaseGenerator` producing 100 messy dispute cases (`data/cases_messy/`) without reusing canonical templates or `reasons.yaml` keywords (varying dates, typos, mixed Hindi-English phrasing, noisy chat transcripts, and varied addresses).
  - `src/disputepilot/sim/generate.py`: Added `--messy` CLI option.
  - `src/disputepilot/core/recommend.yaml`: Set `effort_cost_paise: 0` and `fee_per_dispute_paise: 0` as configurable defaults.
  - `src/disputepilot/core/recommend.py`: Defaulted fallback effort cost to 0 unless explicitly supplied.
  - `src/disputepilot/pipeline/orchestrator.py`: Exposed `extracted_docs` on `CaseProcessingResult` and fixed `SimGateway` data directory parameter.
  - `src/disputepilot/evals/runner.py`: Refactored evaluation harness:
    1. Splits clean set 70/30 deterministically by seed into Train (70%, n=105) and Hold-out (30%, n=45).
    2. Runs full evaluation separately over `data/cases` (clean) and `data/cases_messy` (messy).
    3. Added `--real-llm` flag to run extraction and drafting with `GeminiClient` on 30 random cases from the messy set (skips with a clear notice when `LLM_API_KEY` is unset).
    4. Added top section "What these numbers do and do not show" to `evals/report.md`, marking circular metrics as "pipeline sanity check, not performance", and labelling all financial figures as "simulated, under assumptions listed here".
    5. Clean and messy results are reported side by side and never averaged.
  - `evals/report.md` & `evals/results.json`: Generated side-by-side metrics across Clean Train, Clean Hold-out, and Messy sets.
  - `README.md`: Added "Limitations" section (typed reviewer name, SQLite, synthetic data only, heuristic recommendation, real LLM/Razorpay paths verified only as reported) and removed all claims of "saving fees" and "protecting dispute ratios".
- **Tests Added / Verified**:
  - `tests/test_evals.py`: Verified evaluation harness runs and produces structured report and results.
  - Full suite: 85 passed in 2.4s.
  - Ruff linter: All checks passed (0 errors).
- **Assumed / Not Done**:
  - `LLM_API_KEY` is not set in the local environment, so the real Gemini LLM path was verified for safe fallback and clear skip messaging as required.

---

### Phase J: Classification Hardening, Extraction Bug Resolution, & Evaluation Integrity
- **1. Reason Classification Hardening (`src/disputepilot/core/reasons.py`)**:
  - First pass strictly uses deterministic rules in `reasons.yaml` (exact dispute code matching and keyword matching).
  - If no rule matches with high confidence, calls `LLMClient.generate_json` with an enum of the 7 standard reason classes plus `"unclassified"`, returning `reason_class`, `confidence` (0.0 to 1.0), and a verbatim `quote`.
  - If the LLM is unavailable (e.g. offline test mode without `LLM_API_KEY`), throws an error, or returns confidence < 0.6 or `"unclassified"`, returns `"unclassified"` with `needs_review=True`.
  - Disallowed silent fallback: never silently defaults to `"other"`. Unknown codes/texts without matching rules strictly return `"unclassified"` with `needs_review=True`.
  - Added unit tests in `tests/test_core.py` covering exact codes, keywords, unknown strings, empty/None strings, LLM success (>= 0.6), LLM low confidence rejection (< 0.6), LLM unclassified response, and LLM exception fallback.

- **2. Recommendation on Unclassified Reasons (`src/disputepilot/core/recommend.py` & UI)**:
  - When the reason is `"unclassified"`, `recommend_action()` immediately returns `ContestDecision.UNCERTAIN` with `is_uncertain=True`, `preselect_action=None`, `p_win=0.0`, `expected_value_paise=0`, and `reasons=["reason could not be classified"]`.
  - Prior probabilities: strictly never applies the `"other"` prior.
  - Web UI: Rendered a prominent warning banner (`id="unclassified-banner"`) on `src/disputepilot/web/templates/case_detail.html` stating that the dispute reason could not be classified, no action has been preselected, and manual merchant review is required.
  - Added unit tests in `tests/test_recommend.py` and `tests/test_web.py`.

- **3. Root Cause Analysis: Clean-Set Field Extraction Drop (100% -> 73.21%)**:
  - **Measurement Change**: In Phase G, "field extraction accuracy" was an artifact: the harness merely checked whether order fields (`order.tracking_number`, `order.amount`, `order.customer_name`) were substrings of the generated rebuttal markdown letter (`draft_md`). Because the rebuttal template systematically injected those order fields into the markdown text, it produced an artificial score of 100.0% without evaluating actual document extraction from attached files.
  - **Specification Error / Bug**: In Phase I, the metric was updated to inspect `res.extracted_docs.surviving_fields` per document type. For `customer_communication`, the test benchmark set `expected_keys = ["customer_sentiment"]`. However, `customer_sentiment` does not exist in `ChatTranscript` (`src/disputepilot/extraction/schemas.py`, which defines `ticket_id`, `customer_name`, `issue_reported`, etc., with `model_config = ConfigDict(extra="forbid")`). Because no chat document could ever extract a non-existent schema field, every customer communication document scored 0/1. On the 45-case clean hold-out set, out of 112 expected field evaluations, exactly 82 passed (billing, shipping, policy) and 30 failed (chat documents missing `customer_sentiment`), yielding $82 / 112 = 73.214\%$ (reported as 73.21%).
  - **Classification**: This was a **measurement change** (evaluating document extracted fields rather than drafted letter substrings) compounded by a **benchmark specification error / bug** (specifying a non-existent schema field), NOT a model or pipeline regression.
  - **Fix Applied**: Updated `expected_keys` in `src/disputepilot/evals/runner.py` for `customer_communication` to universal schema fields `["ticket_id", "customer_name"]`, and aligned `FakeLLMClient` regexes and dispatch headers to match canonical markdown template formatting. Clean-set field extraction accuracy is restored to 100.0%.

- **4. Labeling of FakeLLMClient Metrics**:
  - Every metric generated using `FakeLLMClient` across all summary tables and evaluation sections in `evals/report.md`, `README.md`, and progress logs is explicitly labeled as `"fake regex baseline, not a model result"`.
  - It is explicitly not described as evidence about real LLM behavior anywhere in the repository.

- **5. Real-LLM Eval (`python -m disputepilot.evals.runner --real-llm`)**:
  - Implemented `GeminiClient` retry loop with exponential backoff (5 retries catching 429/ResourceExhausted), latency measurement (`time.perf_counter()`), token usage tracking (`prompt_tokens`, `candidates_tokens`, `total_tokens`), and structured output logging to `evals/real_llm_outputs.jsonl`.
  - Fail-closed evaluation: when `LLM_API_KEY` is unset, prints `[REAL-LLM EVAL NOTICE] LLM_API_KEY is unset; skipping real Gemini LLM evaluation on 30 messy cases (NOT RUN)` and marks all Real LLM column values as `NOT RUN` in `evals/report.md` and `evals/results.json`. Never writes a fabricated number for an unexecuted run.

- **6. Side-by-Side Reporting & Verification**:
  - Side-by-side evaluation table in `evals/report.md` reports Clean Train, Clean Hold-out, Messy Rules Only, Messy Rules + LLM (fake regex baseline, not a model result), and Real LLM (`NOT RUN`).
  - Unit tests: 89 passing tests (`uv run pytest`).
  - Ruff linter: Zero errors (`uv run ruff check .`).

---

### Phase K: Reporting Refinement, Uplift Neutrality, & Unclassified Display Integrity
- **1. Unclassified Metrics Display (`src/disputepilot/core/recommend.py` & `case_detail.html`)**:
  - Updated `Recommendation` model in `recommend.py` to allow `p_win: float | str`, `p_win_low: float | str`, `p_win_high: float | str`, and `expected_value_paise: int | str`.
  - For unclassified reasons, `recommend_action()` returns `"n/a"` for all probability bounds and expected value, avoiding misleading `0.0` or `₹0` values.
  - In `case_detail.html`, when `p_win` or `expected_value_paise` is `"n/a"`, UI renders `"n/a"` with `[n/a – n/a]` estimated band.
  - Added unit test assertions in `tests/test_recommend.py` and `tests/test_web.py`.
- **2. FakeLLMClient Removal from Headlines & Summary Tables**:
  - Removed all `FakeLLMClient` columns from the summary table in `evals/report.md` and from `README.md`.
  - Moved all FakeLLMClient metrics down to an appendix titled:
    `## Appendix: FakeLLMClient Baseline (fake client written by the same author as the test generator; sanity check only)`
- **3. Uplift Neutrality & Fee Assumptions**:
  - Removed any sentence stating or implying that realistic dispute fees make uplift positive, replacing it with `"not tested"` (with dispute fees set to ₹0.00 by default in simulation).
- **4. Root Cause: Messy-Set Rules-Only Accuracy Drop (17% -> 6%)**:
  - In an earlier implementation, `classify_reason()` had a silent fallback to `ReasonClass.OTHER` when no dispute code or keyword matched.
  - In the 100-case messy dataset, exactly 14 cases have ground-truth `other`. While 3 of those 14 cases matched the keyword `"clarification"` in `reasons.yaml`, the other 11 cases matched no rule. Under the silent fallback to `other`, those 11 non-matching cases were assigned `other` by default, accidentally scoring true positives. Added to 3 genuine keyword matches for `not_as_described` (`"mismatched"`) and 3 genuine keyword matches for `other` (`"clarification"`), this produced 3 + 3 + 11 = 17 cases (17.00%).
  - Eliminating the silent fallback to enforce honest `unclassified` classification stripped away the 11 accidental default credits on `other`, exposing the exact deterministic rule performance: exactly 6 cases (6.00%): 3 `not_as_described` + 3 `other`. The math reconciles completely: 17 - 11 = 6.
- **5. FakeLLMClient Vocabulary Disclosure**:
  - Documented in `evals/report.md` that `FakeLLMClient._classify_reason_regex` directly checks for colloquial phrases authored in `src/disputepilot/sim/messy.py` (`MESSY_REASONS`), including `"parcel gayab"`, `"nahi mila"`, `"dusra maal"`, `"torn stitching"`, `"cloth quality"`, `"maine koi payment nahi kiya"`, `"sleep kar raha"`, `"wallet me tha"`, `"do alag"`, `"do bar"`, `"twin debits"`, `"service stop"`, `"account delete"`, and `"paise wapas"`.
  - Clarified that because `FakeLLMClient` was authored by the same author as the test generator and uses its exact vocabulary, its 82% score is an offline pipeline sanity check, not a real model evaluation.
- **6. README Results Table**:
  - Placed `**Tests passing: 89/89 (fake LLM, offline)**` on its own line above the table (not inside the Real LLM column).
  - Labeled `Field-Level Extraction Accuracy` as `fake regex baseline, appendix only` (from FakeLLMClient).
  - Added the exact 6-case count and true-class breakdown under the table with complete 17% to 6% reconciliation.
- **7. Test Suite & Verification**:
  - `uv run pytest`: 89 passed in 3.4s.
  - `uv run ruff check .`: Clean, 0 errors.
  - `uv run python -m disputepilot.evals.runner --real-llm`: Clean execution, generated report and results.

### Phase L: Approval Token POST Issuance, Audit Hashing, & Documentation Hygiene
- **1. Relative Links & Local Path Scrubbing**:
  - Replaced all local `file:///c:/...` absolute links across `README.md` with repository-relative paths (`src/...`, `docs/...`, `evals/...`).
  - Verified 0 occurrences of `file:///` or user-specific paths across all markdown files in the repository.
- **2. Approval Token Issuance via POST**:
  - Updated `src/disputepilot/web/app.py` so human approval tokens are issued strictly via `POST /cases/{case_id}/review` (with `POST /cases/{case_id}/confirm-submit` alias).
  - Replaced GET routes with POST routes so GET requests to `/review` or `/confirm-submit` return `405 Method Not Allowed`, preventing token generation or side effects via browser prefetching.
  - Updated `src/disputepilot/web/templates/case_detail.html` to POST reviewer name to `/cases/{{ case.case_id }}/review`.
  - Updated web test suite in `tests/test_web.py` to verify POST issuance and assert that GET returns 405.
- **3. Audit Log Token Hashing**:
  - Updated `src/disputepilot/pipeline/audit.py` to sanitize audit event details so that any approval token (key `"approval_token"` or prefix `"appr_"`) is hashed via SHA-256 (`approval_token_hash`), ensuring the raw approval token is never stored in plaintext in the SQLite audit log.
  - Updated `src/disputepilot/web/app.py` contest and accept action handlers to log only `approval_token_hash`.
  - Added unit test `test_audit_records_only_hash_of_approval_token_never_raw_token` in `tests/test_pipeline.py`.
- **4. Limitations Documentation in README**:
  - Explicitly documented in `README.md`: reviewer name is typed and not authenticated via SSO/OIDC, no CSRF protection on forms, approval relies on a confirmation step in the UI, and SQLite storage only.
- **5. Makefile & Windows Command Equivalents**:
  - Added `sim` target to `Makefile` to regenerate `data/cases` (150 clean cases) and `data/cases_messy` (100 messy cases).
  - Listed plain `uv run ...` equivalents for Windows without `make` across README Quickstart and evaluation sections.
- **6. Verification**:
  - `uv run pytest`: 91 passed in 3.6s.
  - `uv run ruff check .`: All checks passed, 0 errors.












