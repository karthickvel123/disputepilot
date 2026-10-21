# DisputePilot Operations Runbook

This runbook provides actionable procedures for production and pilot operators running DisputePilot in single-merchant live or test mode with Razorpay (`rzp_test_*` or `rzp_live_*`).

---

## 1. Inbound Webhook Delivery Failures & Signature Mismatch Spikes

### Symptoms & Triggers
- **Alert**: Spike in HTTP 400 responses on `/webhook/razorpay`.
- **Log Pattern**: `Razorpay webhook signature verification failed` or `webhook_signature_invalid`.
- **Razorpay Dashboard**: Webhook delivery status showing recurring red `Failed` attempts with response code `400` or `413`.

### Architecture & Security Invariants
- All webhooks must carry an `X-Razorpay-Signature` computed using HMAC-SHA256 over the raw, unparsed request bytes with `RAZORPAY_WEBHOOK_SECRET`.
- The webhook endpoint enforces a strict **256 KB** body limit (rejects oversized payloads with HTTP 413) and a **120 requests/minute** sliding-window IP rate limiter (HTTP 429).
- Duplicate deliveries are idempotent: verified via `dispute.id` and event sequence numbers without re-triggering draft re-computation.

### Diagnostic Steps
1. **Inspect Application Logs**:
   ```bash
   # Filter for webhook authentication failures
   grep "webhook signature verification failed" /var/log/disputepilot.log
   # Filter for oversized payloads or rate-limiting
   grep "Webhook payload exceeded limit" /var/log/disputepilot.log
   ```
2. **Verify Configured Secret**:
   Ensure `RAZORPAY_WEBHOOK_SECRET` in environment matches the secret in Razorpay Merchant Dashboard (`Settings -> Webhooks -> [Target Webhook] -> Secret`).
3. **Check Reverse Proxy / Cloudflare**:
   Confirm reverse proxy (e.g., Render, Nginx, Cloudflare) does NOT alter payload encoding, decompress gzip unexpectedly, or strip HTTP headers (`X-Razorpay-Signature`).

### Remediation Procedure
1. If secret mismatch is confirmed:
   - Update `RAZORPAY_WEBHOOK_SECRET` in deployment environment variables (`render.yaml` or `.env`).
   - Trigger a rolling restart of the application.
2. In the Razorpay Dashboard, navigate to **Settings > Webhooks > Edit** and re-send a sample test event (`payment.dispute.created`).
3. If Razorpay disabled the webhook due to consecutive delivery failures, click **Enable Webhook**.
4. Run the automated integration diagnostic:
   ```bash
   python scripts/smoke_razorpay.py
   ```

---

## 2. Razorpay API Outages & Retry Handling

### Symptoms & Triggers
- **Alert**: 5xx Gateway errors or connection timeouts when fetching dispute cases or uploading evidence documents.
- **Log Pattern**: `Razorpay API error` or `ConnectionError` / `Timeout` connecting to `api.razorpay.com`.

### Architecture & Safety Invariants
- DisputePilot **never** performs automated submissions without human approval.
- Background sync and document upload tasks employ exponential backoff with jitter (1s, 2s, 4s, 8s, up to max 30s) for idempotent GET requests.
- Mutating operations (`PATCH /v1/disputes/:id/contest`, `POST /v1/documents`) require an explicit one-use cryptographic `ApprovalToken`. If the API fails while consuming the token, the token failure is recorded in the audit log, preventing silent chargeback forfeits.

### Diagnostic Steps
1. Check public Razorpay API status: `https://status.razorpay.com`.
2. Probe API connectivity from the server:
   ```bash
   curl -I -u "$RAZORPAY_KEY_ID:$RAZORPAY_KEY_SECRET" https://api.razorpay.com/v1/disputes
   ```
3. Use the built-in diagnostic endpoint (authenticated):
   ```bash
   curl -X POST http://127.0.0.1:8000/api/v1/integrations/razorpay/test -H "Cookie: session=..."
   ```

