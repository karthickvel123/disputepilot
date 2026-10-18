# Deploy DisputePilot demo to Render

This guide deploys the app in **synthetic-data mode** for a public project demo. It does not connect
Razorpay live accounts or submit real disputes. Do not deploy live payment operations until the
security, persistence, and integration limitations in `LIVE_SETUP.md` have been resolved.

## 1. Push the repository to GitHub

Commit the project, including `Dockerfile` and this guide. Do not commit `.env`, API keys, passwords,
customer evidence, or generated secrets.

## 2. Create a Render web service

1. In Render, choose **New → Web Service** and connect the GitHub repository.
2. Choose **Docker** as the runtime; Render will build from `Dockerfile`.
3. Set the following environment variables in the Render dashboard:

   | Variable | Value |
   |---|---|
   | `APP_ENV` | `production` |
   | `DATA_MODE` | `sim` |
   | `COOKIE_SECURE` | `true` |
   | `REVIEWER_USER` | A demo username you choose |
   | `REVIEWER_PASSWORD_HASH` | Output from `python scripts/hash_password.py` |
   | `SESSION_SECRET` | A unique random secret of at least 32 characters |

   Generate credentials locally with `python scripts/hash_password.py` and follow its prompts/output.
   Set the resulting username/hash/secret in Render's environment settings, not in source control.
   Production simulated mode does not fall back to the default `reviewer` / `password123` credentials;
   if you omit these variables, login remains unavailable rather than exposing a known demo password.
   If the script prints both the password hash and session secret, copy those values into the matching
   environment variables. Keep the plaintext demo password only for your own demo access.

4. Deploy and wait for the service to become healthy.
5. Open the public service URL and sign in with the demo credentials you configured.

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
