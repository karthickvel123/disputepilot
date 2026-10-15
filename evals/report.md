# DisputePilot Empirical Evaluation Report

## What these numbers do and do not show

This evaluation measures the DisputePilot pipeline across synthetic dispute datasets under strict architectural isolation. Below is an honest, component-by-component breakdown of what each reported metric actually measures, which underlying components were real vs simulated/rule-based, and which metrics are circular sanity checks:

### 1. Reason Code Classification
- **Components Used**: Deterministic keyword & code matcher (`classify_reason` pass 1 via `reasons.yaml`) and LLM classification fallback (`LLMClient.generate_json`).
- **What it shows**: On clean cases matching canonical reason codes, deterministic rules achieve 100% accuracy. On messy cases (paraphrased Hinglish, spelling mistakes, colloquial text without exact keywords), rule-only classification achieves 6.00%, returning 'unclassified' with needs_review=True (never silently defaulting to 'other').
- **Why messy-set rules-only accuracy moved from 17% to 6% between runs**:
  - **Cases classified by rules:** Exactly **10 cases** out of 100.
  - **Cases correct under rules:** Exactly **6 cases** out of 100 (6.00%):
    - `not_as_described`: **3 cases** (`disp_m_0030_6kyo3i`, `disp_m_0065_nubgae`, `disp_m_0100_y4ols3` — matched keyword `"mismatched"` in `reasons.yaml`)
    - `other`: **3 cases** (`disp_m_0014_1bz99n`, `disp_m_0077_7veemd`, `disp_m_0098_3mlntq` — matched keyword `"clarification"` in `reasons.yaml`)
    - `item_not_received`: **0 cases** (0/15)
    - `unauthorised`: **0 cases** (0/14)
    - `duplicate_charge`: **0 cases** (0/14)
    - `subscription_cancelled`: **0 cases** (0/14)
    - `refund_not_received`: **0 cases** (0/14)
    - **Total correct:** 3 (`not_as_described`) + 3 (`other`) = **6 cases**.
  - **Cases incorrect under rules:** Exactly **4 cases**:
    - 2 cases predicted `duplicate_charge` (ground truth `not_as_described`): `disp_m_0002_3xtplp`, `disp_m_0016_f9caio` (text: *"jo picture me tha wo nahi bheja duplicate piece lag raha"* matched keyword `"duplicate"`)
    - 2 cases predicted `not_as_described` (ground truth `refund_not_received`): `disp_m_0069_xw77t2`, `disp_m_0076_jqb1z7` (text: *"ARN number fake nikla bank bola koi refund nahi aaya"* matched keyword `"fake"`)
  - **Cases left unclassified:** Exactly **90 cases** (90.00%).
  - **Reconciliation with 17% (17 cases):** In the earlier run, when no rule or keyword matched, the classifier had a silent fallback to `ReasonClass.OTHER`. The 100-case messy dataset contains exactly 14 cases whose true ground-truth class is `other`. While 3 of those 14 matched the keyword `"clarification"`, the remaining **11 `other` cases** did not match any rule keyword. Under the silent fallback to `other`, those 11 non-matching cases were assigned `other` by default, accidentally scoring true positives. Added to the 3 keyword matches for `not_as_described` and the 3 keyword matches for `other`, this yielded 3 + 3 + 11 = 17 cases (17.00%). Removing the silent fallback and honestly returning `unclassified` eliminated those 11 accidental credits, leaving exactly 17 - 11 = 6 correct cases (6.00%), 4 incorrect cases (total 10 classified), and 90 unclassified cases. The numbers reconcile completely.
- **What it does not show**: Live production bank dispute accuracy where reason strings may be entirely unstandardized or contain conflicting bank narrative codes.

### 2. Document Field Extraction
- **Components Used**: In offline test mode, FakeLLMClient provides a fake regex baseline, not a model result. In real mode with LLM_API_KEY configured, genuine Google Gemini (GeminiClient) performs structured JSON extraction.
- **What it shows**: On clean cases matching canonical invoice/POD templates, the deterministic regex baseline succeeds (100.0%). On messy cases with varied date styles, docket numbers, and address formats, template regex matching fails (0.0%).
- **What it does not show**: Real-world optical character recognition (OCR) or document image parsing errors (scanned PDFs, blurry photos), as all documents are parsed as UTF-8 text.

