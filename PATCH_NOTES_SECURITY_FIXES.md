# DisputePilot safety fixes

This patch makes the default configuration safer for local development and public demos.

## Changes

- **Safe mode default:** when `DATA_MODE` is not set, DisputePilot now uses `sim` even if Razorpay credentials are present. Real Razorpay API access requires explicitly setting `DATA_MODE=live`.
- **Production approval separation:** `REQUIRE_INDEPENDENT_APPROVAL` defaults to `true` when `APP_ENV=production` or `prod`. Set it explicitly only when you have a documented reason to override the default.
- **Session key fallback:** the fixed development session key is no longer used in production. Set a strong `SESSION_SECRET` in Render; otherwise a process-ephemeral key is used and sessions will not survive restarts.
- **Render blueprint:** independent approval is enabled by default in `render.yaml`.
- **Dependency clarification:** `google-genai` was already declared in `pyproject.toml` and pinned in `uv.lock`; the previous `google.genai` test failure indicates that the test environment had not installed the project's declared dependencies. Use `uv sync --frozen` before running tests.
- **Regression tests:** added checks for safe mode default and production approval default.

## Verification

The automated test suite could not be run in this execution environment because `uv sync --frozen` needed to download the Python 3.12 runtime from GitHub and network access was unavailable. This patch is therefore **not claimed as fully test-passing**. Run the following in an environment with network access and Python 3.12 available:

```bash
uv sync --frozen
uv run pytest -q
```

For Render, verify the environment variables include `APP_ENV=production`, `DATA_MODE=sim`, `REQUIRE_INDEPENDENT_APPROVAL=true`, and a strong `SESSION_SECRET`. Keep Razorpay secrets only in Render environment variables, never in the ZIP or frontend environment.
