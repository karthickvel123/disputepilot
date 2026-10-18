# Running DisputePilot against Razorpay (test mode)

## 1. Install
```bash
uv sync            # also installs python-multipart (needed for evidence upload); refreshes uv.lock
```

## 2. Configure
```bash
cp .env.example .env
python scripts/hash_password.py     # prints REVIEWER_PASSWORD_HASH and SESSION_SECRET
```
Fill in `.env`: `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` (Dashboard in **Test Mode** -> Account & Settings -> API Keys),
`REVIEWER_USER`, `REVIEWER_PASSWORD_HASH`, `SESSION_SECRET`. Optional: `LLM_API_KEY` (Gemini), `RAZORPAY_WEBHOOK_SECRET`.
`rzp_live_` keys are refused unless `ALLOW_LIVE_KEYS=true`.

## 3. Verify the connection
```bash
make smoke                                   # read-only script against the Razorpay API
make run                                     # http://127.0.0.1:8000
curl 'http://127.0.0.1:8000/status?check=1'  # mode, key type, config problems, one live API call
```

## 4. Demo path
Worklist (open disputes from Razorpay) -> case (payment/order/refunds + analysis) -> add evidence files
(uploaded to Razorpay Documents) -> Proceed to Submission Review (issues a single-use approval token bound to
the exact payload) -> Submit (PATCH /v1/disputes/:id/contest) -> status shown is the one Razorpay returned.

## 5. Webhooks (optional)
Expose the app (e.g. `ngrok http 8000`), add `https://<host>/webhook/razorpay/webhook` in Dashboard -> Webhooks with
the same secret as `RAZORPAY_WEBHOOK_SECRET`, subscribe to the dispute events. Status page: `/webhook/razorpay/health`.

## Synthetic mode
`make run-sim` (or `DATA_MODE=sim`) uses the fixtures in `data/` and shows a red SIMULATED DATA banner on every page.

## Known limitations (disclose these in any write-up)
- **Binary evidence is attested, not scanned.** Razorpay accepts only PDF/PNG/JPEG, and this app cannot scan those for card
  numbers or CVVs. The reviewer must tick a "no card data" confirmation (audit-logged). Only the optional pasted excerpt is
  scanned, and any card/CVV finding blocks the upload. No file bytes are kept locally (metadata and SHA-256 only).
- **Classifier robustness.** Reason-code classification scored 100% on the clean synthetic holdout but 6% on the messy
  synthetic set (see `evals/report.md`). Passing software tests says nothing about decision quality on real disputes.
- **Approval tokens are persisted in SQLite** (`data/approvals.db`), surviving server restarts and worker recycles while maintaining single-use cryptographic binding.
- **Win-probability and effort are fixed placeholder priors**, not learned from outcomes.
- **Test-mode disputes:** whether a Razorpay test account can hold disputes was not confirmed; run `make smoke` to find out.
- Lint (`ruff`) and the full suite should be run on your machine before treating any fix here as verified.
