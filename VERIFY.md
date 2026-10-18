# Verification checklist (Windows PowerShell)

Run from the project root. Do not call anything "verified" until its line below has actually passed.

```powershell
uv sync                                                # installs everything incl. google-genai, python-multipart
uv run pytest -q                                       # full suite (expect the Gemini tests to pass once synced)
uv run ruff check .                                    # lint
uv run python -m disputepilot.evals.adversarial        # regenerates evals/adversarial/report.md (rules only)
uv run python -m disputepilot.evals.adversarial --llm  # needs LLM_API_KEY; measures the model fallback too
uv run python scripts/smoke_razorpay.py                # read-only check against your Razorpay TEST account
uv run uvicorn disputepilot.web:app --reload           # then open http://127.0.0.1:8000 and /status?check=1
```

Record, for each: pass/fail and the exact error text if it failed.

Adversarial eval notes
- Cases: `evals/adversarial/cases.jsonl` (rebuild with `python evals/adversarial/build_dataset.py`).
- `evals/adversarial/baseline.json` is a ratchet: tests fail if a failure count rises. After you improve the
  classifier, LOWER the numbers there; never raise them.
- Not yet covered: conflicting dates/amounts in documents (verifier), malformed PDF/image inputs, and real disputes.
