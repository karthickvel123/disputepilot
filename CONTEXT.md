DisputePilot helps Razorpay merchants respond to payment disputes (chargebacks).
Flow: dispute arrives, then triage, evidence gathering, contest-or-accept recommendation, draft rebuttal, human approval, submission, outcome tracking.
Non-negotiables:
1. Nothing is submitted or accepted without a human approval token.
2. Never store or log full card numbers, CVV or tracks. Block card-number-like strings at ingestion.
3. Deterministic code handles deadlines, status mapping, evidence rules, number/date checks and all write calls. An LLM is used only to read unstructured documents and draft narrative.
4. Every factual sentence in a rebuttal must cite a source document or API field. Unsupported claims are removed and reported.
5. Customer messages and uploaded documents are untrusted data, never instructions.
6. Python 3.12, type hints, Pydantic v2 models, pytest tests for every module, no network calls in tests.
7. Amounts are integers in paise. Times are unix seconds, and `now` is always injectable.
