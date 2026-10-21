# Deploying DisputePilot: Frontend to Vercel & Backend to Render

This guide provides the complete, production-ready procedure to deploy **DisputePilot**:
- **Backend**: Deployed to **Render** as a high-performance Docker web service.
- **Frontend**: Deployed to **Vercel** as a high-speed React SPA with client routing.

---

## Architecture & Authentication Overview

DisputePilot operates a decoupled full-stack architecture:
```
┌─────────────────────────────────┐           ┌─────────────────────────────────┐
│     Vercel Frontend (SPA)       │   CORS    │     Render Backend (FastAPI)    │
│  https://disputepilot.vercel.app├──────────►│ https://disputepilot.onrender   │
│  - React 19 + Vite 6            │Credentials│ - Python 3.12 + Docker          │
│  - Tailwind CSS Fintech Design  │           │ - Deterministic Rules Engine    │
│  - Session & CSRF Bearer State  │           │ - Gemini AI Rebuttal Engine     │
└─────────────────────────────────┘           └─────────────────────────────────┘
```

- **Cross-Site Cookie Handling**: Configured with `SameSite=None` and `Secure=True` when `COOKIE_SECURE=true` in production, allowing seamless session cookie persistence across decoupled domains.
- **CSRF Protection**: Every state-changing API call includes the session-bound `X-CSRF-Token` header.
- **Fail-Safe Defaults**: If external payment credentials are not supplied, DisputePilot runs in `DATA_MODE=sim` with synthetic scheme fixtures, allowing evaluators and reviewers to explore the entire workflow without risk.

---

## Step 1: Deploy Backend to Render

### Option A: Render Blueprint (Recommended - 1-Click)
1. Go to the [Render Dashboard](https://dashboard.render.com/) and click **New +** → **Blueprint**.
2. Connect your GitHub repository: `https://github.com/karthickvel123/disputepilot`.
3. Render will detect `render.yaml` and configure:
   - **Service Name**: `disputepilot-backend`
   - **Environment**: `Docker`
   - **Health Check Path**: `/api/v1/health`
   - **Auto-generated Secrets**: `SESSION_SECRET`
4. Click **Apply**.

---

### Option B: Manual Web Service Setup
1. On the Render Dashboard, click **New +** → **Web Service**.
2. Select your repository: `karthickvel123/disputepilot`.
3. Fill in the service configuration:
   - **Name**: `disputepilot-backend`
   - **Region**: `Oregon (US West)` or nearest to your users
   - **Branch**: `main`
   - **Runtime**: `Docker`
   - **Dockerfile Path**: `./Dockerfile`
   - **Health Check Path**: `/api/v1/health`
4. Add the following **Environment Variables**:

| Variable | Recommended Value | Purpose |
|---|---|---|
| `APP_ENV` | `production` | Enables production security guards |
| `DATA_MODE` | `sim` (or `live`) | `sim` for demo evaluation; `live` for Razorpay API |
| `COOKIE_SECURE` | `true` | Enforces HTTPS-only secure cookies |
| `COOKIE_SAMESITE` | `none` | Allows cross-origin cookies between Vercel & Render |
| `SESSION_SECRET` | *(Click "Generate" or random 32+ hex)* | HMAC key for signing session tokens |
| `INITIAL_REVIEWER_USERNAME` | `reviewer` | Production reviewer username |
| `INITIAL_REVIEWER_PASSWORD_HASH` | *(Generate using script below)* | Salted scrypt hash for the initial reviewer |
| `GEMINI_API_KEY` | *(Optional)* | Enables Google Gemini 2.5 AI drafting |
| `RAZORPAY_KEY_ID` | `rzp_test_...` *(Optional)* | Razorpay test key |
| `RAZORPAY_KEY_SECRET` | `...` *(Optional)* | Razorpay test secret |
| `RAZORPAY_WEBHOOK_SECRET` | `...` *(Optional)* | Razorpay webhook secret |

#### Generating Production Reviewer Password Hash:
Run locally in your terminal:
```bash
uv run python scripts/hash_password.py
# Or with standard python:
python scripts/hash_password.py
```
Copy the generated hash string into `INITIAL_REVIEWER_PASSWORD_HASH`.

5. Click **Create Web Service**. Once deployed, copy your Render URL (e.g., `https://disputepilot-backend.onrender.com`).

---

## Step 2: Deploy Frontend to Vercel

1. Log in to the [Vercel Dashboard](https://vercel.com/) and click **Add New...** → **Project**.
2. Select and import your GitHub repository: `karthickvel123/disputepilot`.
3. Configure the project:
   - **Framework Preset**: `Vite`
   - **Root Directory**: Leave as `./` (or select `frontend`)
   - **Build Command**: `cd frontend && npm install && npm run build` (handled automatically by `vercel.json`)
   - **Output Directory**: `frontend/dist` (or `dist` if root directory is set to `frontend`)
4. In **Environment Variables**, add:
   - **Key**: `VITE_API_BASE_URL`
   - **Value**: `https://disputepilot.onrender.com/api/v1` *(replace with your actual Render service URL if different)*
5. Click **Deploy**.

---

## Step 3: Verify Live Deployment

1. **Verify Backend Health**:
   Open in your browser:
   `https://YOUR-RENDER-APP.onrender.com/api/v1/health`
   Expected response:
   ```json
   {"status":"healthy","timestamp":1792422258,"version":"0.2.0"}
   ```

2. **Verify Frontend & End-to-End Auth**:
   - Open your Vercel URL: `https://YOUR-VERCEL-APP.vercel.app`
   - Click **⚡ Launch Interactive Demo (1-Click)** or open the login modal and click **⚡ Reviewer Access**.
   - Confirm you are logged in and routed to the **Dashboard** with active metrics.
   - Go to **Worklist**, select a dispute (e.g. `disp_1001`), and click **Analyze with Gemini**.
   - Check the **PCI-DSS Shield** indicator and verify that the bank rebuttal draft is synthesized.
   - Click **+ Simulate Dispute** in the navigation bar to test live dispute creation and triage!

---

## Step 4: Configuring Razorpay Webhooks (Optional)

If you are running in `DATA_MODE=live` with test mode keys:
1. Open the [Razorpay Dashboard](https://dashboard.razorpay.com/) in **Test Mode**.
2. Navigate to **Account & Settings** → **Webhooks** → **Add New Webhook**.
3. Set the Webhook URL to:
   `https://YOUR-RENDER-APP.onrender.com/webhook/razorpay`
4. Set the **Secret** to match `RAZORPAY_WEBHOOK_SECRET` from your Render environment variables.
5. Subscribe to the following active events:
   - `dispute.created`
   - `dispute.won`
   - `dispute.lost`
   - `dispute.closed`
   - `dispute.under_review`
6. Click **Save Webhook**.

**Reviewer login:** generate a password hash locally with `python scripts/hash_password.py` and set it as Render `REVIEWER_PASSWORD_HASH`. Never commit the plaintext password.
