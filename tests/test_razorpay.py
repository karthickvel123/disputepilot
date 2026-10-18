"""Tests for Razorpay gateway, webhook processing, signature verification, and retries."""

import concurrent.futures
import hashlib
import hmac
import json
import sqlite3
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from disputepilot.core.models import RazorpayDispute
from disputepilot.razorpay.approval import (
    ApprovalRequired,
    ApprovalService,
)
from disputepilot.razorpay.gateway import (
    IDEMPOTENCY_HEADERS,
    RazorpayGateway,
    SimGateway,
)
from disputepilot.razorpay.webhook import (
    create_webhook_router,
    verify_webhook_signature,
)

SECRET = "test_webhook_secret_key_12345"


def make_test_client(router) -> TestClient:
    """Create a TestClient wrapped with a FastAPI application."""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# ==============================================================================
# 1. Webhook Signature, Fail-Closed & Atomic Deduplication Tests
# ==============================================================================


def test_signature_verification_helper() -> None:
    """Verify raw HMAC-SHA256 signature calculation."""
    raw_payload = b'{"event":"payment.dispute.created","id":"evt_123"}'
    valid_sig = hmac.new(SECRET.encode("utf-8"), raw_payload, hashlib.sha256).hexdigest()

    assert verify_webhook_signature(raw_payload, valid_sig, SECRET) is True
    assert verify_webhook_signature(raw_payload, "invalid_sig_hex", SECRET) is False
    assert verify_webhook_signature(raw_payload, None, SECRET) is False
    assert verify_webhook_signature(raw_payload, valid_sig, None) is False
    assert verify_webhook_signature(raw_payload, valid_sig, "") is False


def test_webhook_fails_closed_when_secret_unset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Hardening #1: If secret is unset or empty, reject every request with HTTP 500 (fail-closed)."""
    monkeypatch.delenv("RAZORPAY_WEBHOOK_SECRET", raising=False)
    db_file = tmp_path / "test_fail_closed.db"
    router = create_webhook_router(webhook_secret="", db_path=db_file)
    client = make_test_client(router)

    raw_body = b'{"event":"payment.dispute.created","id":"evt_fail_closed"}'
    response = client.post(
        "/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": "any_sig"},
    )
    assert response.status_code == 500
    assert "fail-closed" in response.json()["detail"].lower()


def test_webhook_valid_signature_and_storage(tmp_path: Path) -> None:
    """Verify valid signature is accepted and dispute event is recorded in SQLite."""
    db_file = tmp_path / "test_disputes.db"
    router = create_webhook_router(webhook_secret=SECRET, db_path=db_file)
    client = make_test_client(router)

    event_payload = {
        "entity": "event",
        "id": "evt_test_001",
        "event": "payment.dispute.created",
        "payload": {
            "dispute": {
                "entity": {
                    "id": "disp_test_001",
                    "payment_id": "pay_test_001",
                    "amount": 500000,
                    "currency": "INR",
                    "reason_code": "13.1",
                    "status": "open",
                }
            }
        },
    }
    raw_body = json.dumps(event_payload).encode("utf-8")
    sig = hmac.new(SECRET.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    response = client.post(
        "/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
    )

    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "processed"
    assert res_data["event_id"] == "evt_test_001"
    assert res_data["dispute_id"] == "disp_test_001"

    # Verify event stored in SQLite table
    with sqlite3.connect(str(db_file)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT event_id, event_type, dispute_id FROM dispute_events WHERE event_id = ?", ("evt_test_001",))
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "evt_test_001"
        assert row[1] == "payment.dispute.created"
        assert row[2] == "disp_test_001"


def test_webhook_invalid_and_missing_signature(tmp_path: Path) -> None:
    """Verify webhook rejects bad signatures and missing signature headers."""
    db_file = tmp_path / "test_disputes.db"
    router = create_webhook_router(webhook_secret=SECRET, db_path=db_file)
    client = make_test_client(router)

    raw_body = b'{"event":"payment.dispute.created","id":"evt_bad_sig"}'

    # Bad signature
    resp_bad = client.post(
        "/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": "wrong_signature_123"},
    )
    assert resp_bad.status_code == 400
    assert "Invalid webhook signature" in resp_bad.json()["detail"]

    # Missing signature header
    resp_none = client.post(
        "/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json"},
    )
    assert resp_none.status_code == 400
    assert "Invalid webhook signature" in resp_none.json()["detail"]


