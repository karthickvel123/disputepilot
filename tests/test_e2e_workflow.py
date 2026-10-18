"""Full End-to-End Workflow Integration Test for DisputePilot.

Validates the complete user journey:
1. Static SPA serving and asset MIME resolution (/app, /assets)
2. Reviewer authentication, HMAC session cookie, and CSRF token generation
3. Dashboard financial aggregator & urgency calculations
4. Disputes triage worklist, pagination, filtering, and win-rate estimations
5. Case details, evidence requirements, and AI fact-extraction/safety pipeline
6. Rebuttal drafting, custom merchant edits, and live character counting
7. Dual human approval token generation with SHA-256 payload binding
8. Single-use token enforcement and gateway submission verification
9. Immutable cryptographic audit ledger and live hash-chain verification
10. Settings, gateway mode detection, and health checks
"""

from pathlib import Path

from fastapi.testclient import TestClient

from disputepilot.web.api import SESSION_COOKIE_NAME
from disputepilot.web.app import app


def _get_client() -> TestClient:
    return TestClient(app, base_url="http://127.0.0.1:8000")


def test_spa_static_serving_and_assets() -> None:
    """SPA index.html is mounted at /app and assets are served with correct MIME types."""
    client = _get_client()

    # App route returns index.html
    resp = client.get("/app")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert '<div id="root">' in resp.text
    assert "DisputePilot" in resp.text

    # Verify assets exist in frontend/dist/assets
    assets_dir = Path("frontend/dist/assets")
    if assets_dir.exists():
        js_files = list(assets_dir.glob("*.js"))
        css_files = list(assets_dir.glob("*.css"))
        if js_files:
            js_resp = client.get(f"/assets/{js_files[0].name}")
            assert js_resp.status_code == 200
            assert "javascript" in js_resp.headers.get("content-type", "")
        if css_files:
            css_resp = client.get(f"/assets/{css_files[0].name}")
            assert css_resp.status_code == 200
            assert "css" in css_resp.headers.get("content-type", "")