### 3. Missing Evidence Category Recall
- **Components Used**: Rule-based comparison between the deterministic requirements matrix (`requirements.yaml`) and the simulator's ground-truth document availability tags.
- **Classification**: **Pipeline sanity check, not performance**.
- **Why Circular**: The Evidence Agent audits available files against the exact same network rules encoded into the system. High recall confirms that the agent correctly queries and flags categories per the spec; it does not represent machine learning discovery on unlabelled data.

### 4. Drafting Faithfulness & Zero Fabrications
- **Components Used**: Deterministic token verifier (`verify_rebuttal` in `src/disputepilot/drafting/verifier.py`).
- **Classification**: **Pipeline sanity check, not performance**.
- **Why Circular**: The 0-fabrication number in clean drafts is not a probabilistic claim about LLM behavior; it is an enforced structural guarantee of the pipeline. The verifier unconditionally deletes any drafted sentence whose dates, amounts, or identifiers are not exact verbatim matches in the verified FactSet.

### 5. Adversarial Safety & PCI-DSS Protection
- **Components Used**: Real Luhn checksum card scanner (`scan_text` in `src/disputepilot/safety/card_scanner.py`) and substring instruction fencing (`<<<UNTRUSTED_CONTENT>>>`).
- **What it shows**: Synthetic credit card sequences with valid Luhn checks are redacted before reaching drafts, and prompt injection attempts are fenced.
- **What it does not show**: Comprehensive immunity against advanced multi-turn jailbreaks or steganographic prompt injection in image attachments.

### 6. Recommendation Decision vs. Winnable Ground Truth
- **Components Used**: Heuristic expected value formula (`recommend_action` in `src/disputepilot/core/recommend.py`) vs. simulator ground-truth labels.
- **Classification**: **Pipeline sanity check, not performance**.
- **Why Circular**: The simulator's ground-truth `winnable` label is assigned by deterministic network rules in `rules.py`. The recommendation engine uses heuristic weights designed to mirror those same rules. Evaluating one against the other tests that the heuristic aligns with the simulator's rules, not that DisputePilot predicts real bank arbitration outcomes.

### 7. Financial Value Recovery Projections
- **Classification**: **Simulated, under assumptions listed here**.
- **Assumptions**: Merchant response effort cost = ₹0.00, dispute fee per chargeback = ₹0.00 (both editable config values set to 0 by default unless supplied).
- **What it shows**: A mathematical tally of synthetic dispute amounts when following the heuristic decision vs contesting all or accepting all under the listed assumptions.
- **What it does not show**: Actual recovered bank funds. Without real bank dispute fee schedules and merchant labor cost data, any rupee recovery figure is purely hypothetical. Whether realistic dispute fees make uplift positive is not tested.

### Evaluation Policy: No Averaging
Clean and messy results are reported side by side in separate columns below. They are **never averaged**, as doing so would obscure the stark degradation caused by noisy inputs.

---

> [!IMPORTANT]
> **Synthetic Data Notice**: All evaluation metrics, win probabilities, and financial simulations in this report were generated on synthetic dispute cases produced by DisputePilot's dispute simulator (`src/disputepilot/sim/`). These results do not reflect live production merchant data.

## Side-by-Side Evaluation Summary

| Metric | Clean Train (70%, in-distribution) | Clean Hold-out (30%, in-distribution) | Messy Set: Rules Only (n=100) | Real LLM (Gemini) | Metric Classification |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Reason Code Accuracy** | 100.00% | 100.00% | 6.00% | 93.75% (k=16 unique) | LLM fallback (Gemini), n=16 unique cases |
| **Reason Code Macro-F1** | 100.00% | 100.00% | 9.33% | 92.38% (k=16 unique) | LLM fallback (Gemini), n=16 unique cases |
| **Field-Level Extraction Accuracy** | fake regex baseline, appendix only | fake regex baseline, appendix only | fake regex baseline, appendix only | n too small (k=1) | fake regex baseline, appendix only |
| **Missing-Category Recall** | 98.96% | 100.00% | 100.00% | N/A (omitted for budget) | **Pipeline sanity check, not performance** |
| **Raw Sentence Grounding Rate** | 100.00% | 100.00% | 100.00% | N/A (omitted for budget) | Pre-verifier fact coverage |
| **Fabricated Claims in Clean Drafts** | **0** | **0** | **0** | N/A (omitted for budget) | **Pipeline sanity check, not performance** (verifier guarantee) |
| **Prompt Injection Containment** | 100.00% | 100.00% | 100.00% | N/A (omitted for budget) | Fencing check |
| **PCI-DSS Card Leaks** | **0** | **0** | **0** | N/A (omitted for budget) | Deterministic Luhn scanner |
| **Decision Accuracy vs. Winnable** | 84.76% | 88.89% | 72.00% | N/A (omitted for budget) | **Pipeline sanity check, not performance** (heuristic vs sim rules) |
| **DisputePilot Policy Recovery (INR)** | ₹367,850.00* | ₹116,783.00* | ₹26,999.00* | N/A (omitted for budget) | Simulated, under assumptions listed here |
| **Uplift vs Contest-All (INR)** | ₹-49,692.00* | ₹-71,995.00* | ₹-127,873.00* | N/A (omitted for budget) | Simulated, under assumptions listed here |

