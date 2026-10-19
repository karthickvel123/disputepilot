"""Tests for full-stack SaaS features: user registration, dispute creation, CSV import/export,
comments, rejections, notifications, evidence download/delete, and integration diagnostics.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from disputepilot.web.app import app


@pytest.fixture
def auth_client() -> tuple[TestClient, str]:
    """TestClient logged in as reviewer with valid CSRF token."""
    client = TestClient(app)
    res = client.post(
        "/api/v1/auth/login",
        json={"username": "reviewer", "password": "password123"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    csrf_token = data["csrf_token"]
    return client, csrf_token


@pytest.fixture
def admin_client() -> tuple[TestClient, str]:
    """TestClient logged in as admin with valid CSRF token."""
    client = TestClient(app)
    res = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin_secret_2026"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["role"] == "admin"
    csrf_token = data["csrf_token"]
    return client, csrf_token


def test_user_registration_and_login() -> None:
    """A new reviewer can register, receive a session cookie, and log in."""
    client = TestClient(app)
    uid = uuid.uuid4().hex[:8]
    username = f"new_reviewer_{uid}"
    reg_res = client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "password": "secure_password_99",
            "full_name": "Test Merchant Reviewer",
            "role": "reviewer",
        },
    )
    assert reg_res.status_code == 200, reg_res.text
    reg_data = reg_res.json()
    assert reg_data["user"] == username
    assert reg_data["role"] == "reviewer"
    assert "csrf_token" in reg_data

    # Log in with the registered credentials
    login_res = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "secure_password_99"},
    )
    assert login_res.status_code == 200
    assert login_res.json()["user"] == username

    # Check /auth/me
    me_res = client.get("/api/v1/auth/me")
    assert me_res.status_code == 200
    assert me_res.json()["user"] == username


def test_change_password(auth_client: tuple[TestClient, str]) -> None:
    """Authenticated user can change their password."""
    client, _csrf = auth_client
    uid = uuid.uuid4().hex[:8]
    u = f"pw_user_{uid}"
    reg_res = client.post(
        "/api/v1/auth/register",
        json={"username": u, "password": "initial_password", "full_name": "User"},
    )
    assert reg_res.status_code == 200, reg_res.text

    # Now log in as u
    u_client = TestClient(app)
    log_res = u_client.post("/api/v1/auth/login", json={"username": u, "password": "initial_password"})
    assert log_res.status_code == 200, log_res.text
    u_csrf = log_res.json()["csrf_token"]

    chg_res = u_client.post(
        "/api/v1/auth/change-password",
        json={"old_password": "initial_password", "new_password": "new_password_123"},
        headers={"x-csrf-token": u_csrf},
    )
    assert chg_res.status_code == 200
    assert chg_res.json()["ok"] is True

    # Old password fails
    bad_login = u_client.post("/api/v1/auth/login", json={"username": u, "password": "initial_password"})
    assert bad_login.status_code == 401

    # New password succeeds
    good_login = u_client.post("/api/v1/auth/login", json={"username": u, "password": "new_password_123"})
    assert good_login.status_code == 200


def test_create_dispute_manual(auth_client: tuple[TestClient, str]) -> None:
    """Manually create a dispute case."""
    client, csrf = auth_client
    uid = uuid.uuid4().hex[:8]
    disp_id = f"disp_man_{uid}"
    try:
        res = client.post(
            "/api/v1/disputes/create",
            json={
                "dispute_id": disp_id,
                "amount_rupees": 2499.00,
                "currency": "INR",
                "reason_code": "item_not_received",
                "reason_description": "Buyer claims sneakers never arrived",
                "customer_name": "Rohan Mehra",
                "customer_email": "rohan@example.com",
                "customer_phone": "+919876543210",
                "shipping_carrier": "Delhivery",
                "tracking_number": "DEL123456789",
                "days_to_respond": 7,
            },
            headers={"x-csrf-token": csrf},
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["ok"] is True
        assert data["dispute_id"] == disp_id
        assert data["amount_paise"] == 249900

        # Verify detail is retrievable
        detail = client.get(f"/api/v1/disputes/{disp_id}")
        assert detail.status_code == 200
        assert detail.json()["dispute"]["id"] == disp_id
        assert detail.json()["order"]["customer_name"] == "Rohan Mehra"
    finally:
        from pathlib import Path
        p = Path(f"data/cases/{disp_id}.json")
        if p.exists():
            p.unlink()


def test_import_disputes_csv(auth_client: tuple[TestClient, str]) -> None:
    """Import disputes via CSV preview and execution."""
    client, csrf = auth_client
    uid = uuid.uuid4().hex[:8]
    id1 = f"disp_csv1_{uid}"
    id2 = f"disp_csv2_{uid}"

    csv_content = f"""dispute_id,amount,reason_code,reason_description,customer_name,customer_email,tracking_number
{id1},1500.00,not_as_described,Color differs from website,Ananya Sen,ananya@test.com,BD101
{id2},3200.50,unauthorised,Cardholder does not recognize charge,Vikram Roy,vikram@test.com,BD102
"""

    try:
        # Dry run preview
        dry_res = client.post(
            "/api/v1/disputes/import-csv",
            json={"csv_data": csv_content, "dry_run": True},
            headers={"x-csrf-token": csrf},
        )
        assert dry_res.status_code == 200, dry_res.text
        dry_data = dry_res.json()
        assert dry_data["dry_run"] is True
        assert dry_data["valid_count"] == 2
        assert dry_data["error_count"] == 0

        # Actual import execution
        exec_res = client.post(
            "/api/v1/disputes/import-csv",
            json={"csv_data": csv_content, "dry_run": False},
            headers={"x-csrf-token": csrf},
        )
        assert exec_res.status_code == 200
        exec_data = exec_res.json()
        assert exec_data["imported_count"] == 2
        assert exec_data["error_count"] == 0

        # Fetch imported dispute
        case_res = client.get(f"/api/v1/disputes/{id1}")
        assert case_res.status_code == 200
        assert case_res.json()["dispute"]["amount"] == 150000
    finally:
        from pathlib import Path
        for f in (Path(f"data/cases/{id1}.json"), Path(f"data/cases/{id2}.json")):
            if f.exists():
                f.unlink()


def test_export_disputes_csv(auth_client: tuple[TestClient, str]) -> None:
    """Export disputes list as downloadable CSV."""
    client, _ = auth_client
    res = client.get("/api/v1/disputes/export")
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert "case_id,amount_inr,urgency" in res.text


def test_dispute_comments(auth_client: tuple[TestClient, str]) -> None:
    """Add and list reviewer comments on a dispute."""
    client, csrf = auth_client
    case_id = "case_001"

    # Add comment
    add_res = client.post(
        f"/api/v1/disputes/{case_id}/comments",
        json={"comment": "Verified courier tracking proof with Delhivery dispatcher."},
        headers={"x-csrf-token": csrf},
    )
    assert add_res.status_code == 200, add_res.text
    add_data = add_res.json()
    assert add_data["case_id"] == case_id
    assert "Delhivery dispatcher" in add_data["comment"]

    # List comments
    list_res = client.get(f"/api/v1/disputes/{case_id}/comments")
    assert list_res.status_code == 200
    comments = list_res.json()["comments"]
    assert any("Delhivery dispatcher" in c["comment"] for c in comments)


def test_notifications_endpoint(auth_client: tuple[TestClient, str]) -> None:
    """Notifications endpoint returns active system alerts."""
    client, _ = auth_client
    res = client.get("/api/v1/notifications")
    assert res.status_code == 200
    data = res.json()
    assert "notifications" in data
    assert isinstance(data["notifications"], list)
    assert data["unread_count"] >= 1


def test_org_settings_endpoint(
    auth_client: tuple[TestClient, str], admin_client: tuple[TestClient, str]
) -> None:
    """Retrieve settings as reviewer; verify updates require admin privileges."""
    client, csrf = auth_client
    # Reviewer can read settings
    get_res = client.get("/api/v1/settings/org")
    assert get_res.status_code == 200

    # Reviewer update attempt must be rejected with 403 Forbidden
    save_attempt_rev = client.post(
        "/api/v1/settings/org",
        json={
            "merchant_name": "Unauthorized Reviewer Mutation",
            "merchant_id": "acc_test_demo_001",
            "currency": "INR",
            "timezone": "Asia/Kolkata",
            "auto_triage": True,
            "high_value_threshold_paise": 10000000,
            "contact_email": "ops@merchant.in",
        },
        headers={"x-csrf-token": csrf},
    )
    assert save_attempt_rev.status_code == 403
    assert "Administrator privileges required" in save_attempt_rev.json()["detail"]

    # Admin update succeeds
    adm_client, adm_csrf = admin_client
    save_res = adm_client.post(
        "/api/v1/settings/org",
        json={
            "merchant_name": "DisputePilot Demo Enterprise",
            "merchant_id": "acc_test_demo_001",
            "currency": "INR",
            "timezone": "Asia/Kolkata",
            "auto_triage": True,
            "high_value_threshold_paise": 10000000,
            "contact_email": "ops@merchant.in",
        },
        headers={"x-csrf-token": adm_csrf},
    )
    assert save_res.status_code == 200
    assert save_res.json()["ok"] is True
    assert save_res.json()["settings"]["merchant_name"] == "DisputePilot Demo Enterprise"


def test_integrations_test_endpoints(auth_client: tuple[TestClient, str]) -> None:
    """Integration diagnostics endpoints return valid status."""
    client, _ = auth_client
    rzp_res = client.post("/api/v1/integrations/razorpay/test")
    assert rzp_res.status_code == 200
    assert "status" in rzp_res.json()

    ai_res = client.post("/api/v1/integrations/ai/test")
    assert ai_res.status_code == 200
    assert "status" in ai_res.json()