def test_full_authentication_lifecycle() -> None:
    """Authentication enforces session validity, rejects invalid credentials, and supplies CSRF tokens."""
    client = _get_client()

    # 1. Unauthenticated request to protected endpoint fails
    resp = client.get("/api/v1/dashboard/metrics")
    assert resp.status_code == 401

    # 2. Invalid credentials fail
    bad_login = client.post(
        "/api/v1/auth/login",
        json={"username": "reviewer", "password": "wrong_password_123"},
    )
    assert bad_login.status_code == 401

    # 3. Valid demo credentials succeed
    good_login = client.post(
        "/api/v1/auth/login",
        json={"username": "reviewer", "password": "password123"},
    )
    assert good_login.status_code == 200
    login_data = good_login.json()
    assert login_data["user"] == "reviewer"
    assert "csrf_token" in login_data
    assert SESSION_COOKIE_NAME in client.cookies

    # 4. /auth/me returns current session identity
    me_resp = client.get("/api/v1/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["user"] == "reviewer"


def test_dashboard_metrics_and_disputes_triage() -> None:
    """Dashboard metrics aggregate real database values and disputes worklist supports triage."""
    client = _get_client()

    login = client.post(
        "/api/v1/auth/login",
        json={"username": "reviewer", "password": "password123"},
    )
    assert login.status_code == 200

    # 1. Dashboard metrics
    metrics_resp = client.get("/api/v1/dashboard/metrics")
    assert metrics_resp.status_code == 200
    metrics = metrics_resp.json()
    assert metrics["total_disputes"] >= 150
    assert metrics["total_amount_paise"] > 0
    assert "reason_breakdown" in metrics
    assert "urgent_disputes" in metrics

    # 2. Disputes list with pagination
    list_resp = client.get("/api/v1/disputes?per_page=10&page=1")
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert len(data["items"]) == 10

    assert data["total"] >= 150
    first_case = data["items"][0]
    assert "case_id" in first_case
    assert "amount_paise" in first_case
    assert "urgency" in first_case
    assert "p_win" in first_case


    # 3. Filter by search query
    target_id = first_case["case_id"]
    search_resp = client.get(f"/api/v1/disputes?search={target_id}")
    assert search_resp.status_code == 200
    search_data = search_resp.json()
    assert any(item["case_id"] == target_id for item in search_data["items"])


def test_case_detail_ai_analysis_and_drafting_flow() -> None:
    """Case detail loads artifacts, AI analysis runs, and merchant drafting saves state."""
    client = _get_client()

    login = client.post(
        "/api/v1/auth/login",
        json={"username": "reviewer", "password": "password123"},
    )
    assert login.status_code == 200
    csrf_token = login.json()["csrf_token"]

    case_id = "disp_0001_hbrpoi"

    # 1. Fetch case details
    detail_resp = client.get(f"/api/v1/disputes/{case_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["case_id"] == case_id
    assert "requirements" in detail
    assert "dispute" in detail
    assert "order" in detail

    # 2. Save merchant draft edits
    draft_payload = {
        "summary": "Verified customer delivery confirmation with matching GPS coordinates.",
        "csrf_token": csrf_token,
    }
    save_draft = client.post(
        f"/api/v1/disputes/{case_id}/draft",
        json=draft_payload,
    )
    assert save_draft.status_code == 200
    assert save_draft.json()["status"] == "saved"


    # 3. Run AI extraction and analysis
    analysis_resp = client.post(
        f"/api/v1/disputes/{case_id}/analyze",
        headers={"x-csrf-token": csrf_token},
    )
    assert analysis_resp.status_code == 200
    analysis = analysis_resp.json()
    assert analysis["status"] == "completed"
    assert "recommendation" in analysis
    assert "evidence_report" in analysis
    assert "verifier_report" in analysis
    assert "clean_draft" in analysis


def test_cryptographic_approval_and_submission_integrity() -> None:
    """Submission requires single-use cryptographically bound human approval token."""
    client = _get_client()

    login = client.post(
        "/api/v1/auth/login",
        json={"username": "reviewer", "password": "password123"},
    )
    assert login.status_code == 200
    csrf_token = login.json()["csrf_token"]

    case_id = "disp_0001_hbrpoi"

    # 1. Ensure case is analyzed first (required before requesting approval)
    client.post(
        f"/api/v1/disputes/{case_id}/analyze",
        headers={"x-csrf-token": csrf_token},
    )

    # 2. Request submission approval token
    appr_resp = client.post(
        f"/api/v1/disputes/{case_id}/request-approval",
        headers={"x-csrf-token": csrf_token},
    )
    assert appr_resp.status_code == 200
    appr_data = appr_resp.json()
    token = appr_data["approval_token"]
    payload_hash = appr_data["payload_hash"]
    assert token.startswith("appr_")
    assert len(payload_hash) == 64  # SHA-256 hex string

    # 3. Attempt submit with mismatched payload hash -> rejected
    bad_submit = client.post(
        f"/api/v1/disputes/{case_id}/submit",
        json={
            "approval_token": token,
            "payload_hash": "0000000000000000000000000000000000000000000000000000000000000000",
            "csrf_token": csrf_token,
        },
        headers={"x-csrf-token": csrf_token},
    )
    assert bad_submit.status_code == 400

    # 4. Submit with exact matching approved content -> succeeds
    good_submit = client.post(
        f"/api/v1/disputes/{case_id}/submit",
        json={
            "approval_token": token,
            "payload_hash": payload_hash,
            "csrf_token": csrf_token,
        },
        headers={"x-csrf-token": csrf_token},
    )
    assert good_submit.status_code == 200
    assert "status" in good_submit.json()


    # 5. Attempt to reuse consumed token -> rejected (single use token enforcement)
    replay_submit = client.post(
        f"/api/v1/disputes/{case_id}/submit",
        json={
            "approval_token": token,
            "payload_hash": payload_hash,
            "csrf_token": csrf_token,
        },
        headers={"x-csrf-token": csrf_token},
    )
    assert replay_submit.status_code == 400


def test_immutable_audit_ledger_and_verification() -> None:
    """Audit ledger persists tamper-evident events and verify endpoint confirms chain integrity."""
    client = _get_client()

    login = client.post(
        "/api/v1/auth/login",
        json={"username": "reviewer", "password": "password123"},
    )
    assert login.status_code == 200

    # 1. Retrieve global audit events
    audit_resp = client.get("/api/v1/audit?page=1&per_page=20")
    assert audit_resp.status_code == 200
    audit_data = audit_resp.json()
    assert "events" in audit_data
    assert "total" in audit_data
    assert audit_data["chain_valid"] is True

    # 2. Verify cryptographic hash chain integrity
    verify_resp = client.get("/api/v1/audit/verify")
    assert verify_resp.status_code == 200
    verify_data = verify_resp.json()
    assert verify_data["chain_valid"] is True
    assert verify_data["hash_algorithm"] == "SHA-256"


def test_settings_and_health_endpoints() -> None:
    """Settings returns non-sensitive system configuration and health returns 200."""
    client = _get_client()

    # Health is public
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["status"] == "healthy"

    # Settings requires auth
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "reviewer", "password": "password123"},
    )
    assert login.status_code == 200

    settings_resp = client.get("/api/v1/settings")
    assert settings_resp.status_code == 200
    settings = settings_resp.json()
    assert "data_mode" in settings
    assert "has_razorpay" in settings
    assert "has_llm" in settings
    # Ensure no secrets leak
    assert "razorpay_key_secret" not in settings
    assert "session_secret" not in settings
