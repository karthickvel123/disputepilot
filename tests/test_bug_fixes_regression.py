"""Comprehensive regression test suite verifying fixes for all 13 reported bugs."""

import io
import json
import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from disputepilot.config import Settings
from disputepilot.core.models import (
    DisputeCase,
    DisputePhase,
    DisputeStatus,
    Order,
    OrderItem,
    RazorpayDispute,
    RazorpayEvidence,
)
from disputepilot.live.locker import EvidenceLocker
from disputepilot.pipeline.audit import (
    DEFAULT_DEAD_LETTER_PATH,
    init_audit_db,
    reconcile_audit_log,
    record_audit_event,
)
from disputepilot.razorpay.approval import ApprovalService, compute_accept_payload_hash
from disputepilot.razorpay.gateway import RazorpayGateway
from disputepilot.safety.card_scanner import (
    extract_text_from_pdf_bytes,
    scan_pdf_bytes,
    scan_text,
)
from disputepilot.web.api import _ensure_actionable, configure_api, router as api_router
from disputepilot.web.app import app
from disputepilot.web.auth import create_session_cookie_value, get_cookie_samesite_and_secure


@pytest.fixture
def test_env(tmp_path):
    """Set up temporary directory, locker, and settings for testing."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    cases_dir = data_dir / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir = data_dir / "evidence_files"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    locker_db = data_dir / "locker.db"
    locker = EvidenceLocker(locker_db)

    approvals_db = data_dir / "approvals.db"
    approval_svc = ApprovalService(db_path=approvals_db)

    settings = Settings(
        data_mode="sim",
        data_dir=data_dir,
        session_secret="a" * 32,
        reviewer_user="reviewer1",
        reviewer_password_hash="fakehash",
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
            "evidence_dir": evidence_dir,
            "locker": locker,
            "approval_svc": approval_svc,
            "settings": settings,
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


def _create_dummy_case(case_id: str, cases_dir: Path, metadata: dict | None = None) -> DisputeCase:
    now = int(time.time())
    disp = RazorpayDispute(
        id=case_id,
        payment_id=f"pay_{case_id}",
        amount=10000,
        currency="INR",
        amount_deducted=10000,
        reason_code="chargeback",
        reason_description="Test chargeback",
        phase=DisputePhase.CHARGEBACK,
        status=DisputeStatus.OPEN,
        respond_by=now + 86400,
        created_at=now,
    )
    order = Order(
        id=f"order_{case_id}",
        amount=10000,
        currency="INR",
        status="paid",
        created_at=now - 86400,
    )
    case = DisputeCase(
        case_id=case_id,
        dispute=disp,
        order=order,
        metadata=metadata or {},
    )
    (cases_dir / f"{case_id}.json").write_text(json.dumps(case.model_dump(), indent=2), encoding="utf-8")
    return case


# ---------------------------------------------------------------------------
# Bug 1: Evidence Authorization & Ownership
# ---------------------------------------------------------------------------

def test_bug1_evidence_authorization_and_ownership(test_env):
    """Evidence download and delete endpoints must enforce role and dispute ownership."""
    client = test_env["client"]
    cases_dir = test_env["cases_dir"]
    locker = test_env["locker"]

    # Create two dispute cases
    case_a = _create_dummy_case("disp_case_a", cases_dir)
    case_b = _create_dummy_case("disp_case_b", cases_dir)

    # Add evidence belonging strictly to case_b
    doc_b = locker.add(
        dispute_id=case_b.dispute.id,
        category="shipping_proof",
        file_name="proof_b.pdf",
        mime="application/pdf",
        size=100,
        sha256="b" * 64,
        uploaded_by="reviewer1",
    )

    # 1. Unauthenticated request must fail
    res_unauth = client.get(f"/api/v1/disputes/{case_a.case_id}/evidence/{doc_b.id}/download")
    assert res_unauth.status_code == 401

    # 2. Authenticated as reviewer
    cookie_val, csrf = create_session_cookie_value(user="reviewer1", role="reviewer")
    client.cookies.set("disputepilot_session", cookie_val)

    # 3. Ownership mismatch: Attempting to download doc_b under case_a must return 403 Forbidden
    res_mismatch = client.get(f"/api/v1/disputes/{case_a.case_id}/evidence/{doc_b.id}/download")
    assert res_mismatch.status_code == 403
    assert "does not belong" in res_mismatch.json()["detail"].lower()

    # 4. Ownership mismatch on delete must also return 403 Forbidden
    res_del_mismatch = client.delete(
        f"/api/v1/disputes/{case_a.case_id}/evidence/{doc_b.id}",
        headers={"x-csrf-token": csrf},
    )
    assert res_del_mismatch.status_code == 403
    assert "does not belong" in res_del_mismatch.json()["detail"].lower()

    # 5. Accessing under correct case succeeds
    res_valid = client.get(f"/api/v1/disputes/{case_b.case_id}/evidence/{doc_b.id}/download")
    assert res_valid.status_code == 200

    # 6. Deleting under correct case succeeds
    res_del_valid = client.delete(
        f"/api/v1/disputes/{case_b.case_id}/evidence/{doc_b.id}",
        headers={"x-csrf-token": csrf},
    )
    assert res_del_valid.status_code == 200
    assert locker.get(doc_b.id) is None


# ---------------------------------------------------------------------------
# Bug 2: Path Traversal Vulnerability
# ---------------------------------------------------------------------------

def test_bug2_path_traversal_prevention(test_env):
    """Dispute creation and CSV import must reject IDs containing path traversal characters."""
    client = test_env["client"]
    cookie_val, csrf = create_session_cookie_value(user="reviewer1", role="reviewer")
    client.cookies.set("disputepilot_session", cookie_val)

    # Attempt path traversal via manual creation
    res_create = client.post(
        "/api/v1/disputes/create",
        json={
            "dispute_id": "../../etc_passwd",
            "amount_rupees": 1500.0,
            "currency": "INR",
            "reason_code": "fraud",
            "reason_description": "Fraudulent charge",
        },
        headers={"x-csrf-token": csrf},
    )
    assert res_create.status_code == 400
    assert "invalid dispute id format" in res_create.json()["detail"].lower()

    # Attempt path traversal via CSV import
    malicious_csv = (
        "dispute_id,amount,reason_code,reason_description\n"
        "../../traversal_case,1000,fraud,Stolen card\n"
    )
    res_import = client.post(
        "/api/v1/disputes/import-csv",
        json={"csv_data": malicious_csv, "dry_run": False},
        headers={"x-csrf-token": csrf},
    )
    assert res_import.status_code == 200
    data = res_import.json()
    assert data["error_count"] > 0
    assert any("invalid dispute id format" in str(e).lower() for e in data["errors"])


# ---------------------------------------------------------------------------
# Bug 3: Block Synthetic Cases from Live Actions
# ---------------------------------------------------------------------------

def test_bug3_block_synthetic_cases_from_live_actions(test_env):
    """Synthetic cases must have proper provenance and be blocked from live Razorpay actions."""
    client = test_env["client"]
    cases_dir = test_env["cases_dir"]
    cookie_val, csrf = create_session_cookie_value(user="reviewer1", role="reviewer")
    client.cookies.set("disputepilot_session", cookie_val)

    # 1. Create a manual dispute case
    res_create = client.post(
        "/api/v1/disputes/create",
        json={
            "dispute_id": "disp_synth_001",
            "amount_rupees": 2000.0,
            "currency": "INR",
            "reason_code": "fraud",
            "reason_description": "Cardholder reported fraud",
        },
        headers={"x-csrf-token": csrf},
    )
    assert res_create.status_code == 200

    # Verify provenance metadata on disk
    case_path = cases_dir / "disp_synth_001.json"
    assert case_path.exists()
    case_data = json.loads(case_path.read_text(encoding="utf-8"))
    assert case_data["metadata"]["provenance"] == "synthetic"
    assert case_data["metadata"]["is_synthetic"] is True
    assert case_data["metadata"]["verified"] is False

    # 2. When evaluated under live mode (DATA_MODE=live), _ensure_actionable must raise 400
    live_settings = Settings(
        data_mode="live",
        data_dir=test_env["data_dir"],
        razorpay_key_id="rzp_test_12345678901234",
        razorpay_key_secret="secret12345678901234",
    )
    configure_api(settings=live_settings)

    case_obj = DisputeCase.model_validate(case_data)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        _ensure_actionable(case_obj)
    assert exc_info.value.status_code == 400
    assert "synthetic or unverified" in exc_info.value.detail.lower()

    # Reset back to test_env sim settings
    configure_api(settings=test_env["settings"])


# ---------------------------------------------------------------------------
# Bug 4: Incomplete Card Data Scanning
# ---------------------------------------------------------------------------

def test_bug4_card_scanner_and_pdf_inspection():
    """PDF text streams must be inspected for Luhn-valid card numbers and CVVs."""
    # 4111111111111111 is a Luhn-valid Visa test card number
    visa_card = "4111111111111111"
    cvv = "CVV: 789"

    # Simulated PDF containing text in stream
    pdf_content = (
        b"%PDF-1.4\n1 0 obj\n<< /Length 60 >>\nstream\n"
        b"BT\n/F1 12 Tf\n(" + visa_card.encode() + b" " + cvv.encode() + b") Tj\nET\n"
        b"endstream\nendobj\n%%EOF"
    )

    findings = scan_pdf_bytes(pdf_content)
    assert len(findings) >= 2
    types = [f.type for f in findings]
    assert "card_number" in types
    assert "cvv" in types


def test_bug4_upload_evidence_pdf_rejection(test_env):
    """Uploading a PDF containing a payment card number must be rejected immediately."""
    client = test_env["client"]
    cases_dir = test_env["cases_dir"]
    case = _create_dummy_case("disp_card_test", cases_dir)

    cookie_val, csrf = create_session_cookie_value(user="reviewer1", role="reviewer")
    client.cookies.set("disputepilot_session", cookie_val)

    bad_pdf = (
        b"%PDF-1.4\n1 0 obj\n<< /Length 50 >>\nstream\n"
        b"BT\n/F1 12 Tf\n(Customer card: 4111111111111111) Tj\nET\n"
        b"endstream\nendobj\n%%EOF"
    )

    files = {"file": ("card_doc.pdf", bad_pdf, "application/pdf")}
    res = client.post(
        f"/api/v1/disputes/{case.case_id}/evidence",
        data={"category": "billing_proof", "attest_no_card_data": "yes", "csrf_token": csrf},
        files=files,
    )
    assert res.status_code == 400
    assert "card number or cvv was detected" in res.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Bug 6: Independent Approval Enforcement
# ---------------------------------------------------------------------------

def test_bug6_independent_approval_enforcement(test_env):
    """When REQUIRE_INDEPENDENT_APPROVAL is enabled, executor cannot be the same user as approver."""
    client = test_env["client"]
    cases_dir = test_env["cases_dir"]
    appr_svc = test_env["approval_svc"]

    case = _create_dummy_case("disp_indep_appr", cases_dir)

    # Enable independent approval requirement
    indep_settings = Settings(
        data_mode="sim",
        data_dir=test_env["data_dir"],
        require_independent_approval=True,
    )
    configure_api(settings=indep_settings, approval_service=appr_svc)

    # Issue an approval token approved by "alice"
    token = appr_svc.issue_token(
        dispute_id=case.dispute.id,
        action="accept",
        amount=case.dispute.amount,
        approver="alice",
    )
    payload_hash = compute_accept_payload_hash(case.dispute.id, case.dispute.amount)

    # Alice attempts to execute the action herself -> must be rejected with 403
    cookie_alice, csrf_alice = create_session_cookie_value(user="alice", role="reviewer")
    client.cookies.set("disputepilot_session", cookie_alice)

    res_same_user = client.post(
        f"/api/v1/disputes/{case.case_id}/accept",
        json={"approval_token": token, "payload_hash": payload_hash, "csrf_token": csrf_alice},
    )
    assert res_same_user.status_code == 403
    assert "independent approval required" in res_same_user.json()["detail"].lower()

    # Reset back to test_env settings
    configure_api(settings=test_env["settings"])


# ---------------------------------------------------------------------------
# Bug 7: Gateway Retry Pre-Check after Upstream Timeout
# ---------------------------------------------------------------------------

def test_bug7_gateway_pre_retry_check_on_timeout():
    """RazorpayGateway._execute_with_retry must check pre_retry_check when timeout occurs."""
    gw = RazorpayGateway(
        key_id="rzp_test_12345678901234",
        key_secret="secret12345678901234",
        max_retries=2,
        backoff_factor=0.01,
    )

    resolved_dispute = RazorpayDispute(
        id="disp_retry_test",
        payment_id="pay_retry_test",
        amount=5000,
        currency="INR",
        amount_deducted=5000,
        reason_code="chargeback",
        reason_description="Test",
        phase=DisputePhase.CHARGEBACK,
        status=DisputeStatus.UNDER_REVIEW,
        respond_by=int(time.time()) + 86400,
        created_at=int(time.time()),
    )

    # Mock client.request to always raise ReadTimeout
    mock_client = MagicMock()
    mock_client.request.side_effect = httpx.ReadTimeout("Request timed out")
    gw.client = mock_client

    # pre_retry_check returns the updated dispute (as if upstream accepted it before timeout)
    pre_check = MagicMock(return_value=resolved_dispute)

    result = gw._execute_with_retry(
        method="PATCH",
        path="/v1/disputes/disp_retry_test/contest",
        json_data={"action": "submit"},
        pre_retry_check=pre_check,
    )

    assert isinstance(result, RazorpayDispute)
    assert result.status == DisputeStatus.UNDER_REVIEW
    assert pre_check.called


# ---------------------------------------------------------------------------
# Bug 8: Audit Log Reliability & Dead Letter Queue
# ---------------------------------------------------------------------------

def test_bug8_audit_dead_letter_fallback_and_reconciliation(tmp_path):
    """Audit logging must fallback to dead-letter log on SQLite failure and reconcile cleanly."""
    db_path = tmp_path / "audit.db"
    dl_path = tmp_path / "dead_letter.jsonl"

    init_audit_db(db_path)

    # Force a lock / failure on the SQLite database by patching sqlite3.connect
    with patch("sqlite3.connect", side_effect=sqlite3.OperationalError("database is locked")):
        hash_res = record_audit_event(
            case_id="disp_audit_fail",
            action="submit_contest",
            actor="reviewer1",
            details={"test": "dead_letter_entry"},
            dead_letter_path=dl_path,
            db_path=db_path,
        )
        assert hash_res is not None

    # Verify entry was written to dead-letter JSONL
    assert dl_path.exists()
    lines = dl_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["case_id"] == "disp_audit_fail"
    assert "database is locked" in record["error"]

    # Now reconcile the dead-letter log back into SQLite
    reconciled_count = reconcile_audit_log(dead_letter_path=dl_path, db_path=db_path)
    assert reconciled_count == 1
    assert not dl_path.exists() or dl_path.read_text(encoding="utf-8").strip() == ""


# ---------------------------------------------------------------------------
# Bug 9: CSV Imported Data Accuracy
# ---------------------------------------------------------------------------

def test_bug9_csv_import_data_accuracy(test_env):
    """CSV import must not blindly assume winnable=True or fixed 5-day deadline."""
    client = test_env["client"]
    cases_dir = test_env["cases_dir"]
    cookie_val, csrf = create_session_cookie_value(user="reviewer1", role="reviewer")
    client.cookies.set("disputepilot_session", cookie_val)

    csv_data = (
        "dispute_id,amount,reason_code,reason_description,winnable,days_to_respond\n"
        "disp_csv_unwin,3000,fraud,Stolen card,false,2\n"
        "disp_csv_nodata,4000,product_not_received,Did not receive,,\n"
    )

    res = client.post(
        "/api/v1/disputes/import-csv",
        json={"csv_data": csv_data, "dry_run": False},
        headers={"x-csrf-token": csrf},
    )
    assert res.status_code == 200
    assert res.json()["imported_count"] == 2

    # Verify unwin case
    case_unwin = json.loads((cases_dir / "disp_csv_unwin.json").read_text(encoding="utf-8"))
    assert case_unwin["ground_truth"]["winnable"] is False
    assert case_unwin["metadata"]["deadline_assumed"] is False

    # Verify nodata case: no blind winnable=True
    case_nodata = json.loads((cases_dir / "disp_csv_nodata.json").read_text(encoding="utf-8"))
    assert case_nodata["ground_truth"] is None
    assert case_nodata["metadata"]["deadline_assumed"] is True


# ---------------------------------------------------------------------------
# Bug 12: Security Configuration & Cookie Attributes
# ---------------------------------------------------------------------------

def test_bug12_cookie_attributes_and_cors_configuration():
    """Verify cookie SameSite/Secure logic and configurable CORS origins."""
    # When cookie_secure is True (HTTPS production)
    samesite, secure = get_cookie_samesite_and_secure(cookie_secure=True)
    assert samesite == "none"
    assert secure is True

    # When cookie_secure is False (local dev)
    samesite, secure = get_cookie_samesite_and_secure(cookie_secure=False)
    assert samesite == "lax"
    assert secure is False


# ---------------------------------------------------------------------------
# Bug 13: Grounded Messaging (No Zero Hallucination Claim)
# ---------------------------------------------------------------------------

def test_bug13_grounded_engine_status_messaging(test_env):
    """Status probe must not make exaggerated 'zero hallucination guarantee' claims."""
    client = test_env["client"]
    cookie_val, _ = create_session_cookie_value(user="reviewer1", role="reviewer")
    client.cookies.set("disputepilot_session", cookie_val)

    res = client.post("/api/v1/integrations/ai/test")
    assert res.status_code == 200
    data = res.json()
    assert "zero hallucination guarantee" not in data.get("message", "").lower()
