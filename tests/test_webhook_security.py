"""Comprehensive webhook security regression tests.

Verifies:
- Raw request body HMAC-SHA256 constant-time signature verification.
- Rejection of invalid, corrupted, or missing signatures before database persistence.
- Rejection of malformed / unparseable JSON payloads.
- Replay handling, idempotent event deduplication, and repeated deliveries.
- Fail-closed behavior when RAZORPAY_WEBHOOK_SECRET is empty or unset.
- Sensitive-data minimization and PII pruning before SQLite persistence.
- Event retention pruning (`prune_dispute_events`).
"""

import hashlib
import hmac
import json
import sqlite3
import time
from pathlib import Path

from fastapi import FastAPI
from starlette.testclient import TestClient

from disputepilot.razorpay.webhook import (
    create_webhook_router,
    init_db,
    prune_dispute_events,
    sanitize_webhook_payload,
    verify_webhook_signature,
)

WEBHOOK_SECRET = "sec_live_webhook_hardening_9876543210"


def make_test_client(router) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_verify_webhook_signature_raw_bytes() -> None:
    """Ensure verification uses exact raw bytes and constant-time compare."""
    body = b'{"hello": "world"}'
    sig = hmac.new(WEBHOOK_SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()

    assert verify_webhook_signature(body, sig, WEBHOOK_SECRET) is True
    # Tampered body must fail
    assert verify_webhook_signature(b'{"hello": "world!"}', sig, WEBHOOK_SECRET) is False
    # Corrupted signature must fail
    assert verify_webhook_signature(body, "bad_hex_signature", WEBHOOK_SECRET) is False
    # Missing parameters must fail
    assert verify_webhook_signature(body, None, WEBHOOK_SECRET) is False
    assert verify_webhook_signature(body, sig, None) is False
    assert verify_webhook_signature(body, sig, "") is False


def test_webhook_invalid_signature_rejected_before_db(tmp_path: Path) -> None:
    """Incoming request with invalid signature must be rejected before persisting anything."""
    db_file = tmp_path / "webhook_events.db"
    router = create_webhook_router(webhook_secret=WEBHOOK_SECRET, db_path=db_file)
    client = make_test_client(router)

    raw_body = b'{"event": "dispute.created", "id": "evt_invalid_sig"}'
    response = client.post(
        "/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": "invalid_sig_123"},
    )
    assert response.status_code == 400
    assert "invalid webhook signature" in response.json()["detail"].lower()

    # DB must have zero stored events (even after schema init)
    init_db(db_file)
    with sqlite3.connect(str(db_file)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM dispute_events")
        count = cursor.fetchone()[0]
        assert count == 0


def test_webhook_malformed_json_rejected(tmp_path: Path) -> None:
    """Malformed non-JSON body must return 400 Bad Request."""
    db_file = tmp_path / "webhook_events.db"
    router = create_webhook_router(webhook_secret=WEBHOOK_SECRET, db_path=db_file)
    client = make_test_client(router)

    raw_body = b"not_valid_json{{{[["
    sig = hmac.new(WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    response = client.post(
        "/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
    )
    assert response.status_code == 400
    assert "invalid json payload" in response.json()["detail"].lower()


def test_webhook_payload_pruning_and_pii_redaction(tmp_path: Path) -> None:
    """Payloads stored in SQLite must contain only dispute entity fields and omit sensitive data."""
    db_file = tmp_path / "webhook_events.db"
    router = create_webhook_router(webhook_secret=WEBHOOK_SECRET, db_path=db_file)
    client = make_test_client(router)

    event_payload = {
        "entity": "event",
        "account_id": "acc_prod_001",
        "event": "dispute.created",
        "id": "evt_sanitize_01",
        "created_at": 1700000000,
        "payload": {
            "dispute": {
                "entity": {
                    "id": "disp_sanitized_01",
                    "payment_id": "pay_sanitized_01",
                    "amount": 10000,
                    "currency": "INR",
                    "status": "under_review",
                    "phase": "chargeback",
                    "reason_code": "fraud",
                    # Sensitive fields that MUST NOT be retained
                    "customer_card_number": "4111111111111111",
                    "cvv": "123",
                    "customer_email": "victim@example.com",
                    "authorization_token": "secret_bearer_token",
                }
            },
            # Non-dispute sensitive sub-objects
            "payment": {
                "entity": {
                    "card": {"number": "4111111111111111", "name": "Secret User"},
                }
            },
        },
    }
    raw_body = json.dumps(event_payload).encode("utf-8")
    sig = hmac.new(WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    response = client.post(
        "/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
    )
    assert response.status_code == 200

    # Inspect stored payload in SQLite
    with sqlite3.connect(str(db_file)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT payload FROM dispute_events WHERE event_id = ?", ("evt_sanitize_01",))
        stored_raw = cursor.fetchone()[0]
        stored_json = json.loads(stored_raw)

    # 1. Essential dispute fields preserved
    dispute_entity = stored_json["payload"]["dispute"]["entity"]
    assert dispute_entity["id"] == "disp_sanitized_01"
    assert dispute_entity["payment_id"] == "pay_sanitized_01"
    assert dispute_entity["amount"] == 10000

    # 2. Sensitive customer data pruned
    assert "customer_card_number" not in dispute_entity
    assert "cvv" not in dispute_entity
    assert "customer_email" not in dispute_entity
    assert "authorization_token" not in dispute_entity
    assert "payment" not in stored_json["payload"]
    assert "4111111111111111" not in stored_raw
    assert "secret_bearer_token" not in stored_raw


def test_webhook_deduplication_and_repeated_delivery(tmp_path: Path) -> None:
    """Repeated webhook delivery of the same event ID returns duplicate_ignored idempotently."""
    db_file = tmp_path / "webhook_events.db"
    router = create_webhook_router(webhook_secret=WEBHOOK_SECRET, db_path=db_file)
    client = make_test_client(router)

    event_payload = {
        "entity": "event",
        "id": "evt_repeat_001",
        "event": "dispute.won",
        "payload": {
            "dispute": {
                "entity": {
                    "id": "disp_repeat_001",
                    "payment_id": "pay_repeat_001",
                    "amount": 25000,
                    "status": "won",
                }
            }
        },
    }
    raw_body = json.dumps(event_payload).encode("utf-8")
    sig = hmac.new(WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    # First delivery -> processed
    res1 = client.post(
        "/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
    )
    assert res1.status_code == 200
    assert res1.json()["status"] == "processed"

    # Second delivery (replay attack or network duplicate) -> duplicate_ignored
    res2 = client.post(
        "/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
    )
    assert res2.status_code == 200
    assert res2.json()["status"] == "duplicate_ignored"

    # Verify only ONE entry exists in the DB
    with sqlite3.connect(str(db_file)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM dispute_events WHERE event_id = ?", ("evt_repeat_001",))
        assert cursor.fetchone()[0] == 1


def test_sanitize_webhook_payload_direct() -> None:
    """Directly test sanitize_webhook_payload strips personal identifiers and non-dispute data."""
    raw = {
        "entity": "event",
        "account_id": "acc_123",
        "event": "dispute.created",
        "id": "evt_123",
        "payload": {
            "dispute": {
                "entity": {
                    "id": "disp_123",
                    "amount": 500,
                    "currency": "INR",
                    "customer_phone": "+919999999999",
                }
            },
            "unrelated_secret": "forbidden",
        },
    }
    sanitized = sanitize_webhook_payload(raw)
    assert sanitized["account_id"] == "acc_123"
    assert "customer_phone" not in sanitized["payload"]["dispute"]["entity"]
    assert "unrelated_secret" not in sanitized["payload"]


def test_event_retention_pruning(tmp_path: Path) -> None:
    """prune_dispute_events deletes records older than max_age_days."""
    db_file = tmp_path / "retention.db"

    now = int(time.time())
    old_timestamp = now - (95 * 86400)  # 95 days old

    init_db(db_file)
    # Insert one old event and one fresh event directly into SQLite
    with sqlite3.connect(str(db_file)) as conn:
        conn.execute(
            "INSERT INTO dispute_events (event_id, event_type, dispute_id, payment_id, payload, received_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("evt_old_01", "dispute.created", "disp_old", "pay_old", "{}", old_timestamp),
        )
        conn.execute(
            "INSERT INTO dispute_events (event_id, event_type, dispute_id, payment_id, payload, received_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("evt_new_01", "dispute.created", "disp_new", "pay_new", "{}", now),
        )
        conn.commit()

    # Prune with 90 days retention
    pruned_count = prune_dispute_events(max_age_days=90, db_path=db_file)
    assert pruned_count == 1

    # Only new event remains
    with sqlite3.connect(str(db_file)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT event_id FROM dispute_events")
        rows = cursor.fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "evt_new_01"


def test_webhook_missing_secret_returns_500_fail_closed(tmp_path: Path, monkeypatch) -> None:
    """When RAZORPAY_WEBHOOK_SECRET is empty/unset, reject request with HTTP 500 (fail-closed server error)."""
    monkeypatch.delenv("RAZORPAY_WEBHOOK_SECRET", raising=False)
    db_file = tmp_path / "webhook_events.db"
    router = create_webhook_router(webhook_secret="", db_path=db_file)
    client = make_test_client(router)

    raw_body = b'{"event": "dispute.created", "id": "evt_secret_unset"}'
    response = client.post(
        "/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": "dummy_sig"},
    )
    assert response.status_code == 500
    assert "fail-closed" in response.json()["detail"].lower()


def test_webhook_missing_signature_returns_400(tmp_path: Path) -> None:
    """Request without X-Razorpay-Signature header must be rejected with 400 Bad Request."""
    db_file = tmp_path / "webhook_events.db"
    router = create_webhook_router(webhook_secret=WEBHOOK_SECRET, db_path=db_file)
    client = make_test_client(router)

    raw_body = b'{"event": "payment.dispute.created", "id": "evt_no_sig"}'
    response = client.post(
        "/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
    assert "missing" in response.json()["detail"].lower()


def test_webhook_payload_size_limit_returns_413(tmp_path: Path) -> None:
    """Payloads exceeding maximum body size must be rejected with HTTP 413."""
    db_file = tmp_path / "webhook_events.db"
    # Set a small limit of 512 bytes for testing
    router = create_webhook_router(webhook_secret=WEBHOOK_SECRET, db_path=db_file, max_body_bytes=512)
    client = make_test_client(router)

    oversized_data = {"event": "payment.dispute.created", "padding": "x" * 600}
    raw_body = json.dumps(oversized_data).encode("utf-8")
    sig = hmac.new(WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    response = client.post(
        "/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
    )
    assert response.status_code == 413
    assert "exceeds maximum allowed size" in response.json()["detail"]


def test_webhook_rate_limiting_returns_429(tmp_path: Path) -> None:
    """Requests exceeding sliding-window rate limit must be rejected with HTTP 429."""
    from disputepilot.core.rate_limit import SlidingWindowRateLimiter

    db_file = tmp_path / "webhook_events.db"
    # Allow at most 2 requests per 60s
    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60)
    router = create_webhook_router(webhook_secret=WEBHOOK_SECRET, db_path=db_file, rate_limiter=limiter)
    client = make_test_client(router)

    def send_req(evt_id: str):
        payload = {"event": "payment.dispute.created", "id": evt_id}
        body = json.dumps(payload).encode("utf-8")
        sig = hmac.new(WEBHOOK_SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return client.post(
            "/webhook",
            content=body,
            headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
        )

    r1 = send_req("evt_rl_1")
    assert r1.status_code == 200
    r2 = send_req("evt_rl_2")
    assert r2.status_code == 200

    # 3rd request should hit rate limit
    r3 = send_req("evt_rl_3")
    assert r3.status_code == 429
    assert "too many webhook requests" in r3.json()["detail"].lower()


def test_webhook_normalizes_dispute_and_payment_dispute_events(tmp_path: Path) -> None:
    """Both payment.dispute.* and dispute.* events are processed and normalized."""
    db_file = tmp_path / "webhook_events.db"
    router = create_webhook_router(webhook_secret=WEBHOOK_SECRET, db_path=db_file)
    client = make_test_client(router)

    # 1. Official payment.dispute.created
    p1 = {
        "event": "payment.dispute.created",
        "id": "evt_official_01",
        "payload": {"dispute": {"entity": {"id": "disp_off_01", "payment_id": "pay_off_01"}}},
    }
    b1 = json.dumps(p1).encode("utf-8")
    s1 = hmac.new(WEBHOOK_SECRET.encode("utf-8"), b1, hashlib.sha256).hexdigest()
    res1 = client.post(
        "/webhook",
        content=b1,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": s1},
    )
    assert res1.status_code == 200
    assert res1.json()["event_type"] == "payment.dispute.created"

    # 2. Short dispute.under_review normalized to payment.dispute.under_review
    p2 = {
        "event": "dispute.under_review",
        "id": "evt_short_01",
        "payload": {"dispute": {"entity": {"id": "disp_short_01", "payment_id": "pay_short_01"}}},
    }
    b2 = json.dumps(p2).encode("utf-8")
    s2 = hmac.new(WEBHOOK_SECRET.encode("utf-8"), b2, hashlib.sha256).hexdigest()
    res2 = client.post(
        "/webhook",
        content=b2,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": s2},
    )
    assert res2.status_code == 200
    assert res2.json()["event_type"] == "payment.dispute.under_review"


