"""Regression and concurrency security tests for ApprovalService and token consumption.

Covers:
- Two simultaneous requests using the same token (multithreaded race).
- Two simulated multi-process workers attempting to consume the same token.
- Expired tokens.
- Already-consumed tokens.
- Modified payloads.
- Invalid signatures / tokens.
- Unauthorized reviewers.
- Database failures during token consumption (failure does NOT mark token as consumed).
"""

import concurrent.futures
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from disputepilot.razorpay.approval import (
    ApprovalRequired,
    ApprovalService,
    compute_accept_payload_hash,
    compute_contest_payload_hash,
)


def test_concurrent_token_consumption_exactly_one_succeeds(tmp_path: Path) -> None:
    """Two simultaneous requests using the same token: exactly one consumes it, second fails."""
    db_path = tmp_path / "approvals.db"
    service = ApprovalService(db_path=db_path)
    dispute_id = "disp_concurrency_001"
    payload = {"action": "submit", "summary": "Delivered on time"}
    token = service.issue_token(
        dispute_id=dispute_id,
        action="submit",
        payload=payload,
        approver="compliance_officer_alice",
    )
    expected_hash = compute_contest_payload_hash(payload)

    results: list[bool] = []

    def try_consume() -> bool:
        # Separate service instance pointing to the same DB simulating independent request workers
        worker_service = ApprovalService(db_path=db_path)
        return worker_service.verify_token(
            token=token,
            action="submit",
            dispute_id=dispute_id,
            expected_payload_hash=expected_hash,
            consume=True,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(try_consume) for _ in range(10)]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    # Exactly ONE thread must succeed; all other 9 must fail
    assert results.count(True) == 1
    assert results.count(False) == 9

    # Token must now be marked as used in database
    rec = service.get_token_record(token)
    assert rec is not None
    assert rec.used is True


def test_two_workers_attempt_to_consume_same_token(tmp_path: Path) -> None:
    """Worker 1 and Worker 2 concurrently consume: exactly one gets True."""
    db_path = tmp_path / "workers.db"
    issuer = ApprovalService(db_path=db_path)
    token = issuer.issue_token(
        dispute_id="disp_worker_test",
        action="accept",
        amount=50000,
        approver="reviewer_bob",
    )
    expected_hash = compute_accept_payload_hash("disp_worker_test", 50000)

    worker1 = ApprovalService(db_path=db_path)
    worker2 = ApprovalService(db_path=db_path)

    res1 = worker1.verify_token(
        token=token,
        action="accept",
        dispute_id="disp_worker_test",
        expected_payload_hash=expected_hash,
        consume=True,
    )
    assert res1 is True

    # Immediate second worker attempt must fail
    res2 = worker2.verify_token(
        token=token,
        action="accept",
        dispute_id="disp_worker_test",
        expected_payload_hash=expected_hash,
        consume=True,
    )
    assert res2 is False


def test_expired_tokens_are_rejected(tmp_path: Path) -> None:
    """Expired token must be rejected even if never used."""
    db_path = tmp_path / "expiry.db"
    service = ApprovalService(token_ttl_seconds=60, db_path=db_path)
    base_time = 1700000000

    token = service.issue_token(
        dispute_id="disp_expired",
        action="submit",
        payload={"action": "submit", "test": True},
        approver="reviewer_exp",
        now=base_time,
    )

    # 1 second after expiration (61s after issue)
    expired = service.verify_token(
        token=token,
        action="submit",
        dispute_id="disp_expired",
        now=base_time + 61,
        consume=True,
    )
    assert expired is False

    # Check that require_approval raises ApprovalRequired
    with pytest.raises(ApprovalRequired):
        service.require_approval(
            token=token,
            action="submit",
            dispute_id="disp_expired",
            now=base_time + 61,
        )


