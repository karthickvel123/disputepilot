"""Regression tests for audit bug fixes:
1. CSV import casing normalization and storage routing.
2. Dynamic data_dir persistent storage routing (metrics, list, export, notifications, org settings).
3. Path traversal protection on comments and rejection endpoints.
4. Clean 400 Bad Request responses on ValueError (empty comments, short passwords).
5. AI connection diagnostic probing via generate_json.
6. Live mode dispute CSV export.
7. Shared evidence file retention on deletion.
"""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from disputepilot.config import Settings
from disputepilot.core.models import (
    DisputeCase,
    DisputePhase,
    DisputeStatus,
    Order,
    RazorpayDispute,
)
from disputepilot.live.locker import EvidenceLocker
from disputepilot.razorpay.approval import ApprovalService
from disputepilot.web.api import configure_api
from disputepilot.web.app import app
from disputepilot.web.auth import SESSION_COOKIE_NAME, create_session_cookie_value
from disputepilot.web.user_store import get_user_store


@pytest.fixture
def audit_env(tmp_path):
    """Set up temporary directory, locker, user store, and settings."""
    data_dir = tmp_path / "persistent_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    cases_dir = data_dir / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)
    drafts_dir = data_dir / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir = data_dir / "evidence_files"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    locker_db = data_dir / "locker.db"
    locker = EvidenceLocker(locker_db)

    approvals_db = data_dir / "approvals.db"
    approval_svc = ApprovalService(db_path=approvals_db)

    # Initialize user store in data_dir
    user_store = get_user_store(data_dir=data_dir)
    user_store.create_user("test_reviewer", "password123", full_name="Test Reviewer", role="reviewer")
    user_store.create_user("test_admin", "adminpass123", full_name="Test Admin", role="admin")

    settings = Settings(
        data_mode="sim",
        data_dir=data_dir,
        session_secret="s" * 32,
        cookie_secure=False,
        require_independent_approval=False,
    )

    import disputepilot.web.api as api_mod

    orig_state = {
        "settings": api_mod._settings,
        "gateway": api_mod._gateway,
        "live_source": api_mod._live_source,
        "llm_client": api_mod._llm_client,
        "approval_service": api_mod._approval_service,
        "locker": api_mod._locker,
        "razorpay_problems": api_mod._razorpay_problems,
        "auth_problems": api_mod._auth_problems,
    }

    configure_api(
        settings=settings,
        gateway=None,
        live_source=None,
        llm_client=None,
        approval_service=approval_svc,
        locker=locker,
    )

    client = TestClient(app)
    try:
        yield {
            "client": client,
            "data_dir": data_dir,
            "cases_dir": cases_dir,
            "drafts_dir": drafts_dir,
            "evidence_dir": evidence_dir,
            "locker": locker,
            "approval_svc": approval_svc,
            "settings": settings,
            "user_store": user_store,
        }
    finally:
        configure_api(
            settings=orig_state["settings"],
            gateway=orig_state["gateway"],
            live_source=orig_state["live_source"],
            llm_client=orig_state["llm_client"],
            approval_service=orig_state["approval_service"],
            locker=orig_state["locker"],
            razorpay_problems=orig_state["razorpay_problems"],
            auth_problems=orig_state["auth_problems"],
        )


def _login_client(client: TestClient, username: str = "test_reviewer", role: str = "reviewer") -> dict[str, str]:
    cookie_val, csrf = create_session_cookie_value(user=username, role=role)
    client.cookies.set(SESSION_COOKIE_NAME, cookie_val)
    return {"x-csrf-token": csrf}


def _create_test_case(case_id: str, cases_dir: Path, hours_left: float = 12.0) -> DisputeCase:
    now = int(time.time())
    respond_by = int(now + (hours_left * 3600))
    disp = RazorpayDispute(
        id=case_id,
        payment_id=f"pay_{case_id}",
        amount=250000,
        currency="INR",
        amount_deducted=250000,
        reason_code="fraud",
        reason_description="Cardholder disputes charge as unauthorized",
        phase=DisputePhase.CHARGEBACK,
        status=DisputeStatus.OPEN,
        respond_by=respond_by,
        created_at=now - 86400,
    )
    order = Order(
        id=f"order_{case_id}",
        amount=250000,
        currency="INR",
        status="paid",
        created_at=now - 90000,
    )
    case = DisputeCase(
        case_id=case_id,
        dispute=disp,
        order=order,
        metadata={"source": "test"},
    )
    case_path = cases_dir / f"{case_id}.json"
    case_path.write_text(case.model_dump_json(indent=2), encoding="utf-8")
    return case


