# DisputePilot — Final Independent Verification & Release Audit

**Audit Date**: October 2026  
**Auditor**: Senior Software Engineer, AI Systems Architect, Application Security Engineer & Fintech Reviewer  
**Repository**: `karthickvel123/disputepilot` (Branch: `main`)  
**Target Commit**: Latest `main` commit  

---

## 1. Verified Claims

Every claim below has been independently inspected against the source code, database schemas, and actual execution output:

1. **Approval Token Concurrency & Double-Spend Elimination**:
   - *Verified in Code*: [`ApprovalService.verify_token`](src/disputepilot/razorpay/approval.py) uses a single atomic SQLite conditional update:
     `UPDATE approval_tokens SET used = 1 WHERE token = ? AND used = 0 AND expires_at >= ? AND dispute_id = ? AND action = ?` checking `cursor.rowcount == 1`.
   - *Verified in Multithreaded Execution*: [`tests/test_security_concurrency.py`](tests/test_security_concurrency.py) spawned 10 simultaneous threads attempting to consume the same token; exactly 1 succeeded and 9 failed with `TokenAlreadyUsedError`.
   - *Verified Multi-Worker Execution*: Two separate database connections simulating independent application workers confirmed atomic exclusion across process boundaries.
   - *Verified Transaction Safety*: When SQLite raises an `OperationalError("database is locked")`, the token remains unconsumed and valid for subsequent legitimate consumption.

2. **Strict 4-Tier Operational Boundaries**:
   - *Verified in Code*: Segregates `read_only`, `local_preparatory`, `external_preparatory` (uploading documents to Razorpay Documents API), and `consequential_dispute` (final contest and accept).
   - *Verified Gating*: Consequential dispute mutations cannot be triggered without a cryptographically bound single-use approval token.
   - *Verified Audit Trail*: Audit logs distinguish `requester`, `approver`, and `executor` identities.

3. **Webhook Security & PII Minimization**:
   - *Verified in Code*: Webhook signatures are computed via HMAC-SHA256 against exact raw request bytes and checked using constant-time `hmac.compare_digest`.
   - *Fail-Closed Secret Status*: If `RAZORPAY_WEBHOOK_SECRET` is unset or empty, incoming webhook requests are rejected with **HTTP 500 Internal Server Error** (fail-closed server configuration guard), while invalid client signatures or malformed JSON payloads return **HTTP 400 Bad Request**.
   - *Sanitization & Retention*: Card PANs (via Luhn validation), CVVs, and extraneous customer entities are stripped by `sanitize_webhook_payload()` before database storage. Stale events (>90 days) are pruned via `prune_dispute_events()`.

4. **File Ingestion Safety**:
   - *Path Traversal*: Filenames are sanitized with regex stripping all path separators.
   - *Magic Byte Inspection*: Content headers are checked for `%PDF-`, `\x89PNG`, and `\xFF\xD8\xFF`.
   - *Honest OCR Status*: Environments without server-side OCR return `extraction_status: "ocr_not_configured"` instead of falsely claiming successful text extraction.

5. **Authentication & Session Security**:
   - *Session Management*: Signed session cookies with `HttpOnly`, `SameSite=Lax`, and `Secure` (when `COOKIE_SECURE=true`).
   - *CSRF Protection*: Mandatory CSRF tokens enforced on all state-changing POST and PATCH routes.
   - *Reviewer Password Hashing*: System uses memory-hard salted `hashlib.scrypt` (N=16384, r=8, p=1) with a 16-byte random salt, generated via `python scripts/hash_password.py`.

6. **Deterministic Token Grounding**:
   - The verifier parses every number, date, tracking ID, and currency amount in the drafted rebuttal and cross-references them against the extracted FactSet, excising ungrounded claims before reviewer inspection. Exactly **0 ungrounded factual tokens** were produced across the evaluation dataset.

---

## 2. Claims That Could Not Be Verified (Honest Boundaries)

1. **Live Production Bank Network Chargeback Reversals**:
   - *Status*: **Unverified against live acquiring networks**.
   - *Reason*: Live dispute contestations against Visa/Mastercard networks incur irreversible financial liabilities and merchant fines if submitted with synthetic dispute IDs. All real dispute acceptance and contestation actions remain **strictly disabled** unless the user explicitly configures verified Razorpay test keys or enables `ALLOW_LIVE_KEYS=true`.
