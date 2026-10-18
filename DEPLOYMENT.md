# DisputePilot — Production & Sandbox Deployment Guide

This guide describes how to configure, test, and deploy DisputePilot safely across local development, sandbox demonstration, and production cloud environments (Render, Railway, Fly.io, AWS, or Docker).

---

## 1. Quick Start (Local Development & Simulation)

DisputePilot includes a complete local dispute simulator and sandbox test cases requiring zero external cloud credentials to run.

### Prerequisites
- Python 3.12+ installed
- `uv` package manager (`curl -LsSf https://astral.sh/uv/install.sh | sh` or `pip install uv`)

### Step-by-Step Installation
```bash
# 1. Clone repository
git clone https://github.com/karthickvel123/disputepilot.git
cd disputepilot

# 2. Sync dependencies using lockfile
uv sync

# 3. Initialize SQLite database & directories
mkdir -p data/drafts data/cases
uv run python -c "from disputepilot.razorpay.approval import init_db; init_db('data/disputepilot.db')"

# 4. Start local development server
uv run uvicorn disputepilot.web:app --host 127.0.0.1 --port 8000 --reload
```

Open `http://127.0.0.1:8000` in your web browser. Default local reviewer credentials:
- **Username**: `reviewer`
- **Password**: `password123`

---

## 2. Configuration & Environment Variables

All configuration is managed cleanly through environment variables, validated by Pydantic settings.

| Variable Name | Default Value | Required In Prod? | Description / Security Guidance |
| :--- | :--- | :--- | :--- |
| `APP_ENV` | `development` | **YES** | Set to `production` in live deployments. Disables insecure fallback credentials. |
| `DATA_MODE` | `sim` | **YES** | `sim` (uses local synthetic cases in `data/cases`) or `live` (calls real Razorpay API). |
| `SESSION_SECRET` | `insecure_dev_secret_replace...` | **YES** | Minimum 32-character high-entropy secret for HMAC session signing. |
| `COOKIE_SECURE` | `false` | **YES** | Set to `true` in production to enforce HTTPS-only session cookies. |
| `DATABASE_PATH` | `data/disputepilot.db` | No | Path to SQLite database file. Ensure persistent volume storage is attached. |
| `RAZORPAY_KEY_ID` | `""` | Only in `live` mode | Razorpay Key ID (`rzp_live_...` or `rzp_test_...`). |
| `RAZORPAY_KEY_SECRET` | `""` | Only in `live` mode | Razorpay Key Secret. Never commit to git or expose to frontend. |
| `RAZORPAY_WEBHOOK_SECRET` | `""` | Only in `live` mode | Secret used for HMAC-SHA256 signature verification of webhook events. |
| `GEMINI_API_KEY` | `""` | No | Google Gemini API Key for LLM classification and structured extraction. |
| `REVIEWER_USER` | `reviewer` | **YES** (in Prod) | Designated reviewer username for Tier 4 approvals. |
| `REVIEWER_PASSWORD_HASH` | (demo hash) | **YES** (in Prod) | Salted scrypt hash (`salt.hex():key.hex()`). Generate with `python scripts/hash_password.py`. |

### Secure Credential Generation
To generate a production reviewer hash and session secret, run:
```bash
python scripts/hash_password.py
# Or in Python:
python -c "from disputepilot.web.auth import hash_password; print(hash_password('YourStrongPasswordHere'))"
```
*DisputePilot uses memory-hard salted `hashlib.scrypt` (N=16384, r=8, p=1) with a 16-byte cryptographically random salt to resist GPU/ASIC rainbow-table attacks. Legacy unsalted SHA-256 is supported only as a backward-compatible fallback for existing dev setups.*

---

## 3. Verification & Testing Commands

Always run the full test suite and linter before deploying any release:

```bash
# 1. Run complete unit, integration, and security regression test suite
uv run pytest

# 2. Run Ruff linter and static code check
uv run ruff check src tests

# 3. Run empirical evaluation harness
uv run python -m disputepilot.evals.runner

# 4. Run adversarial security test suite specifically
uv run pytest tests/test_security_concurrency.py tests/test_webhook_security.py
```

---

## 4. Production Deployment Best Practices

### A. Persistent Volume Mounting
DisputePilot uses SQLite for high-performance, single-node transactional data storage (audit logs, approval tokens, webhook deduplication). When deploying on containerized platforms (e.g. Render, Railway, Fly.io, AWS ECS):
- Attach a **Persistent Disk** mounted at `/app/data`.
- Set `DATABASE_PATH=/app/data/disputepilot.db`.
- This ensures tokens and audit logs persist across container restarts and zero-downtime redeployments.

### B. Fail-Closed Webhooks
In production, verify that `RAZORPAY_WEBHOOK_SECRET` is set in the hosting provider's dashboard.
Configure Razorpay Webhook settings in the Razorpay Merchant Dashboard:
- **Webhook URL**: `https://<your-domain>/api/v1/razorpay/webhook`
- **Active Events**: `dispute.created`, `dispute.won`, `dispute.lost`, `dispute.closed`, `dispute.under_review`
- **Secret**: Must match the `RAZORPAY_WEBHOOK_SECRET` environment variable.

### C. Docker Deployment
A production-ready Dockerfile:
```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY src ./src
COPY data/cases ./data/cases

ENV APP_ENV=production \
    DATA_MODE=sim \
    COOKIE_SECURE=true \
    PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "disputepilot.web:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 5. Safe Mode & Circuit Breakers

1. **Simulator Mode Safety**: In `DATA_MODE=sim`, the gateway strictly intercepts all calls via `SimGateway`. Zero network traffic reaches `api.razorpay.com`.
2. **Approval Gate Circuit Breaker**: No dispute can be submitted or accepted without a single-use approval token.
3. **Idempotency Protection**: Every mutation request sent to Razorpay sends dual idempotency headers and performs pre-retry dispute status queries to prevent duplicate processing.