def test_csv_import_casing_and_storage_routing(audit_env):
    """Verify CSV import parses uppercase/mixed-case headers and stores into dynamic data_dir."""
    client = audit_env["client"]
    cases_dir = audit_env["cases_dir"]
    headers = _login_client(client)

    csv_data = (
        "Dispute_ID,Amount,Reason_Code,Reason_Description,Respond_By,Customer_Name\n"
        "disp_csv_001,1500.50,general,Service dissatisfaction,1799999999,Jane Doe\n"
        "disp_csv_002,3200.00,fraud,Fraudulent transaction,1799999999,John Smith\n"
    )

    # 1. Dry run
    resp = client.post(
        "/api/v1/disputes/import-csv",
        json={"csv_data": csv_data, "dry_run": True},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["dry_run"] is True
    assert data["valid_count"] == 2
    assert data["error_count"] == 0

    # 2. Actual import
    resp_import = client.post(
        "/api/v1/disputes/import-csv",
        json={"csv_data": csv_data, "dry_run": False},
        headers=headers,
    )
    assert resp_import.status_code == 200, resp_import.text
    import_data = resp_import.json()
    assert import_data["dry_run"] is False
    assert import_data["imported_count"] == 2

    # Verify written to cases_dir in data_dir
    assert (cases_dir / "disp_csv_001.json").exists()
    assert (cases_dir / "disp_csv_002.json").exists()

    # Load and check parsed content
    c1 = json.loads((cases_dir / "disp_csv_001.json").read_text(encoding="utf-8"))
    assert c1["dispute"]["amount"] == 150050
    assert c1["dispute"]["reason_code"] == "general"


def test_data_dir_persistent_storage_routing(audit_env):
    """Verify metrics, list, export, notifications, and org settings use dynamic data_dir."""
    client = audit_env["client"]
    data_dir = audit_env["data_dir"]
    cases_dir = audit_env["cases_dir"]
    headers = _login_client(client, username="test_admin", role="admin")

    # Seed a case with urgent deadline (10h left)
    _create_test_case("disp_persist_01", cases_dir, hours_left=10.0)

    # 1. Dashboard metrics
    m_resp = client.get("/api/v1/dashboard/metrics")
    assert m_resp.status_code == 200
    m_data = m_resp.json()
    assert m_data["total_disputes"] >= 1
    assert m_data["open_disputes"] >= 1

    # 2. List disputes
    l_resp = client.get("/api/v1/disputes")
    assert l_resp.status_code == 200
    l_data = l_resp.json()
    assert any(d["case_id"] == "disp_persist_01" for d in l_data["items"])

    # 3. Export CSV
    e_resp = client.get("/api/v1/disputes/export")
    assert e_resp.status_code == 200
    assert "disp_persist_01" in e_resp.text

    # 4. Notifications
    n_resp = client.get("/api/v1/notifications")
    assert n_resp.status_code == 200
    n_data = n_resp.json()
    assert any("disp_persist_01" in notif["title"] for notif in n_data["notifications"])

    # 5. Org settings (saved to data_dir / "org_settings.json")
    org_payload = {
        "merchant_name": "Persistent Test Merchant",
        "merchant_id": "acc_persist_99",
        "currency": "INR",
        "timezone": "Asia/Kolkata",
        "auto_triage": False,
        "high_value_threshold_paise": 1000000,
        "contact_email": "ops@persist.com",
    }
    s_resp = client.post("/api/v1/settings/org", json=org_payload, headers=headers)
    assert s_resp.status_code == 200

    # Ensure file written to dynamic data_dir
    expected_file = data_dir / "org_settings.json"
    assert expected_file.exists()
    assert json.loads(expected_file.read_text(encoding="utf-8"))["merchant_name"] == "Persistent Test Merchant"

    # Get settings returns the saved settings
    g_resp = client.get("/api/v1/settings/org")
    assert g_resp.status_code == 200
    assert g_resp.json()["merchant_name"] == "Persistent Test Merchant"


def test_path_traversal_blocked_in_comments_and_rejection(audit_env):
    """Verify invalid / path-traversing case IDs are rejected on comments and rejection routes."""
    client = audit_env["client"]
    headers = _login_client(client)

    malicious_ids = ["../evil_case", "../../etc/passwd", "disp_..", "disp_bad/slash"]

    for evil_id in malicious_ids:
        # GET comments
        r1 = client.get(f"/api/v1/disputes/{evil_id}/comments")
        assert r1.status_code == 404

        # POST comment
        r2 = client.post(
            f"/api/v1/disputes/{evil_id}/comments",
            json={"comment": "Hello"},
            headers=headers,
        )
        assert r2.status_code == 404

        # POST reject
        r3 = client.post(
            f"/api/v1/disputes/{evil_id}/reject",
            json={"reason": "Rejection note"},
            headers=headers,
        )
        assert r3.status_code == 404


def test_value_errors_return_400_not_500(audit_env):
    """Verify ValueError is caught and returned as clean 400 Bad Request."""
    client = audit_env["client"]
    cases_dir = audit_env["cases_dir"]
    headers = _login_client(client, username="test_reviewer")

    _create_test_case("disp_valerr_01", cases_dir)

    # 1. Empty comment should return 400, not 500
    r_empty_comment = client.post(
        "/api/v1/disputes/disp_valerr_01/comments",
        json={"comment": "   "},
        headers=headers,
    )
    assert r_empty_comment.status_code == 400
    assert "Comment cannot be empty" in r_empty_comment.json()["detail"]

    # 2. Short password (< 6 chars) should return 400, not 500
    r_short_pw = client.post(
        "/api/v1/auth/change-password",
        json={"old_password": "password123", "new_password": "123"},
        headers=headers,
    )
    assert r_short_pw.status_code == 400
    assert "at least 6 characters" in r_short_pw.json()["detail"]


def test_ai_connection_probe_real_testing(audit_env):
    """Verify /api/v1/integrations/ai/test performs a real structured test probe."""
    client = audit_env["client"]
    _login_client(client)

    import disputepilot.web.api as api_mod

    # Case 1: Mock LLM client with generate_json probe success
    mock_llm = MagicMock()
    mock_llm.model = "gemini-2.5-flash-test"
    mock_llm.generate_json.return_value = {"status": "ok"}
    api_mod._llm_client = mock_llm

    r_success = client.post("/api/v1/integrations/ai/test")
    assert r_success.status_code == 200
    data = r_success.json()
    assert data["status"] == "connected"
    assert data["model"] == "gemini-2.5-flash-test"
    mock_llm.generate_json.assert_called_once()

    # Case 2: Mock LLM client with exception (e.g. quota exhausted or key invalid)
    mock_llm.generate_json.side_effect = RuntimeError("Quota exceeded: 429")
    r_error = client.post("/api/v1/integrations/ai/test")
    assert r_error.status_code == 200
    data_err = r_error.json()
    assert data_err["status"] == "error"
    assert "Quota exceeded" in data_err["message"]


def test_live_mode_csv_export(audit_env):
    """Verify disputes export works in live mode using live_source."""
    client = audit_env["client"]
    _login_client(client)

    import disputepilot.web.api as api_mod

    mock_live_source = MagicMock()
    now = int(time.time())
    mock_live_source.list_disputes.return_value = (
        [
            RazorpayDispute(
                id="disp_live_export_01",
                payment_id="pay_live_01",
                amount=750000,
                currency="INR",
                amount_deducted=750000,
                reason_code="fraud",
                reason_description="Live fraud dispute",
                phase=DisputePhase.CHARGEBACK,
                status=DisputeStatus.OPEN,
                respond_by=now + 86400,
                created_at=now,
            )
        ],
        None,
    )

    api_mod._settings = Settings(
        data_mode="live",
        data_dir=audit_env["data_dir"],
        session_secret="s" * 32,
        cookie_secure=False,
    )
    api_mod._live_source = mock_live_source

    resp = client.get("/api/v1/disputes/export")
    assert resp.status_code == 200
    assert "disp_live_export_01" in resp.text
    assert "7500.00" in resp.text


def test_shared_evidence_deletion_safety(audit_env):
    """Verify deleting evidence preserves the underlying disk file if another locker record references the same sha256."""
    client = audit_env["client"]
    cases_dir = audit_env["cases_dir"]
    evidence_dir = audit_env["evidence_dir"]
    locker = audit_env["locker"]
    headers = _login_client(client)

    case1 = _create_test_case("disp_ev_01", cases_dir)
    case2 = _create_test_case("disp_ev_02", cases_dir)

    dummy_content = b"%PDF-1.4 dummy evidence pdf payload"
    import hashlib
    file_hash = hashlib.sha256(dummy_content).hexdigest()
    file_name = "proof_of_delivery.pdf"

    # Save physical file to evidence_dir
    disk_file = evidence_dir / f"{file_hash}_{file_name}"
    disk_file.write_bytes(dummy_content)
    assert disk_file.exists()

    # Add two locker records sharing the same sha256
    doc1 = locker.add(
        dispute_id="disp_ev_01",
        category="shipping_proof",
        file_name=file_name,
        mime="application/pdf",
        size=len(dummy_content),
        sha256=file_hash,
        uploaded_by="test_reviewer",
    )
    doc2 = locker.add(
        dispute_id="disp_ev_02",
        category="shipping_proof",
        file_name=file_name,
        mime="application/pdf",
        size=len(dummy_content),
        sha256=file_hash,
        uploaded_by="test_reviewer",
    )

    assert locker.count_by_hash(file_hash) == 2

    # Delete doc1 (case 1)
    del1_resp = client.delete(f"/api/v1/disputes/disp_ev_01/evidence/{doc1.id}", headers=headers)
    assert del1_resp.status_code == 200
    assert locker.get(doc1.id) is None
    # Physical file MUST still exist because doc2 references it
    assert locker.count_by_hash(file_hash) == 1
    assert disk_file.exists()

    # Delete doc2 (case 2)
    del2_resp = client.delete(f"/api/v1/disputes/disp_ev_02/evidence/{doc2.id}", headers=headers)
    assert del2_resp.status_code == 200
    assert locker.get(doc2.id) is None
    # Physical file should now be deleted since references dropped to 0
    assert locker.count_by_hash(file_hash) == 0
    assert not disk_file.exists()
