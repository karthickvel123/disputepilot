# DisputePilot final security hardening patch

## Changes made

- **No runtime state in the ZIP or Docker image:** removed SQLite databases and generated drafts from this source archive. The Dockerfile copies only synthetic dispute fixtures and the demo organization settings, never user, approval, audit, webhook, or reminder databases.
- **Docker build context hardened:** `.dockerignore` excludes databases, generated drafts, evidence uploads, local environments, and caches.
- **Production user-store cleanup:** on production startup, the user store removes accounts only when they match the exact built-in demo username/hash combinations. If the configured reviewer uses the default demo hash, it replaces that hash with the configured password hash. User-changed passwords are preserved.
- **Setup script no longer opts into live mode:** `scripts/setup_keys.py` always writes `DATA_MODE=sim`, even if Razorpay credentials are entered. Live mode must be enabled explicitly after deliberate review.
- **No hard-coded reviewer password hash:** the setup script asks for a reviewer username and password, validates the username and password length, and creates a fresh salted scrypt hash.
- **CORS restricted:** removed broad wildcard trust for all Vercel and Render subdomains. Production allows only exact origins configured through `CORS_ALLOWED_ORIGINS`. Localhost convenience is only enabled outside production.
- **Render origin configured:** `render.yaml` sets `CORS_ALLOWED_ORIGINS=https://frontend-blue-nine-19.vercel.app`.
- **Regression coverage:** added `tests/test_deployment_hardening.py` for password hashing, safe setup mode, image packaging, CORS restrictions, and demo-account cleanup.

## Verification results

- Targeted security/deployment tests: **12 passed**.
- Python source compilation: passed.
- Full test suite: **252 passed, 2 failed** in this environment. Both failures are in `tests/test_extraction.py` and occur because `google.genai` is not installed in the execution environment. The package is declared in `pyproject.toml` and `uv.lock`; network access was unavailable to install the locked environment here.
- Docker image build and live Razorpay API calls were not run in this environment.

## Before deploying

1. Use Python 3.12 and run `uv sync --frozen` followed by `uv run pytest -q` in an environment with dependency downloads available.
2. In Render, keep `DATA_MODE=sim` until test-mode integration is verified, set `APP_ENV=production`, `REQUIRE_INDEPENDENT_APPROVAL=true`, and a strong `SESSION_SECRET`.
3. Set `CORS_ALLOWED_ORIGINS` to the exact frontend origin(s) you control.
4. Configure `REVIEWER_USER` and `REVIEWER_PASSWORD_HASH` using `python scripts/hash_password.py` or the interactive setup script. Do not commit `.env`.
5. If an older Render persistent disk already contains state, back it up and inspect it before deployment. This archive does not contain those databases, but it cannot remove existing state from a separately persisted Render disk.
6. Never put Razorpay Key Secrets or webhook secrets in Vercel/browser-visible variables or source control.

## Deployment and persistence follow-up

- **Production frontend API fallback:** production builds now default to `https://disputepilot.onrender.com/api/v1` if `VITE_API_BASE_URL` is missing; the environment variable should still be set explicitly in Vercel. Local development continues to use the Vite `/api` proxy.
- **Frontend error handling:** network failures and malformed JSON responses now produce explicit API errors instead of opaque browser exceptions. Existing HTTP status and HTML-routing mismatch handling is preserved.
- **Durable Render storage:** `render.yaml` now uses a Starter web service and a 1 GB persistent disk mounted at `/var/data/disputepilot`, with `DATA_DIR` pointing to that mount. Render's free web service tier does not support persistent disks, so this has a hosting cost; review current Render pricing before applying the blueprint.
- **Data directory safety:** startup creates `DATA_DIR`, checks write access, and fails clearly if it is not writable. On first boot only, an empty external data directory is seeded from bundled data; existing persistent files are not overwritten. The simulator now reads cases and writes drafts beneath `DATA_DIR`.
- **Reviewer setup:** the Render blueprint asks for `REVIEWER_PASSWORD_HASH` instead of silently leaving a fresh production install without a configured reviewer. Generate it locally using `python scripts/hash_password.py`; do not commit the plaintext password or generated secrets.
- **Docker dependency install:** the frontend image stage now uses `npm ci` for lockfile-reproducible installation.
- **Regression coverage:** added tests checking the production API fallback, persistent Render mount, and configured simulator storage paths.

## Follow-up verification status

- Targeted deployment/security tests after these changes: **15 passed**.
- `node --check frontend/src/api.js`: passed.
- `python -m compileall -q src scripts`: passed.
- Full backend suite: **255 passed, 2 failed** in this environment. The same two extraction tests still cannot import `google.genai` because dependency downloads are blocked in this environment. `google-genai>=2.30.1` remains declared in `pyproject.toml` and pinned in `uv.lock`; the extraction logic itself was not skipped or changed to conceal the missing dependency.
- `npm ci` and `npm run build` could not be completed here because npm registry access is unavailable and required package tarballs are not cached. The Docker build is configured to run `npm ci` and `npm run build` in a network-enabled deployment environment, but a successful production build has **not** been observed here.
- Live Vercel/Render login, persistence-after-restart, and Razorpay API submission remain deployment checks and are not claimed as verified.