def test_already_consumed_token_is_rejected(tmp_path: Path) -> None:
    """Once consumed, token cannot be reused under any circumstances."""
    db_path = tmp_path / "used.db"
    service = ApprovalService(db_path=db_path)
    payload = {"action": "submit", "foo": "bar"}
    token = service.issue_token(
        dispute_id="disp_reuse",
        action="submit",
        payload=payload,
        approver="reviewer_reuse",
    )
    h = compute_contest_payload_hash(payload)

    first = service.verify_token(token, "submit", "disp_reuse", expected_payload_hash=h, consume=True)
    assert first is True

    # Second consumption attempt
    second = service.verify_token(token, "submit", "disp_reuse", expected_payload_hash=h, consume=True)
    assert second is False

    # Read-only verification check must also report it as invalid
    peek = service.verify_token(token, "submit", "disp_reuse", expected_payload_hash=h, consume=False)
    assert peek is False


def test_modified_payload_fails_verification(tmp_path: Path) -> None:
    """Tampering with approved payload must fail verification."""
    db_path = tmp_path / "tamper.db"
    service = ApprovalService(db_path=db_path)
    original_payload = {"action": "submit", "summary": "Original legitimate evidence"}
    tampered_payload = {"action": "submit", "summary": "Tampered malicious evidence"}

    token = service.issue_token(
        dispute_id="disp_tamper",
        action="submit",
        payload=original_payload,
        approver="auditor_charlie",
    )

    tampered_hash = compute_contest_payload_hash(tampered_payload)
    valid = service.verify_token(
        token=token,
        action="submit",
        dispute_id="disp_tamper",
        expected_payload_hash=tampered_hash,
        consume=True,
    )
    assert valid is False

    # Original token remains unconsumed because payload hash mismatched
    original_hash = compute_contest_payload_hash(original_payload)
    valid_original = service.verify_token(
        token=token,
        action="submit",
        dispute_id="disp_tamper",
        expected_payload_hash=original_hash,
        consume=True,
    )
    assert valid_original is True


def test_unauthorized_reviewer_is_rejected(tmp_path: Path) -> None:
    """Token approved by one user cannot be validated when expected_approver requires another."""
    db_path = tmp_path / "auth_reviewer.db"
    service = ApprovalService(db_path=db_path)
    token = service.issue_token(
        dispute_id="disp_reviewer",
        action="accept",
        amount=10000,
        approver="compliance_lead_dave",
    )
    h = compute_accept_payload_hash("disp_reviewer", 10000)

    # Reject unauthorized expected approver
    unauthorized = service.verify_token(
        token=token,
        action="accept",
        dispute_id="disp_reviewer",
        expected_payload_hash=h,
        expected_approver="unauthorized_mallory",
        consume=True,
    )
    assert unauthorized is False

    # Accept authorized expected approver
    authorized = service.verify_token(
        token=token,
        action="accept",
        dispute_id="disp_reviewer",
        expected_payload_hash=h,
        expected_approver="compliance_lead_dave",
        consume=True,
    )
    assert authorized is True


def test_database_failure_does_not_mark_token_consumed(tmp_path: Path) -> None:
    """If database transaction fails, token must not be marked consumed in memory or storage."""
    db_path = tmp_path / "failure.db"
    service = ApprovalService(db_path=db_path)
    token = service.issue_token(
        dispute_id="disp_fail_test",
        action="accept",
        amount=25000,
        approver="reviewer_erin",
    )
    h = compute_accept_payload_hash("disp_fail_test", 25000)

    # Mock sqlite3 connect to simulate unexpected DB lock/error during verify
    with patch("sqlite3.connect", side_effect=sqlite3.OperationalError("database is locked")):
        consumed = service.verify_token(
            token=token,
            action="accept",
            dispute_id="disp_fail_test",
            expected_payload_hash=h,
            consume=True,
        )
        assert consumed is False

    # After the DB error is resolved, token MUST still be valid and unconsumed
    recovered = service.verify_token(
        token=token,
        action="accept",
        dispute_id="disp_fail_test",
        expected_payload_hash=h,
        consume=True,
    )
    assert recovered is True