\* *Simulated, under assumptions listed here: response effort cost = ₹0.00, dispute fee = ₹0.00. Whether realistic dispute fees make uplift positive is not tested.*

---

## Real LLM Evaluation (GeminiClient)

**Overall Status: PARTIAL (classification 16 unique of 30 planned, extraction 1 unique of 5 planned)**

### Stage 1: Reason Code Classification (Rules Fallback Only)
- **Status:** PARTIAL: 16 unique of 30 planned
- **Unique Cases Scored:** k=16 unique cases (rule: first completed record used; 5 duplicate records dropped)
- **Correct Count:** 15 / 16
- **Accuracy (vs Ground Truth):** 93.75% (15 of 16 unique)
- **Macro-F1 Score:** 92.38%
- **Duplicate Records Dropped:** 5

#### Sample Composition & Origin:
- **Sample Selection**: Not a random sample. These 16 unique cases represent the order in which cases left unclassified by rules were encountered during earlier interrupted evaluation runs.
- **Interrupted Runs**: Calls were recorded across multiple quota-limited runs before checkpoint deduplication, yielding 21 total records. When deduplicated by case ID using the first completed record rule, 5 duplicate records are dropped, leaving 16 unique cases.
- **Unique Cases Scored (16 cases)**:
  1. `disp_m_0096_ul4bkz`
  2. `disp_m_0092_nyhd17`
  3. `disp_m_0088_bi1dls`
  4. `disp_m_0095_7x79m1`
  5. `disp_m_0036_9z8dzt`
  6. `disp_m_0032_8nkm7w`
  7. `disp_m_0094_3499yi`
  8. `disp_m_0084_mqm9sb`
  9. `disp_m_0055_tii54p`
  10. `disp_m_0005_kwo886`
  11. `disp_m_0078_bh400t`
  12. `disp_m_0085_r71yk1`
  13. `disp_m_0093_lob3f2`
  14. `disp_m_0068_446v8y`
  15. `disp_m_0090_l2g3vu`
  16. `disp_m_0058_bmo2fj`

#### Misclassified Cases:
| Case ID | Model Answer | True Label | Model Confidence | Raw Reason Text |
| --- | --- | --- | --- | --- |
| `disp_m_0005_kwo886` | `unauthorised` | `subscription_cancelled` | 1.00 | *"free trial khatam hote hi bina permission charge lagaya"* |

### Confidence Statistics & Calibration
- **Reported Confidence Distribution:**
  - `1.00`: 8 records (50.0%)
  - `0.95`: 5 records (31.2%)
  - `0.90`: 3 records (18.8%)
- **Answers Below 0.6 Review Threshold:** 0 (0.0%)
- **Calibration Assessment:** Self-reported confidence is not calibrated. For example, on the misclassified case (`disp_m_0005_kwo886`), the model expressed 1.00 (100%) confidence in `unauthorised`, despite the ground truth being `subscription_cancelled`. Raw LLM confidence cannot be interpreted as calibrated posterior probability without empirical recalibration.

