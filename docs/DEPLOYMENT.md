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

### Live Production Deployments
- **Vercel Frontend**: [https://disputepilot-frontend.vercel.app](https://disputepilot-frontend.vercel.app)
- **Render Backend API**: [https://disputepilot-backend.onrender.com/api/v1/health](https://disputepilot-backend.onrender.com/api/v1/health)
- **Production Reviewer**: `ops_reviewer` / `DisputePilot#2026!Secure` (or click **⚡ Launch Demo** on the landing page)

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

### A. Tenancy Architecture: Single-Tenant Per Merchant ("One Deployment Per Merchant")
DisputePilot is designed with a strict **single-tenant isolation model**:
- **One deployment per merchant**: Each merchant organization runs in an independent container instance with its own dedicated persistent volume, encryption keys, and isolated database.
- **Cross-Tenant Leakage Prevention**: Prevents any risk of cross-merchant data leakage, shared-database corruption, or authorization bypasses for high-value financial chargebacks and evidence documents.
- **Audit Provenance**: Every table and audit ledger entry includes a `merchant_id` column to guarantee cryptographic provenance.

### B. Persistent Volume Mounting
DisputePilot stores relational data and evidence documents under `DATA_DIR` (default `/data` or `data`):
- Attach a **Persistent Disk** (Render Disk, Kubernetes PVC, or AWS EBS volume) mounted at `/data`.
- Set `DATA_DIR=/data`.
- All SQLite databases (`disputes.db`, `approvals.db`, `locker.db`, `audit.db`, `users.db`, `comments.db`) and durable evidence files (`data/evidence_files/`) reside on this volume.

### C. Automated Atomic Backups
DisputePilot includes an atomic online backup tool in `scripts/backup_restore.py`:
```bash
# Create point-in-time backup with SHA-256 manifest and SQLite integrity validation
python scripts/backup_restore.py backup --data-dir /data --dest /data/backups --merchant-id my_merchant

# Verify backup archive integrity
python scripts/backup_restore.py verify --archive /data/backups/disputepilot_backup_my_merchant_1720000000.tar.gz

# Restore from backup archive
python scripts/backup_restore.py restore --archive /data/backups/disputepilot_backup_my_merchant_1720000000.tar.gz --target-dir /data
```

### D. PostgreSQL Migration Path (via Alembic)
DisputePilot includes an Alembic migration suite for transitioning from SQLite to PostgreSQL:
```bash
# 1. Configure DATABASE_URL in .env
DATABASE_URL=postgresql://user:password@pg-host:5432/disputepilot

# 2. Preview static DDL SQL
uv run alembic upgrade head --sql

# 3. Apply schema to live PostgreSQL database
uv run alembic upgrade head
```

### E. Fail-Closed Webhooks
In production, verify that `RAZORPAY_WEBHOOK_SECRET` is set in the hosting provider's dashboard.
Configure Razorpay Webhook settings in the Razorpay Merchant Dashboard:
- **Webhook URL**: `https://<your-domain>/webhook/razorpay/webhook`
- **Active Events**: `payment.dispute.created`, `payment.dispute.under_review`, `payment.dispute.action_required`, `payment.dispute.won`, `payment.dispute.lost`, `payment.dispute.closed`
- **Secret**: Must match the `RAZORPAY_WEBHOOK_SECRET` environment variable.

### F. Docker Deployment
A production-ready Dockerfile:
```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./
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
4. **Rate Limiting & Body Limits**: Webhook receiver enforces a 256 KB body size limit and 120 req/min sliding-window rate limit.

---

## 5. Hosted demo: Render (backend) + Vercel (frontend)

1. **Backend (Render).** New + > Blueprint, select this repo. `render.yaml` provisions the Docker service, a 1 GB
   persistent disk for SQLite, and a generated `SESSION_SECRET`. A paid instance is required because free services have no disk.
2. **Frontend (Vercel).** Import the repo, set the root directory to `frontend/`, and set `VITE_API_BASE_URL` to the Render URL
   (see `frontend/.env.example`). `frontend/vercel.json` handles SPA routing.
3. **Cross-site cookies.** Set `COOKIE_SECURE=true`, `COOKIE_SAMESITE=none`, and `CORS_ALLOWED_ORIGINS` to the exact Vercel origin.
4. **Reviewer login.** Generate a hash with `python scripts/hash_password.py` and set `INITIAL_REVIEWER_USERNAME` /
   `INITIAL_REVIEWER_PASSWORD_HASH`. Turn off `DISPUTEPILOT_ALLOW_DEV_USERS` for anything public.

## 6. Running against Razorpay test mode

```bash
cp .env.example .env
python scripts/hash_password.py          # prints REVIEWER_PASSWORD_HASH and SESSION_SECRET
make smoke                               # read-only GET /v1/disputes, refuses non rzp_test_ keys
make run                                 # then open /status?check=1 for mode and config problems
```

Webhooks: expose the app (for example `ngrok http 8000`), add `https://<host>/webhook/razorpay/webhook` in the Razorpay
dashboard with the same secret as `RAZORPAY_WEBHOOK_SECRET`, and subscribe to dispute events.

## 7. Known limitations

- Binary evidence (PDF/PNG/JPEG) is attested by the reviewer, not scanned for card data. Only pasted excerpts are scanned.
- Reason classification scored 100% on the clean synthetic set and 50% on the messy set with rules only (85%+ with LLM fallback). See `evals/report.md`.
- Win probability and effort are fixed priors, not learned from outcomes.
- Whether a Razorpay test account can hold disputes is unconfirmed. `make smoke` tells you.
- SQLite is fine for single-tenant demos. Use managed Postgres for anything multi-region.
