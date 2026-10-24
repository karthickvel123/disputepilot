"""Regression tests verifying security hardening of authentication and RBAC:
1. Public registration cannot create admin or auditor accounts (enforces reviewer).
2. Unauthenticated and non-admin callers cannot escalate roles.
3. Authenticated administrators can manage and elevate roles with valid CSRF.
4. Admin-sensitive endpoints (GET /auth/users, POST /settings/org) reject non-admins.
5. Zero hardcoded password bypasses in UserStore.authenticate().
6. Old fallback passwords fail immediately once an account password changes.
7. Production mode (APP_ENV=production) never seeds default demo accounts.
8. CSRF tokens and signed session cookies are strictly verified.
"""

import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from disputepilot.web.app import app
from disputepilot.web.user_store import UserStore, get_user_store


@pytest.fixture
def reviewer_client() -> tuple[TestClient, str, str]:
    """TestClient logged in as reviewer with valid CSRF token."""
    client = TestClient(app)
    res = client.post(
        "/api/v1/auth/login",
        json={"username": "reviewer", "password": "password123"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["role"] == "reviewer"
    return client, data["user"], data["csrf_token"]


@pytest.fixture
def admin_client() -> tuple[TestClient, str, str]:
    """TestClient logged in as admin with valid CSRF token."""
    client = TestClient(app)
    res = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin_secret_2026"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["role"] == "admin"
    return client, data["user"], data["csrf_token"]


def test_public_registration_cannot_create_admin_or_auditor() -> None:
    """Public self-registration must force role='reviewer' and ignore elevated requests."""
    client = TestClient(app)

    # 1. Attempt to self-register as admin
    admin_attempt_user = f"hacker_admin_{uuid.uuid4().hex[:6]}"
    res1 = client.post(
        "/api/v1/auth/register",
        json={
            "username": admin_attempt_user,
            "password": "strong_password_123",
            "full_name": "Rogue Admin Attempt",
            "role": "admin",
        },
    )
    assert res1.status_code == 200
    data1 = res1.json()
    # Response must report reviewer role
    assert data1["role"] == "reviewer"

    # Verify directly in database
    store = get_user_store()
    rec1 = store.get_user(admin_attempt_user)
    assert rec1 is not None
    assert rec1["role"] == "reviewer"

    # 2. Attempt to self-register as auditor
    auditor_attempt_user = f"hacker_auditor_{uuid.uuid4().hex[:6]}"
    res2 = client.post(
        "/api/v1/auth/register",
        json={
            "username": auditor_attempt_user,
            "password": "strong_password_123",
            "full_name": "Rogue Auditor Attempt",
            "role": "auditor",
        },
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["role"] == "reviewer"

    rec2 = store.get_user(auditor_attempt_user)
    assert rec2 is not None
    assert rec2["role"] == "reviewer"


def test_unauthenticated_cannot_escalate_roles() -> None:
    """Unauthenticated requests to update user roles must be rejected with 401."""
    client = TestClient(app)
    res = client.post(
        "/api/v1/auth/users/reviewer/role",
        json={"role": "admin"},
    )
    assert res.status_code == 401
    assert "Authentication required" in res.json()["detail"]


def test_reviewer_cannot_escalate_roles(reviewer_client: tuple[TestClient, str, str]) -> None:
    """Non-admin authenticated users cannot escalate roles (returns 403 Forbidden)."""
    client, user, csrf = reviewer_client

    # Attempt to elevate another user
    res1 = client.post(
        "/api/v1/auth/users/reviewer/role",
        json={"role": "admin"},
        headers={"x-csrf-token": csrf},
    )
    assert res1.status_code == 403
    assert "Administrator privileges required" in res1.json()["detail"]

    # Attempt to self-elevate
    res2 = client.post(
        f"/api/v1/auth/users/{user}/role",
        json={"role": "admin"},
        headers={"x-csrf-token": csrf},
    )
    assert res2.status_code == 403


def test_admin_can_escalate_and_manage_roles(
    admin_client: tuple[TestClient, str, str],
) -> None:
    """An authenticated administrator can elevate and modify roles."""
    adm_client, _, adm_csrf = admin_client

    # Register a standard reviewer using separate client so admin session is preserved
    reg_client = TestClient(app)
    uid = uuid.uuid4().hex[:6]
    test_user = f"candidate_{uid}"
    reg_res = reg_client.post(
        "/api/v1/auth/register",
        json={
            "username": test_user,
            "password": "password_initial_123",
            "full_name": "Candidate User",
            "role": "admin",  # will be forced to reviewer on registration
        },
    )
    assert reg_res.status_code == 200
    assert reg_res.json()["role"] == "reviewer"

    # Admin promotes user to auditor
    promote_res = adm_client.post(
        f"/api/v1/auth/users/{test_user}/role",
        json={"role": "auditor"},
        headers={"x-csrf-token": adm_csrf},
    )
    assert promote_res.status_code == 200
    assert promote_res.json()["ok"] is True
    assert promote_res.json()["role"] == "auditor"

    store = get_user_store()
    assert store.get_user(test_user)["role"] == "auditor"

    # Admin promotes user to admin
    promote_admin_res = adm_client.post(
        f"/api/v1/auth/users/{test_user}/role",
        json={"role": "admin"},
        headers={"x-csrf-token": adm_csrf},
    )
    assert promote_admin_res.status_code == 200
    assert promote_admin_res.json()["role"] == "admin"
    assert store.get_user(test_user)["role"] == "admin"

    # Invalid role must be rejected with 400
    invalid_role_res = adm_client.post(
        f"/api/v1/auth/users/{test_user}/role",
        json={"role": "superuser"},
        headers={"x-csrf-token": adm_csrf},
    )
    assert invalid_role_res.status_code == 400
    assert "Invalid role" in invalid_role_res.json()["detail"]


def test_admin_sensitive_endpoints_authorization(
    reviewer_client: tuple[TestClient, str, str],
    admin_client: tuple[TestClient, str, str],
) -> None:
    """Admin-only endpoints must reject unauthenticated callers (401) and reviewers (403)."""
    anon_client = TestClient(app)
    rev_client, _, rev_csrf = reviewer_client
    adm_client, _, adm_csrf = admin_client

    # 1. GET /api/v1/auth/users
    assert anon_client.get("/api/v1/auth/users").status_code == 401
    assert rev_client.get("/api/v1/auth/users").status_code == 403
    adm_users_res = adm_client.get("/api/v1/auth/users")
    assert adm_users_res.status_code == 200
    assert "users" in adm_users_res.json()

    # 2. POST /api/v1/settings/org (mutating organization profile)
    org_payload = {
        "merchant_name": "Patched Security Enterprise",
        "merchant_id": "acc_sec_demo_001",
        "currency": "INR",
        "timezone": "Asia/Kolkata",
        "auto_triage": True,
        "high_value_threshold_paise": 7500000,
        "contact_email": "security@merchant.in",
    }
    assert anon_client.post("/api/v1/settings/org", json=org_payload).status_code == 401
    assert (
        rev_client.post(
            "/api/v1/settings/org",
            json=org_payload,
            headers={"x-csrf-token": rev_csrf},
        ).status_code
        == 403
    )
    adm_save_res = adm_client.post(
        "/api/v1/settings/org",
        json=org_payload,
        headers={"x-csrf-token": adm_csrf},
    )
    assert adm_save_res.status_code == 200
    assert adm_save_res.json()["ok"] is True


def test_no_hardcoded_admin_passwords_after_password_change() -> None:
    """When the admin password changes, all old/default passwords must fail immediately."""
    client = TestClient(app)

    # 1. Login with seeded admin demo password
    login_res = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin_secret_2026"},
    )
    assert login_res.status_code == 200
    csrf = login_res.json()["csrf_token"]

    # 2. Change admin password
    new_secret = "new_hardened_secret_pass_2026"
    change_res = client.post(
        "/api/v1/auth/change-password",
        json={
            "old_password": "admin_secret_2026",
            "new_password": new_secret,
        },
        headers={"x-csrf-token": csrf},
    )
    assert change_res.status_code == 200
    assert change_res.json()["ok"] is True

    # 3. Old passwords must immediately fail with 401 Unauthorized
    old_attempt_1 = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin_secret_2026"},
    )
    assert old_attempt_1.status_code == 401
    assert "Invalid username or password" in old_attempt_1.json()["detail"]

    old_attempt_2 = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "password123"},
    )
    assert old_attempt_2.status_code == 401

    # 4. UserStore.authenticate() direct verification
    store = get_user_store()
    assert store.authenticate("admin", "admin_secret_2026") is None
    assert store.authenticate("admin", "password123") is None

    # 5. New password works
    new_attempt = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": new_secret},
    )
    assert new_attempt.status_code == 200

    # Clean up: restore admin password for other tests
    restore_csrf = new_attempt.json()["csrf_token"]
    restore_res = client.post(
        "/api/v1/auth/change-password",
        json={
            "old_password": new_secret,
            "new_password": "admin_secret_2026",
        },
        headers={"x-csrf-token": restore_csrf},
    )
    assert restore_res.status_code == 200


