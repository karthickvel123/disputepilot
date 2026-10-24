"""Tests for DisputePilot REST API endpoints."""

import time

import pytest
from fastapi.testclient import TestClient

from disputepilot.pipeline.orchestrator import process_case
from disputepilot.web import api as web_api
from disputepilot.web.app import app, gateway
from disputepilot.web.auth import (
    SESSION_COOKIE_NAME,
    create_session_cookie_value,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def auth_client() -> tuple[TestClient, str]:
    c = TestClient(app)
    cookie_val, csrf_token = create_session_cookie_value(user="Priya Sharma")
    c.cookies.set(SESSION_COOKIE_NAME, cookie_val)
    return c, csrf_token


@pytest.fixture
def sample_case_id() -> str:
    c_id = "disp_0001_hbrpoi"
    process_case(case_id=c_id, gateway=gateway)
    return c_id


def test_api_health(client: TestClient) -> None:
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "version" in data


def test_api_me_requires_auth(client: TestClient) -> None:
    res = client.get("/api/v1/auth/me")
    assert res.status_code == 401


def test_api_me_authenticated(auth_client: tuple[TestClient, str]) -> None:
    c, csrf = auth_client
    res = c.get("/api/v1/auth/me")
    assert res.status_code == 200
    data = res.json()
    assert data["user"] == "Priya Sharma"
    assert data["csrf_token"] == csrf


def test_api_dashboard_metrics(auth_client: tuple[TestClient, str]) -> None:
    c, _ = auth_client
    res = c.get("/api/v1/dashboard/metrics")
    assert res.status_code == 200
    data = res.json()
    assert "total_disputes" in data
    assert "open_disputes" in data
    assert "urgent_disputes" in data
    assert "reason_breakdown" in data
    assert "amount_at_risk_paise" in data
    assert 0 <= data["amount_at_risk_paise"] <= data["total_amount_paise"]
    assert sum(data["reason_breakdown"].values()) == data["total_disputes"]
    assert data["data_mode"] in ("sim", "live")


def test_api_list_disputes(auth_client: tuple[TestClient, str]) -> None:
    c, _ = auth_client
    res = c.get("/api/v1/disputes?page=1&per_page=10")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert data["page"] == 1
    if data["items"]:
        item = data["items"][0]
        assert "case_id" in item
        assert "amount_paise" in item
        assert "urgency" in item
        assert "recommendation" in item


def test_api_list_disputes_urgent_filter(
    auth_client: tuple[TestClient, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c, _ = auth_client
    fixed_now = int(time.time())
    monkeypatch.setattr(web_api.time, "time", lambda: fixed_now)
    all_res = c.get("/api/v1/disputes?page=1&per_page=200")
    urgent_res = c.get("/api/v1/disputes?page=1&per_page=200&status_filter=urgent")

    assert all_res.status_code == 200
    assert urgent_res.status_code == 200
    all_items = all_res.json()["items"]
    expected_urgent_ids = {
        item["case_id"]
        for item in all_items
        if item["hours_remaining"] is not None and item["hours_remaining"] <= 48
    }
    actual_urgent_ids = {
        item["case_id"] for item in urgent_res.json()["items"]
    }
    assert actual_urgent_ids == expected_urgent_ids


def test_api_dispute_detail(auth_client: tuple[TestClient, str], sample_case_id: str) -> None:
    c, _ = auth_client
    res = c.get(f"/api/v1/disputes/{sample_case_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["case_id"] == sample_case_id
    assert "dispute" in data
    assert "deadline" in data
    assert "requirements" in data
    assert "safety_findings" in data


def test_api_save_draft(auth_client: tuple[TestClient, str], sample_case_id: str) -> None:
    c, csrf = auth_client
    res = c.post(
        f"/api/v1/disputes/{sample_case_id}/draft",
        json={"summary": "Updated rebuttal argument with delivery proof.", "csrf_token": csrf},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "saved"


def test_api_request_approval_and_submit(
    auth_client: tuple[TestClient, str], sample_case_id: str
) -> None:
    c, csrf = auth_client
    # 1. Request approval token
    res = c.post(
        f"/api/v1/disputes/{sample_case_id}/request-approval",
        headers={"x-csrf-token": csrf},
    )
    assert res.status_code == 200
    data = res.json()
    token = data["approval_token"]
    payload_hash = data["payload_hash"]
    assert token.startswith("appr_")

    # 2. Submit contest
    sub_res = c.post(
        f"/api/v1/disputes/{sample_case_id}/submit",
        json={
            "approval_token": token,
            "payload_hash": payload_hash,
            "csrf_token": csrf,
        },
    )
    assert sub_res.status_code == 200
    sub_data = sub_res.json()
    assert sub_data["status"] in ("open", "under_review", "submitted")


def test_api_request_accept_and_accept(
    auth_client: tuple[TestClient, str], sample_case_id: str
) -> None:
    c, csrf = auth_client
    # Get dispute amount
    det = c.get(f"/api/v1/disputes/{sample_case_id}").json()
    amount_rupees = det["dispute"]["amount"] / 100.0

    # 1. Request accept token with typed amount
    res = c.post(
        f"/api/v1/disputes/{sample_case_id}/request-accept",
        json={"typed_amount": str(amount_rupees), "csrf_token": csrf},
    )
    assert res.status_code == 200
    data = res.json()
    token = data["approval_token"]
    payload_hash = data["payload_hash"]
    assert token.startswith("appr_")

    # 2. Accept dispute
    acc_res = c.post(
        f"/api/v1/disputes/{sample_case_id}/accept",
        json={
            "approval_token": token,
            "payload_hash": payload_hash,
            "csrf_token": csrf,
        },
    )
    assert acc_res.status_code == 200
    assert acc_res.json()["status"] in ("open", "lost", "closed")



def test_api_audit_and_verification(
    auth_client: tuple[TestClient, str], sample_case_id: str
) -> None:
    c, _ = auth_client
    # Case audit
    res = c.get(f"/api/v1/disputes/{sample_case_id}/audit")
    assert res.status_code == 200
    assert "events" in res.json()
    assert res.json()["chain_valid"] is True

    # Global audit
    g_res = c.get("/api/v1/audit?page=1&per_page=10")
    assert g_res.status_code == 200
    assert "events" in g_res.json()
    assert "total" in g_res.json()

    # Verification
    v_res = c.get("/api/v1/audit/verify")
    assert v_res.status_code == 200
    assert v_res.json()["chain_valid"] is True


def test_api_settings(auth_client: tuple[TestClient, str]) -> None:
    c, _ = auth_client
    res = c.get("/api/v1/settings")
    assert res.status_code == 200
    data = res.json()
    assert "data_mode" in data
    assert "evidence_categories" in data


def test_spa_served(client: TestClient) -> None:
    res = client.get("/app")
    assert res.status_code == 200
    assert "DisputePilot" in res.text
    assert "root" in res.text