### Stage 2: Document Field Extraction (Verbatim Quoted Fields Only)
- **Status:** PARTIAL: 1 unique of 5 planned
- **Documents Scored:** 1 (n too small for an accuracy rate)
- **Fields Returned:** 6 (all with verbatim source quotes: 6 of 6)
- **Fields Checkable vs Ground Truth:** 2 (correct: 2)
- **Fields with No Ground-Truth Field in Eval:** 4 (`invoice_number`, `payment_id`, `billing_address`, `invoice_date`)
- **Fields Null:** 4
- **Fields without Verbatim Quote:** None (all quotes found verbatim)
- **Field-Level Accuracy:** n too small for an accuracy rate
- **Evaluation Criteria:** Accuracy is computed only for fields where the model returned a verbatim `source_quote` matching the source document text.

### Real LLM results: how to read them
- **Status:** PARTIAL (classification 16 unique of 30 planned, extraction 1 unique of 5 planned)
- Synthetic data only.
- One run.
- No confidence intervals.
- Results are not evidence of real-world accuracy.
- Sample is not a random sample (derived from interrupted evaluation runs).

---

## 1. Reason Code Classification

### Clean Hold-out Set (30%, in-distribution, n=45)
- **Overall Accuracy:** 100.00%
- **Macro-F1 Score:** 100.00%

| Reason Class | Precision | Recall | F1-Score | Support |
| --- | --- | --- | --- | --- |
| `item_not_received` | 100.0% | 100.0% | 100.0% | 8 |
| `not_as_described` | 100.0% | 100.0% | 100.0% | 8 |
| `unauthorised` | 100.0% | 100.0% | 100.0% | 5 |
| `duplicate_charge` | 100.0% | 100.0% | 100.0% | 4 |
| `subscription_cancelled` | 100.0% | 100.0% | 100.0% | 2 |
| `refund_not_received` | 100.0% | 100.0% | 100.0% | 8 |
| `other` | 100.0% | 100.0% | 100.0% | 10 |

### Messy Set: Rules Only (n=100)
- **Overall Accuracy:** 6.00%
- **Macro-F1 Score:** 9.33%

| Reason Class | Precision | Recall | F1-Score | Support |
| --- | --- | --- | --- | --- |
| `item_not_received` | 0.0% | 0.0% | 0.0% | 15 |
| `not_as_described` | 60.0% | 20.0% | 30.0% | 15 |
| `unauthorised` | 0.0% | 0.0% | 0.0% | 14 |
| `duplicate_charge` | 0.0% | 0.0% | 0.0% | 14 |
| `subscription_cancelled` | 0.0% | 0.0% | 0.0% | 14 |
| `refund_not_received` | 0.0% | 0.0% | 0.0% | 14 |
| `other` | 100.0% | 21.4% | 35.3% | 14 |

---

## 2. Recommendation Engine & Calibration
- **Clean Hold-out Accuracy vs Winnable:** 88.89%
- **Messy Set (Rules Only) Accuracy vs Winnable:** 72.00%

### Calibration Table: Clean Hold-out Set
| Win Probability Bin | Count | Mean Predicted $p_{win}$ | Actual Win Rate |
| --- | --- | --- | --- |
| [0.0, 0.2) | 14 | 11.0% | 0.0% |
| [0.2, 0.4) | 11 | 34.3% | 27.3% |
| [0.4, 0.6) | 5 | 55.2% | 0.0% |
| [0.6, 0.8) | 6 | 73.2% | 100.0% |
| [0.8, 1.0] | 9 | 93.0% | 100.0% |

---

## 3. Financial Value Recovery Analysis

> **Assumptions (Editable Config Values)**:
> - Response effort cost per dispute: ₹0.00 (simulated, under assumptions listed here)
> - Dispute fee per chargeback: ₹0.00 (simulated, under assumptions listed here)

| Policy | Clean Hold-out (in-distribution, n=45) | Messy Set: Rules Only (n=100) | Real LLM (Gemini) | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Accept Everything** | ₹0.00* | ₹0.00* | N/A (omitted for budget) | Concedes 100% of disputes |
| **Contest Everything** | ₹188,778.00* | ₹154,872.00* | N/A (omitted for budget) | Contests winnable and unwinnable alike |
| **DisputePilot Policy** | **₹116,783.00*** | **₹26,999.00*** | N/A (omitted for budget) | Selectively contests high-probability disputes |
| **Uplift vs Contest-All** | **₹-71,995.00*** | **₹-127,873.00*** | N/A (omitted for budget) | Not tested (dispute fees set to ₹0.00 in simulation) |

\* *All rupee amounts are simulated, under assumptions listed here (effort cost ₹0.00, dispute fee ₹0.00). Whether realistic dispute fees make uplift positive is not tested.*