def test_webhook_duplicate_event_deduplication(tmp_path: Path) -> None:
    """Verify webhook idempotently ignores duplicate events by event id."""
    db_file = tmp_path / "test_disputes.db"
    router = create_webhook_router(webhook_secret=SECRET, db_path=db_file)
    client = make_test_client(router)

    event_payload = {
        "entity": "event",
        "id": "evt_duplicate_test",
        "event": "payment.dispute.created",
        "payload": {"dispute": {"entity": {"id": "disp_dup_123", "amount": 100000}}},
    }
    raw_body = json.dumps(event_payload).encode("utf-8")
    sig = hmac.new(SECRET.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    # First delivery
    resp1 = client.post(
        "/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
    )
    assert resp1.status_code == 200
    assert resp1.json()["status"] == "processed"

    # Second delivery with identical event_id
    resp2 = client.post(
        "/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
    )
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "duplicate_ignored"

    # Verify only single entry exists in database
    with sqlite3.connect(str(db_file)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM dispute_events WHERE event_id = ?", ("evt_duplicate_test",))
        count = cursor.fetchone()[0]
        assert count == 1


def test_webhook_concurrent_duplicate_events(tmp_path: Path) -> None:
    """Hardening #2: Atomic deduplication test delivering the exact same event concurrently."""
    db_file = tmp_path / "test_concurrent.db"
    router = create_webhook_router(webhook_secret=SECRET, db_path=db_file)
    client = make_test_client(router)

    event_payload = {
        "entity": "event",
        "id": "evt_concurrent_001",
        "event": "payment.dispute.created",
        "payload": {"dispute": {"entity": {"id": "disp_conc_001", "amount": 100000}}},
    }
    raw_body = json.dumps(event_payload).encode("utf-8")
    sig = hmac.new(SECRET.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    def send_event() -> dict:
        r = client.post(
            "/webhook",
            content=raw_body,
            headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
        )
        assert r.status_code == 200
        return r.json()

    # Deliver 5 requests concurrently across worker threads
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(send_event) for _ in range(5)]
        results = [f.result() for f in futures]

    statuses = [res["status"] for res in results]
    assert statuses.count("processed") == 1
    assert statuses.count("duplicate_ignored") == 4

    # Verify database has exactly 1 row
    with sqlite3.connect(str(db_file)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM dispute_events WHERE event_id = ?", ("evt_concurrent_001",))
        assert cursor.fetchone()[0] == 1


# ==============================================================================
# 2. Approval Binding to Content & Token Enforcement Tests
# ==============================================================================


def test_submit_without_token_fails(tmp_path: Path) -> None:
    """Non-negotiable #1: Accept and submit without approval token must raise ApprovalRequired."""
    appr_service = ApprovalService()
    sim_gateway = SimGateway(data_dir=tmp_path, drafts_dir=tmp_path / "drafts", approval_service=appr_service)

    dummy_disp = RazorpayDispute(
        id="disp_mock_001",
        payment_id="pay_mock_001",
        amount=250000,
        currency="INR",
        reason_code="13.1",
        phase="chargeback",
        status="open",
        respond_by=1720000000,
        created_at=1719000000,
    )
    sim_gateway._memory_overrides["disp_mock_001"] = dummy_disp

    # 1. Submit without token fails
    with pytest.raises(ApprovalRequired):
        sim_gateway.contest_dispute(
            dispute_id="disp_mock_001",
            action="submit",
            summary="Proof attached",
            approval_token=None,
        )

    # 2. Submit with invalid token fails
    with pytest.raises(ApprovalRequired):
        sim_gateway.contest_dispute(
            dispute_id="disp_mock_001",
            action="submit",
            summary="Proof attached",
            approval_token="appr_invalid_garbage_token",
        )

    # 3. Accept without token fails
    with pytest.raises(ApprovalRequired):
        sim_gateway.accept_dispute(
            dispute_id="disp_mock_001",
            approval_token="fake_token",
        )

    # 4. Draft does NOT require an approval token
    draft_res = sim_gateway.contest_dispute(
        dispute_id="disp_mock_001",
        action="draft",
        summary="Work in progress draft rebuttal",
        approval_token=None,
    )
    assert draft_res.id == "disp_mock_001"
    draft_file = tmp_path / "drafts" / "disp_mock_001_draft.json"
    assert draft_file.exists()


def test_approval_bound_to_content_hash_rejects_payload_tampering(tmp_path: Path) -> None:
    """Hardening #3: Approve payload A, try to submit payload B, expect failure."""
    appr_service = ApprovalService()
    sim_gateway = SimGateway(data_dir=tmp_path, drafts_dir=tmp_path / "drafts", approval_service=appr_service)

    dummy_disp = RazorpayDispute(
        id="disp_content_001",
        payment_id="pay_001",
        amount=250000,
        currency="INR",
        reason_code="13.1",
        phase="chargeback",
        status="open",
        respond_by=1720000000,
        created_at=1719000000,
    )
    sim_gateway._memory_overrides["disp_content_001"] = dummy_disp

    # Payload A: What the human approver inspected and signed off on
    payload_a = {
        "action": "submit",
        "summary": "Legitimate rebuttal summary A",
        "amount": 250000,
    }
    token = appr_service.issue_token(
        dispute_id="disp_content_001",
        action="submit",
        payload=payload_a,
    )

    # Attempt to submit Payload B using token issued for Payload A -> Must fail!
    with pytest.raises(ApprovalRequired) as exc_info:
        sim_gateway.contest_dispute(
            dispute_id="disp_content_001",
            action="submit",
            summary="Tampered rebuttal summary B",  # Different summary!
            amount=250000,
            approval_token=token,
        )
    assert "requires a valid human approval token matching the approved content" in str(exc_info.value)

    # Submitting exact approved Payload A succeeds
    submitted_res = sim_gateway.contest_dispute(
        dispute_id="disp_content_001",
        action="submit",
        summary="Legitimate rebuttal summary A",
        amount=250000,
        approval_token=token,
    )
    assert submitted_res.id == "disp_content_001"

    # Re-using the consumed token fails
    with pytest.raises(ApprovalRequired):
        sim_gateway.contest_dispute(
            dispute_id="disp_content_001",
            action="submit",
            summary="Legitimate rebuttal summary A",
            amount=250000,
            approval_token=token,
        )


def test_approval_bound_to_accept_hash_amount_tampering(tmp_path: Path) -> None:
    """Hardening #3: Accept token binds to dispute id and amount."""
    appr_service = ApprovalService()
    sim_gateway = SimGateway(data_dir=tmp_path, drafts_dir=tmp_path / "drafts", approval_service=appr_service)

    dummy_disp = RazorpayDispute(
        id="disp_acc_001",
        payment_id="pay_001",
        amount=150000,
        currency="INR",
        reason_code="13.1",
        phase="chargeback",
        status="open",
        respond_by=1720000000,
        created_at=1719000000,
    )
    sim_gateway._memory_overrides["disp_acc_001"] = dummy_disp

    # Issue token for a different amount (e.g. 50000 instead of 150000)
    tampered_token = appr_service.issue_token(
        dispute_id="disp_acc_001",
        action="accept",
        amount=50000,
    )

    with pytest.raises(ApprovalRequired):
        sim_gateway.accept_dispute(
            dispute_id="disp_acc_001",
            approval_token=tampered_token,
        )

    # Valid token with matching amount succeeds
    valid_token = appr_service.issue_token(
        dispute_id="disp_acc_001",
        action="accept",
        amount=150000,
    )
    res = sim_gateway.accept_dispute(
        dispute_id="disp_acc_001",
        approval_token=valid_token,
    )
    assert res.id == "disp_acc_001"


# ==============================================================================
# 3. HTTPX Mock Transport, Retries, and Retry Safety Tests
# ==============================================================================


def test_idempotency_headers_constant() -> None:
    """Hardening #5: Verify both idempotency header names exist in IDEMPOTENCY_HEADERS constant."""
    assert "X-Razorpay-Idempotency-Key" in IDEMPOTENCY_HEADERS
    assert "Idempotency-Key" in IDEMPOTENCY_HEADERS


def test_razorpay_gateway_retry_on_500_and_429() -> None:
    """Verify gateway retries with backoff on 5xx and 429 using consistent idempotency keys."""
    attempts = 0
    received_idempotency_keys: list[str | None] = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        key = request.headers.get("X-Razorpay-Idempotency-Key")
        received_idempotency_keys.append(key)

        if attempts == 1:
            return httpx.Response(500, json={"error": {"description": "Server error"}})
        if attempts == 2:
            return httpx.Response(429, json={"error": {"description": "Too many requests"}})

        # Third attempt: success with status read from API response
        return httpx.Response(
            200,
            json={
                "id": "disp_live_001",
                "entity": "dispute",
                "payment_id": "pay_live_001",
                "amount": 100000,
                "currency": "INR",
                "reason_code": "13.1",
                "status": "lost",
                "phase": "chargeback",
                "respond_by": 1720000000,
                "created_at": 1719000000,
                "evidence": {},
            },
        )

    transport = httpx.MockTransport(mock_handler)
    mock_client = httpx.Client(transport=transport)

    appr_service = ApprovalService()
    token = appr_service.issue_token(dispute_id="disp_live_001", action="accept", amount=100000)

    gateway = RazorpayGateway(
        key_id="rzp_test_key",
        key_secret="rzp_test_secret",
        client=mock_client,
        approval_service=appr_service,
        max_retries=3,
        backoff_factor=0.001,
    )
    gateway.fetch_dispute = lambda disp_id: RazorpayDispute(  # type: ignore
        id=disp_id,
        payment_id="pay_001",
        amount=100000,
        currency="INR",
        reason_code="13.1",
        status="open",
        phase="chargeback",
        respond_by=1720000000,
        created_at=1719000000,
    )

    result = gateway.accept_dispute(
        dispute_id="disp_live_001",
        approval_token=token,
        idempotency_key="custom_idem_key_12345",
    )

    assert result.id == "disp_live_001"
    # Status is read directly from API response; not assumed
    assert result.status.value == "lost"
    assert attempts == 3
    assert len(received_idempotency_keys) == 3
    assert all(k == "custom_idem_key_12345" for k in received_idempotency_keys)


def test_retry_safety_timeout_re_fetch_status_changed() -> None:
    """Hardening #4: If first request actually succeeded but timed out, re-fetch status and do NOT resend."""
    post_count = 0
    get_count = 0
    server_dispute_status = "open"

    def mock_server(request: httpx.Request) -> httpx.Response:
        nonlocal post_count, get_count, server_dispute_status
        if request.method == "GET" and request.url.path == "/v1/disputes/disp_timeout_001":
            get_count += 1
            return httpx.Response(
                200,
                json={
                    "id": "disp_timeout_001",
                    "entity": "dispute",
                    "payment_id": "pay_timeout_001",
                    "amount": 100000,
                    "currency": "INR",
                    "reason_code": "13.1",
                    "status": server_dispute_status,
                    "phase": "chargeback",
                    "respond_by": 1720000000,
                    "created_at": 1719000000,
                    "evidence": {},
                },
            )

        if request.method == "POST" and request.url.path == "/v1/disputes/disp_timeout_001/accept":
            post_count += 1
            # Server successfully processed the accept and transitioned status
            server_dispute_status = "lost"
            # But the connection timed out before the client received the response!
            raise httpx.ReadTimeout("Socket timeout waiting for response")

        return httpx.Response(404)

    transport = httpx.MockTransport(mock_server)
    mock_client = httpx.Client(transport=transport)

    appr_service = ApprovalService()
    token = appr_service.issue_token(
        dispute_id="disp_timeout_001",
        action="accept",
        amount=100000,
    )

    gateway = RazorpayGateway(
        key_id="rzp_test_key",
        key_secret="rzp_test_secret",
        client=mock_client,
        approval_service=appr_service,
        max_retries=3,
        backoff_factor=0.001,
    )

    result = gateway.accept_dispute(
        dispute_id="disp_timeout_001",
        approval_token=token,
    )

    # 1. Returned dispute has updated status
    assert result.id == "disp_timeout_001"
    assert result.status.value == "lost"

    # 2. Critical: The POST request was only made ONCE and was NOT resent!
    assert post_count == 1
    # 3. Re-fetch occurred before retry
    assert get_count >= 2


def test_razorpay_gateway_retry_exhaustion_raises() -> None:
    """Verify gateway raises HTTPStatusError when all retries return 503."""
    attempts = 0

    def mock_503_handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, json={"error": {"description": "Service Unavailable"}})

    transport = httpx.MockTransport(mock_503_handler)
    mock_client = httpx.Client(transport=transport)

    gateway = RazorpayGateway(
        key_id="rzp_test_key",
        key_secret="rzp_test_secret",
        client=mock_client,
        max_retries=3,
        backoff_factor=0.001,
    )

    with pytest.raises(httpx.HTTPStatusError):
        gateway.fetch_dispute("disp_unreachable_001")

    assert attempts == 3


def test_sim_gateway_list_and_upload(tmp_path: Path) -> None:
    """Verify SimGateway document upload and listing."""
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir(parents=True)
    drafts_dir = tmp_path / "drafts"

    dummy_case = {
        "case_id": "disp_sim_001",
        "dispute": {
            "id": "disp_sim_001",
            "entity": "dispute",
            "payment_id": "pay_001",
            "amount": 299900,
            "currency": "INR",
            "reason_code": "13.1",
            "status": "open",
            "phase": "chargeback",
            "respond_by": 1720000000,
            "created_at": 1719000000,
            "evidence": {},
        },
        "order": {
            "id": "order_001",
            "entity": "order",
            "amount": 299900,
            "currency": "INR",
            "status": "paid",
            "created_at": 1718000000,
            "customer_name": "Test User",
            "customer_email": "test@example.com",
            "customer_phone": "+919876543210",
            "shipping_address": "Test Street",
        },
        "ground_truth": {
            "reason_class": "item_not_received",
            "available_evidence": ["shipping_proof"],
            "winnable": True,
            "rule_explanation": "Test",
        },
    }
    with open(cases_dir / "disp_sim_001.json", "w", encoding="utf-8") as f:
        json.dump(dummy_case, f)

    gateway = SimGateway(data_dir=cases_dir, drafts_dir=drafts_dir)
    disputes = gateway.list_disputes()
    assert len(disputes) == 1
    assert disputes[0].id == "disp_sim_001"

    # Upload document
    doc_res = gateway.upload_document(
        file_content=b"# Test Proof",
        file_name="proof.md",
        purpose="dispute_evidence",
    )
    assert doc_res["id"].startswith("doc_sim_")
    assert doc_res["name"] == "proof.md"
    assert (drafts_dir / f"{doc_res['id']}_proof.md").exists()
