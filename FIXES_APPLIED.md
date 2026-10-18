# DisputePilot fixes applied

This package contains targeted reliability, security, and regression-test changes. It is still a demo/prototype and is not certified for production payment operations.

## Changes

1. **CSRF-protected logout**
   - Logout now accepts POST only and validates the active session's CSRF token.
   - The navigation logout control is a form with a CSRF token instead of a state-changing GET link.
   - Session cookie deletion retains the `HttpOnly`, `Secure` (when configured), and `SameSite=Lax` attributes.

2. **Baseline browser security headers**
   - Adds `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, a conservative `Referrer-Policy`, and a restrictive `Permissions-Policy`.

3. **Safer public demo credentials**
   - In `APP_ENV=production`, simulated mode no longer falls back to the known `reviewer` / `password123` credentials.
   - Production deployments must explicitly configure `REVIEWER_USER` and `REVIEWER_PASSWORD_HASH`.
   - Local development in `DATA_MODE=sim` keeps the demo fallback for convenience.

4. **Subscription-vs-fraud classification regression**
   - The deterministic `FakeLLMClient` baseline now checks subscription/renewal cues before generic fraud cues. This prevents phrases such as a charge after a free trial from being labeled as account takeover just because the customer says they did not give permission.
   - The real Gemini prompt still needs empirical evaluation; this change does not claim to improve production LLM accuracy by itself.

5. **Regression tests**
   - Added coverage for security headers, POST/CSRF-protected logout, production credential fallback, and the subscription-renewal classification edge case.

## Verification performed

- `python -m pytest -q -k 'not test_schema_sent_to_sdk_contains_no_additional_properties and not test_nested_pydantic_model_schema_sanitization'`: **161 passed, 2 deselected**.
- Full `python -m pytest -q`: **161 passed, 2 failed** because `google.genai` is not installed in the current execution environment. The package declares `google-genai` in `pyproject.toml`; install the project dependencies and rerun those two SDK schema tests before release.
- `python -m compileall -q src tests`: passed.
- Ruff lint was not run because Ruff is not installed in the current execution environment.
- Docker build and hosted deployment were not run.

## Before a public demo

- Set `APP_ENV=production`, `DATA_MODE=sim`, `COOKIE_SECURE=true`, a unique `SESSION_SECRET` of at least 32 characters, and explicitly generated reviewer credentials in the hosting provider's environment settings.
- Do not add live Razorpay keys to the public demo. Use synthetic case data only.
- Complete the full dependency install, run all tests and lint, build the Docker image, and smoke-test the deployed site.
- The SQLite state, in-memory approval tokens, and uploaded evidence flow are not multi-instance production persistence. Do not use this package to submit real disputes without a separate security and architecture review.