---

## Appendix: FakeLLMClient Baseline (fake client written by the same author as the test generator; sanity check only)

### Classification Methodology & sim/messy.py Vocabulary Overlap
FakeLLMClient performs reason classification in `src/disputepilot/extraction/llm.py` via `_classify_reason_regex`. It does not execute a machine learning model or neural network. Instead, it applies regular expressions and substring keyword matching.

**Direct Vocabulary Overlap with `sim/messy.py`:**
FakeLLMClient explicitly uses vocabulary mined directly from the colloquial phrase templates in `src/disputepilot/sim/messy.py` (`MESSY_REASONS`). Specifically:
- **`item_not_received`**: Checks for phrases like `"parcel gayab"`, `"nahi mila"`, `"consignment lost"`, `"waiting since"`, `"empty"`, `"handed over"`.
- **`not_as_described`**: Checks for `"dusra maal"`, `"torn stitching"`, `"cloth quality"`, `"cheap plastic"`, `"shattered"`, `"wrong variant"`.
- **`unauthorised`**: Checks for `"maine koi payment nahi kiya"`, `"otp kisne dala"`, `"wallet me tha"`, `"sleep kar raha"`, `"stranger purchased"`.
- **`duplicate_charge`**: Checks for `"do alag"`, `"do bar"`, `"twin debits"`, `"double withdrawal"`, `"deducted twice"`, `"screen freeze"`.
- **`subscription_cancelled`**: Checks for `"service stop"`, `"account delete"`, `"opted out"`, `"free trial"`, `"unsubscribed"`.
- **`refund_not_received`**: Checks for `"paise wapas"`, `"paisa wapas"`, `"consignment returned"`, `"arn number fake"`.
- **`other`**: Checks for `"bank branch manager"`, `"audit clarification"`, `"tax and surcharge"`.

Because `FakeLLMClient` was authored by the same engineer who wrote the synthetic test generator and reuses the exact keywords from `sim/messy.py`, its 82.00% accuracy on messy cases is an internal pipeline sanity check, not evidence of generalization or real-world LLM capabilities.

### Sanity Check Metrics: Messy Set (Rules + FakeLLMClient, n=100)

| Metric | Messy Set: Rules + FakeLLMClient (Sanity Check Only, n=100) |
| :--- | :--- |
| **Reason Code Accuracy** | 82.00% |
| **Reason Code Macro-F1** | 86.54% |
| **Field-Level Extraction Accuracy** | 0.00% |
| **Missing-Category Recall** | 100.00% |
| **Raw Sentence Grounding Rate** | 100.00% |
| **Fabricated Claims in Clean Drafts** | 0 |
| **Prompt Injection Containment** | 100.00% |
| **PCI-DSS Card Leaks** | 0 |
| **Decision Accuracy vs. Winnable** | 76.00% |
| **DisputePilot Policy Recovery (INR)** | ₹135,678.00* |
| **Uplift vs Contest-All (INR)** | ₹-19,194.00* |

#### FakeLLMClient Per-Class Reason Breakdown (Messy Set)
| Reason Class | Precision | Recall | F1-Score | Support |
| --- | --- | --- | --- | --- |
| `item_not_received` | 90.0% | 60.0% | 72.0% | 15 |
| `not_as_described` | 84.6% | 73.3% | 78.6% | 15 |
| `unauthorised` | 92.9% | 92.9% | 92.9% | 14 |
| `duplicate_charge` | 87.5% | 100.0% | 93.3% | 14 |
| `subscription_cancelled` | 100.0% | 92.9% | 96.3% | 14 |
| `refund_not_received` | 100.0% | 57.1% | 72.7% | 14 |
| `other` | 100.0% | 100.0% | 100.0% | 14 |

#### FakeLLMClient Calibration Table (Messy Set)
| Win Probability Bin | Count | Mean Predicted $p_{win}$ | Actual Win Rate |
| --- | --- | --- | --- |
| [0.0, 0.2) | 11 | 11.7% | 0.0% |
| [0.2, 0.4) | 19 | 29.0% | 5.3% |
| [0.4, 0.6) | 15 | 49.6% | 0.0% |
| [0.6, 0.8) | 23 | 70.3% | 47.8% |
| [0.8, 1.0] | 20 | 91.9% | 65.0% |