### Remediation Procedure
1. If Razorpay is experiencing a degraded outage:
   - Operators can continue reviewing dispute evidence, generating drafts, and verifying facts locally.
   - Do **NOT** attempt manual retry loops that could hammer degraded upstream endpoints.
   - Outbound submissions should be held until the Razorpay status page reports operational status.
2. If network/DNS resolution issue on the container:
   - Check container DNS resolution (`nslookup api.razorpay.com`).
   - Restart the worker process if socket pools are exhausted.

---

## 3. Gemini LLM Outage / Quota Exhaustion & Fallback Monitoring

### Symptoms & Triggers
- **Alert**: HTTP 429 `ResourceExhausted` (daily quota or per-minute burst exhausted) or HTTP 503 `ServiceUnavailable` from Google Gemini API.
- **Log Pattern**: `LLM rebuttal drafting failed`, `LLM reason classification failed`, or `GeminiDailyQuotaError`.

### Built-in Safety & Fallback Behavior
DisputePilot is designed to operate safely even during total LLM outages:
1. **Reason Classification**: Falls back to deterministic rule-based matching (`classify_reason` in `src/disputepilot/core/reasons.py`). If ambiguous, sets `reason_class = UNCLASSIFIED` and flags `needs_review = True`.
2. **Rebuttal Drafting**: Falls back to deterministic template generation (`_fallback_summary`, `_fallback_timeline`, `_fallback_evidence`, `_fallback_conclusion`). Every sentence cites exact Fact IDs.
3. **Deterministic Verifier**: `verify_rebuttal` strictly checks all entity claims (dates, order IDs, amounts) against `FactSet`. No hallucinated claims can ever pass to the merchant.

### Monitoring & Metrics
- The operator dashboard displays fallback events and unclassified reasons under **Pending Review**.
- Check `/api/v1/status` to verify whether LLM is active or in fallback mode.

### Remediation Procedure
1. If quota exhausted (429):
   - Switch to paid tier in Google AI Studio or increase daily quota.
   - Rotate `GEMINI_API_KEY` or `LLM_API_KEY` in environment variables:
     ```bash
     export GEMINI_API_KEY="AIzaSyNewKey..."
     ```
2. If temporary Google API outage (503):
   - No operator panic is necessary. Deterministic fallback continues generating grounded, verifiable rebuttals without hallucinations.
   - Merchant reviewers can inspect and edit rebuttal drafts manually in the Review Queue.

---

## 4. Expired Dispute Deadlines & SLA Escalation

### Dispute Lifecycle & SLA Windows
- Under Visa, Mastercard, and RuPay card scheme rules, merchants have strict deadlines to contest chargebacks (typically **3 to 7 calendar days** from dispute creation).
- Razorpay specifies this deadline via the `respond_by` unix timestamp.
- If a dispute is not contested or conceded prior to `respond_by`, the card scheme **automatically forfeits** liability to the cardholder and debits merchant funds plus chargeback penalties.

### Reminders & Escalation System
DisputePilot tracks deadlines in SQLite (`data/reminders.db`):
- **T-48 Hours**: Case flagged with Amber badge on Dashboard; moved to top of Priority Queue.
- **T-24 Hours**: Urgent SLA escalation banner triggered; email notification dispatched to merchant operations lead.
- **T-12 Hours**: Emergency escalation; pre-verified draft auto-staged for immediate one-click cryptographic approval token generation.
- **T-0 (Expired)**: Recorded in audit log as `DISPUTE_EXPIRED_UNCONTESTED`.

### Daily Operator Checklist
1. Log in to DisputePilot Dashboard every business morning at 09:00 IST.
2. Review the **Urgent Queue** (`/disputes?filter=urgent`):
   - Verify all disputes with `< 48h` deadline have evidence matched.
   - If evidence is complete and recommendation is `CONTEST`, generate Approval Token and contest before T-12h.
   - If merchant has no proof of delivery or fraud is verified, concede before deadline to avoid scheme arbitration fees.
3. Verify reminder daemon status:
   ```bash
   # Check pending reminders
   sqlite3 /var/data/disputepilot/reminders.db "SELECT case_id, remind_at, status FROM reminders WHERE status = 'pending' ORDER BY remind_at ASC LIMIT 10;"
   ```