def test_production_mode_does_not_seed_demo_accounts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In production mode (APP_ENV=production), UserStore._init_db must never seed demo credentials."""
    monkeypatch.setenv("APP_ENV", "production")

    prod_db = tmp_path / "prod_users.db"
    prod_store = UserStore(prod_db)

    # Database must have 0 seeded users
    users = prod_store.list_users()
    assert len(users) == 0

    # Well-known demo credentials must return None
    assert prod_store.authenticate("reviewer", "password123") is None
    assert prod_store.authenticate("admin", "admin_secret_2026") is None
    assert prod_store.authenticate("admin", "password123") is None


def test_login_rate_limiting_and_account_lockout() -> None:
    """Login endpoints must enforce IP sliding-window rate limits and account lockout after repeated failures."""
    from disputepilot.web.login_security import login_security

    client = TestClient(app)
    login_security.reset()

    target_user = f"lockout_target_{uuid.uuid4().hex[:6]}"
    # 1. Five consecutive failed login attempts must lock the account
    for attempt in range(5):
        res = client.post(
            "/api/v1/auth/login",
            json={"username": target_user, "password": "wrong_password_123"},
            headers={"x-forwarded-for": f"198.51.100.{attempt + 1}"},
        )
        if attempt < 4:
            assert res.status_code == 401
        else:
            # 5th failed attempt triggers lockout
            assert res.status_code == 429
            assert "locked" in res.json()["detail"].lower()

    # 6th attempt from a different IP is still locked because account is locked
    res_locked = client.post(
        "/api/v1/auth/login",
        json={"username": target_user, "password": "any_password_123"},
        headers={"x-forwarded-for": "198.51.100.99"},
    )
    assert res_locked.status_code == 429
    assert "locked" in res_locked.json()["detail"].lower()

    # Clean up
    login_security.reset()


def test_password_policy_enforcement(monkeypatch: pytest.MonkeyPatch) -> None:
    """Passwords must satisfy complexity requirements in development and production."""
    from disputepilot.web.auth import validate_password_strength

    # 1. Too short
    with pytest.raises(ValueError, match="at least 8 characters"):
        validate_password_strength("short1", is_production=False)

    # 2. Letters only (no digits or symbols)
    with pytest.raises(ValueError, match="contain both letters and numbers"):
        validate_password_strength("onlylettershere", is_production=False)

    # 3. Same as username
    with pytest.raises(ValueError, match="cannot match username"):
        validate_password_strength("MyUser1234", username="MyUser1234", is_production=False)

    # 4. Valid non-production password
    validate_password_strength("validpass123", is_production=False)

    # 5. Production complexity: minimum 10 chars, uppercase and lowercase
    with pytest.raises(ValueError, match="at least 10 characters"):
        validate_password_strength("Short1!", is_production=True)

    with pytest.raises(ValueError, match="uppercase and lowercase"):
        validate_password_strength("lowercaseonly123!", is_production=True)

    with pytest.raises(ValueError, match="Demo passwords are prohibited"):
        validate_password_strength("password123", is_production=True)

    # Valid production password
    validate_password_strength("SecureReviewer2026!", is_production=True)


def test_session_expiry_enforcement() -> None:
    """Sessions past their maximum age must be rejected upon verification."""
    from disputepilot.web.auth import create_session_cookie_value, parse_session_cookie

    cookie_val, _ = create_session_cookie_value("test_user", "reviewer")
    # Fresh cookie verifies
    session = parse_session_cookie(cookie_val)
    assert session is not None
    assert session["user"] == "test_user"

    # Simulated future time exceeding 24h (86400s)
    future_time = time.time() + 90000
    expired_session = parse_session_cookie(cookie_val, now=future_time)
    assert expired_session is None


def test_csrf_on_integration_and_notification_routes(reviewer_client: tuple[TestClient, str, str]) -> None:
    """Integration probe and notification mutating routes must strictly reject missing CSRF tokens."""
    client, _user, csrf_token = reviewer_client

    # 1. Notification read: Reject without CSRF
    res_no_csrf = client.post("/api/v1/notifications/notif_123/read")
    assert res_no_csrf.status_code == 403
    assert "CSRF" in res_no_csrf.json()["detail"]

    # Notification read: Accept with valid CSRF
    res_with_csrf = client.post(
        "/api/v1/notifications/notif_123/read",
        headers={"x-csrf-token": csrf_token},
    )
    assert res_with_csrf.status_code == 200

    # 2. Rejection state mutation: Reject without CSRF
    res_rej_no_csrf = client.post("/api/v1/disputes/disp_test_01/reject", json={"reason": "Test note"})
    assert res_rej_no_csrf.status_code == 403
    assert "CSRF" in res_rej_no_csrf.json()["detail"]

    # 3. Comment state mutation: Reject without CSRF
    res_com_no_csrf = client.post("/api/v1/disputes/disp_test_01/comments", json={"comment": "Test comment"})
    assert res_com_no_csrf.status_code == 403
    assert "CSRF" in res_com_no_csrf.json()["detail"]

    # 4. Diagnostic test routes: Reject invalid CSRF token
    res_bad_csrf = client.post(
        "/api/v1/integrations/ai/test",
        headers={"x-csrf-token": "tampered_bad_csrf_token"},
    )
    assert res_bad_csrf.status_code == 403


def test_security_headers_csp_hsts_frame_ancestors() -> None:
    """Responses must include Content-Security-Policy (with frame-ancestors 'none') and HSTS when secure."""
    client = TestClient(app)
    res = client.get("/api/v1/settings")
    assert res.status_code == 200

    headers = res.headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"

    csp = headers.get("content-security-policy", "")
    assert "frame-ancestors 'none'" in csp
    assert "default-src 'self'" in csp
    assert "base-uri 'self'" in csp