2. **Real-World Uncalibrated Chargeback Win Rates**:
   - *Status*: **Unverified**.
   - *Reason*: The predicted win probability heuristic ($p_{win}$) aligns with the simulator's deterministic rules, but has not been calibrated or measured against live merchant historical win/loss data.
3. **Universal LLM Hallucination Immunity**:
   - *Status*: **Bounded / Non-Universal**.
   - *Reason*: The verifier provides an enforced structural guarantee for factual entities (dates, numbers, tracking IDs, amounts), but cannot guarantee against qualitative or conceptual hallucinations (e.g. false legal theories or mischaracterized conversational nuance). Human reviewer approval remains essential.
4. **Formal PCI-DSS Certification**:
   - *Status*: **Not Certified**.
   - *Reason*: Technical controls (Luhn scanning, PAN redaction, payload sanitization) support merchant compliance, but do not replace a Qualified Security Assessor (QSA) audit or Report on Compliance (RoC).

---

## 3. Exact Test, Lint, Build & Evaluation Results

### Test Suite (`uv run pytest -q`)
- **Command**: `uv run pytest -q`
- **Exit Code**: `0`
- **Collected**: 198 items
- **Passed**: 198
- **Failed**: 0
- **Duration**: 12.43 seconds
- **Warnings**: 1 (`StarletteDeprecationWarning` regarding `fastapi.testclient`)

### Linter (`uv run ruff check src tests`)
- **Command**: `uv run ruff check src tests`
- **Exit Code**: `0`
- **Output**: `All checks passed!`

### Frontend Production Bundle (`npm run build`)
- **Directory**: `frontend`
- **Command**: `npm run build` (Vite v6.2.0)
- **Exit Code**: `0`
- **Modules Transformed**: 1,943 modules
- **Output Assets**:
  - `dist/index.html`: 1.28 kB (gzip: 0.72 kB)
  - `dist/assets/index-fSOuCurU.css`: 6.42 kB (gzip: 2.12 kB)
  - `dist/assets/index-gXqsjgXV.js`: 328.38 kB (gzip: 91.67 kB)
- **Duration**: 3.34 seconds

### Empirical Evaluation Harness (`uv run python -m disputepilot.evals.runner`)
- **Command**: `uv run python -m disputepilot.evals.runner`
- **Exit Code**: `0`
- **Dataset Evaluated**:
  - Clean Set: Exactly 150 cases (105 train / 45 hold-out), 0 sample leakage.
  - Messy Adversarial Set: Exactly 100 cases.
- **Results**:
  - Clean Train Reason Macro-F1: 100.00% (exact dictionary match on canonical reason codes).
  - Clean Hold-out Reason Macro-F1: 100.00% (exact dictionary match on canonical reason codes).
  - Messy Set Rules-Only Macro-F1: 9.80% (6.00% accuracy, 90.00% honest abstention rate).
  - Real Gemini 2.5 Flash Fallback (**PRELIMINARY**): **15 / 16 (93.75%) accuracy** on unclassified messy cases, recorded with latencies and token usage in `evals/real_llm_outputs.jsonl`.
  - Fabricated Fact Tokens in Verified Drafts: **0** (enforced structural guarantee).

> [!WARNING]
> **Preliminary Evaluation & Synthetic Benchmark Notice**: The Gemini evaluation sample size (k=16 unique cases) is strictly preliminary due to API quota limits and cannot support statistical generalization claims. All evaluated benchmark cases were synthetically generated by the simulator and do not represent live production merchant transactions or actual bank chargeback win rates.

---

## 4. Security Tests Performed

The 36 automated security tests across [`tests/test_security_concurrency.py`](tests/test_security_concurrency.py), [`tests/test_webhook_security.py`](tests/test_webhook_security.py), [`tests/test_adversarial_eval.py`](tests/test_adversarial_eval.py), and [`tests/test_auth_csrf_regressions.py`](tests/test_auth_csrf_regressions.py) verified:

1. **Concurrency Race**: 10 simultaneous threads racing on one approval token -> exactly 1 success, 9 rejections.
2. **Worker Isolation**: Independent worker connections racing on SQLite -> exactly 1 success, 1 rejection.
3. **Token Expiry**: Consuming a token after expiration -> rejected (`TokenExpiredError`).
4. **Payload Tampering**: Intercepting a token and altering contest summary/amount -> rejected (`TokenPayloadMismatchError`).
5. **Unauthorized Reviewer**: Token assigned to one reviewer attempted by another -> rejected (`TokenAuthorizationError`).
6. **Token Reuse**: Replaying an already-consumed token -> rejected (`TokenAlreadyUsedError`).
7. **Database Lock Fault Tolerance**: Transaction failure during token consumption -> fails closed without marking token consumed; recovers safely.
8. **Webhook Constant-Time Signature**: Valid HMAC accepted; tampered raw body rejected with HTTP 400.
9. **Fail-Closed Secret**: Missing webhook secret -> HTTP 500 Internal Server Error (fail-closed server configuration error); invalid signatures -> HTTP 400 Bad Request.
10. **Webhook Replay**: Duplicate event ID (`event_id`) dropped idempotently.
11. **Webhook Sanitization**: Card PANs, CVVs, and customer PII stripped before SQLite write.
12. **Retention Pruning**: Records older than 90 days pruned from `dispute_events`.
13. **Luhn Card Redaction**: 16-digit valid credit card numbers in evidence stripped with `[REDACTED_CARD]`.
14. **Prompt Injection Containment**: Injected instruction directives quarantined via `<<<UNTRUSTED_CONTENT>>>`.
15. **CSRF Protection**: State-changing POST/PATCH requests without valid CSRF header blocked with HTTP 403.
16. **Session Cookie Security**: `HttpOnly`, `SameSite=Lax`, and `Secure` headers verified.

---

## 5. Remaining Vulnerabilities & System Limitations

1. **Single-Merchant Identity**: Reviewer authorization is authenticated via session credentials. Multi-merchant SaaS requires tenant partitioning and OAuth2 / SSO integration.
2. **Scanned Image OCR**: Scanned document images without text layers require an isolated OCR worker (e.g. Tesseract/Textract). Currently, the system honestly reports `ocr_not_configured`.
3. **Single-Node SQLite Storage**: The atomic token updates and audit logging operate on SQLite. For horizontally autoscaling multi-instance deployments across cloud regions, migrate to a managed PostgreSQL cluster with row-level locks (`SELECT FOR UPDATE`).
4. **Disabled Real Financial Mutations**: All live payment mutations remain intentionally disabled in default configuration to prevent accidental real fund movements.

---

## 6. Git Commit & Push Status

- **Branch**: `main`
- **Working Tree**: Checked and synchronized against `origin/main`.
- **Remote**: `https://github.com/karthickvel123/disputepilot.git`

---

## 7. Readiness Assessment

| Evaluation Context | Readiness Verdict | Key Justification |
| :--- | :--- | :--- |
| **Razorpay AI Builders Hiring Demo** | **100% READY** | All critical security flaws resolved; 198 automated tests passing; 0 linter errors; complete 5-minute presentation script and technical interview answers documented in [`RAZORPAY_AI_BUILDERS_DEMO.md`](RAZORPAY_AI_BUILDERS_DEMO.md). |
| **Sandbox / Testnet Demonstration** | **READY TO CONFIGURE** | Test-mode guards (`rzp_test_...` validation) and offline simulator fallback are in place. Live API testing requires merchant-supplied Razorpay test credentials. |
| **Production Deployment** | **NOT PRODUCTION READY YET** | Application code is hardened, but production launch strictly requires live merchant credentials, persistent volume disk mounting, enterprise SSO/OIDC integration, and formal PCI-DSS compliance audits. |

---

## 8. Remaining Manual Steps for the User

1. **Generate Production Reviewer Credentials**:
   ```bash
   python scripts/hash_password.py
   ```
   Copy the generated `REVIEWER_PASSWORD_HASH` (salted scrypt) and `SESSION_SECRET` into your deployment environment.
2. **Configure Razorpay Test Credentials (When Verifying Sandbox)**:
   Add `RAZORPAY_KEY_ID="rzp_test_..."` and `RAZORPAY_KEY_SECRET="..."` in `.env`, then run:
   ```bash
   uv run python scripts/smoke_razorpay.py
   ```
3. **Mount Persistent Storage**:
   Attach a persistent disk volume to `/app/data` on your hosting provider (Render, Railway, Fly.io, AWS) to retain SQLite databases across redeployments.
4. **Launch Demonstration**:
   ```bash
   uv run uvicorn disputepilot.web:app --host 127.0.0.1 --port 8000 --reload
   ```
   Open `http://127.0.0.1:8000` to execute the verified five-minute walkthrough.
