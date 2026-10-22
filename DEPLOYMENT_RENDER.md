# Deploy DisputePilot demo to Render

This guide deploys the app in **synthetic-data mode** for a public project demo. It does not connect
Razorpay live accounts or submit real disputes. Do not deploy live payment operations until the
security, persistence, and integration limitations in `LIVE_SETUP.md` have been resolved.

## 1. Push the repository to GitHub

Commit the project, including `Dockerfile` and this guide. Do not commit `.env`, API keys, passwords,
customer evidence, or generated secrets.

## 2. Deploy via Render Blueprint or Web Service

### Option A: Automatic Blueprint Deployment (Recommended for Demo)
DisputePilot includes a `render.yaml` blueprint. In Render:
1. Click **New +** → **Blueprint**.
2. Select this repository.
3. Render automatically provisions the Docker service with the persistent 1GB disk and configured environment variables (`APP_ENV=staging`, `DATA_MODE=sim`).
4. Click **Apply**.
5. Once deployed, reviewers can log in with:
   - **Username**: `reviewer`
   - **Password**: `password123`

### Option B: Manual Web Service Setup
1. In Render, choose **New → Web Service** and connect the GitHub repository.
2. Choose **Docker** as the runtime; Render builds from `Dockerfile`.
3. Set the following environment variables in the Render dashboard:

   | Variable | Demo Showcase Value | Live Production Value |
   |---|---|---|
   | `APP_ENV` | `staging` | `production` |
   | `DATA_MODE` | `sim` | `live` |
   | `COOKIE_SECURE` | `true` | `true` |
   | `REVIEWER_USER` | `reviewer` | A dedicated admin username |
   | `REVIEWER_PASSWORD_HASH` | (omitted or demo) | Salted scrypt hash from `scripts/hash_password.py` |
   | `SESSION_SECRET` | (auto-generated) | Cryptographic 32+ char hex secret |

4. Deploy and wait for the service to become healthy (`/api/v1/health`).
5. Open the public service URL and sign in.

## 3. Verify the deployment

- Confirm the site shows the **SIMULATED DATA** banner.
- Open a sample dispute and test analysis, evidence checks, and rebuttal drafting.
- Confirm the login cookie is `Secure`, `HttpOnly`, and `SameSite=Lax` in browser developer tools.
- Try an invalid login and confirm access is not granted.
- Do not enter real cardholder or customer data.

## Important limitations

- Render's container filesystem is ephemeral unless a persistent disk is configured. This demo should be
  treated as disposable; local audit/locker state may be lost after a restart or redeploy.
- Approval tokens are persisted in `data/approvals.db` alongside the audit log and locker databases (mount a persistent disk to preserve across redeploys).
- The app does not scan uploaded PDF/image bytes for payment card data; only use synthetic files and
  respect the application's reviewer attestation flow.
- Do not set `DATA_MODE=live` or add live Razorpay keys for a public showcase deployment.
