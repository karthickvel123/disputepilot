"""Unit tests for Phase E: Pipeline orchestration, ApprovalService extensions, and Cryptographic Audit Log."""

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from disputepilot.core.triage import load_cases_from_directory
from disputepilot.pipeline import (
    compute_and_record_reminders,
    process_case,
    record_audit_event,
    verify_audit_trail,
)
from disputepilot.razorpay.approval import ApprovalRequired, ApprovalService
from disputepilot.razorpay.gateway import DisputesGateway


class SpyGateway(DisputesGateway):
    """Spy implementation of DisputesGateway to verify safety and call arguments."""

    def __init__(self) -> None:
        self.accept_calls: list[dict[str, Any]] = []
        self.contest_calls: list[dict[str, Any]] = []

    def list_disputes(
        self,
        status: str | None = None,
        phase: str | None = None,
        limit: int = 10,
        skip: int = 0,
    ) -> list[Any]:
        return []

    def fetch_dispute(self, dispute_id: str) -> Any:
        return {"id": dispute_id, "status": "open"}

    def accept_dispute(
        self,
        dispute_id: str,
        approval_token: str,
        idempotency_key: str | None = None,
    ) -> Any:
        self.accept_calls.append({"dispute_id": dispute_id, "token": approval_token})
        return {"id": dispute_id, "status": "accepted"}

    def contest_dispute(
        self,
        dispute_id: str,
        action: str,
        summary: str | None = None,
        amount: int | None = None,
        evidence: Any = None,
        approval_token: str | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        self.contest_calls.append({
            "dispute_id": dispute_id,
            "action": action,
            "summary": summary,
            "token": approval_token,
        })
        return {"id": dispute_id, "action": action, "status": "draft_saved"}

    def upload_document(self, file_content: bytes, file_name: str) -> dict[str, Any]:
        return {"id": "doc_test"}


def test_pipeline_never_submits(tmp_path: Path) -> None:
    """The pipeline strictly processes and drafts; it NEVER calls accept or submit on any gateway."""
    cases = load_cases_from_directory("data/cases")
    assert cases, "Simulated cases required"
    case = cases[0]

    spy_gw = SpyGateway()
    audit_db = tmp_path / "audit.db"
    reminders_db = tmp_path / "reminders.db"
    drafts_dir = tmp_path / "drafts"

    result = process_case(
        case_id=case.case_id,
        gateway=spy_gw,
        drafts_dir=drafts_dir,
        audit_db_path=audit_db,
        reminders_db_path=reminders_db,
    )

    # 1. Pipeline never calls accept
    assert len(spy_gw.accept_calls) == 0, "Pipeline must NEVER call accept!"

    # 2. Pipeline contest call is strictly action='draft', never submit
    assert len(spy_gw.contest_calls) == 1
    assert spy_gw.contest_calls[0]["action"] == "draft", "Pipeline must NEVER submit contest without human approval!"

    # 3. Artifacts generated
    assert result.case_id == case.case_id
    assert result.recommendation is not None
    assert result.clean_draft is not None
    assert result.verifier_report is not None


def test_expired_approval_token_rejected() -> None:
    """An approval token past its TTL is strictly rejected for any action."""
    service = ApprovalService(token_ttl_seconds=1800)  # 30 minutes
    now = 1700000000

    token = service.issue_token(
        dispute_id="disp_test_123",
        action="submit",
        payload={"action": "submit", "reason": "valid"},
        approver="Senior Risk Analyst Priya",
        now=now,
    )

    # Valid within 30 minutes
    assert service.verify_token(
        token=token,
        action="submit",
        dispute_id="disp_test_123",
        expected_payload_hash=service.get_token_record(token).payload_hash,  # type: ignore[union-attr]
        now=now + 1799,
        consume=False,
    ) is True

    # Exactly 1 second past expiration
    expired_time = now + 1801
    assert service.verify_token(
        token=token,
        action="submit",
        dispute_id="disp_test_123",
        expected_payload_hash=service.get_token_record(token).payload_hash,  # type: ignore[union-attr]
        now=expired_time,
    ) is False

    with pytest.raises(ApprovalRequired):
        service.require_approval(
            token=token,
            action="submit",
            dispute_id="disp_test_123",
            expected_payload_hash=service.get_token_record(token).payload_hash,  # type: ignore[union-attr]
            now=expired_time,
        )


def test_approval_requires_named_reviewer() -> None:
    """Approval token issuance strictly fails if named human reviewer is missing or empty."""
    service = ApprovalService()

    with pytest.raises(ValueError, match="A named human approver is strictly required"):
        service.issue_token(
            dispute_id="disp_test_123",
            action="submit",
            payload={"action": "submit"},
            approver="",  # Empty reviewer
        )

    with pytest.raises(ValueError, match="A named human approver is strictly required"):
        service.issue_token(
            dispute_id="disp_test_123",
            action="submit",
            payload={"action": "submit"},
            approver="   ",  # Whitespace reviewer
        )


def test_audit_chain_detects_tampering(tmp_path: Path) -> None:
    """Cryptographic hash chain detects any modification, deletion, or forgery in audit trail."""
    db_path = tmp_path / "tamper_test_audit.db"

    # Record 3 events
    record_audit_event("case_1", "viewed", actor="Alice", db_path=db_path, timestamp=100)
    record_audit_event("case_1", "saved_draft", actor="Bob", db_path=db_path, timestamp=200)
    record_audit_event("case_1", "approved", actor="Carol", db_path=db_path, timestamp=300)

    # Initial state must be valid
    assert verify_audit_trail(db_path=db_path) is True

    # Tamper with row 2: change action from 'saved_draft' to 'edited_unauthorized'
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE audit_log SET action = 'edited_unauthorized' WHERE id = 2;")
        conn.commit()

    # Hash chain must immediately detect tampering
    assert verify_audit_trail(db_path=db_path) is False


def test_reminders_table_persists_schedule(tmp_path: Path) -> None:
    """Reminders at T-48h, T-24h, and T-12h are computed and written to table without external send."""
    cases = load_cases_from_directory("data/cases")
    case = cases[0]

    reminders_db = tmp_path / "reminders_test.db"
    records = compute_and_record_reminders(case=case, now=1700000000, db_path=reminders_db)

    assert len(records) == 3
    types = [r["reminder_type"] for r in records]
    assert "T-48h" in types
    assert "T-24h" in types
    assert "T-12h" in types


def test_audit_records_only_hash_of_approval_token_never_raw_token(tmp_path: Path) -> None:
    """Audit log records only a SHA-256 hash of the approval token, never the token itself."""
    import hashlib

    db_path = tmp_path / "token_audit_test.db"
    raw_token = "appr_secure_random_token_9876543210_abcdef"
    expected_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    record_audit_event(
        case_id="case_token_test",
        action="submit_contest",
        actor="Priya Sharma",
        details={
            "payload_hash": "dummy_payload_hash_123",
            "approval_token": raw_token,
        },
        db_path=db_path,
        timestamp=1700000000,
    )

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT details_json FROM audit_log WHERE case_id = 'case_token_test';")
        row = cursor.fetchone()
        assert row is not None
        details_json = row[0]

    # Raw token must NEVER appear anywhere in the persisted audit log
    assert raw_token not in details_json
    # The SHA-256 hash must be recorded
    assert expected_hash in details_json
    assert "approval_token_hash" in details_json


def test_persistent_approval_tokens_survive_restarts(tmp_path: Path) -> None:
    """Approval tokens persisted to SQLite survive process restarts and new service instances."""
    db_path = tmp_path / "approvals_test.db"

    service1 = ApprovalService(db_path=db_path)
    now = 1700000000
    payload = {"action": "submit", "evidence": "order_receipt"}

    token = service1.issue_token(
        dispute_id="disp_persist_123",
        action="submit",
        payload=payload,
        approver="Compliance Lead Ramesh",
        now=now,
    )

    # Re-instantiate ApprovalService simulating a server restart / new worker process
    service2 = ApprovalService(db_path=db_path)
    record = service2.get_token_record(token)
    assert record is not None
    assert record.dispute_id == "disp_persist_123"
    assert record.approver == "Compliance Lead Ramesh"
    assert record.used is False

    # Verify and consume the token in the second instance
    valid = service2.verify_token(
        token=token,
        action="submit",
        dispute_id="disp_persist_123",
        expected_payload_hash=record.payload_hash,
        now=now + 60,
        consume=True,
    )
    assert valid is True

    # Re-instantiate in a third instance - the token must now be marked as used in the database
    service3 = ApprovalService(db_path=db_path)
    second_attempt = service3.verify_token(
        token=token,
        action="submit",
        dispute_id="disp_persist_123",
        expected_payload_hash=record.payload_hash,
        now=now + 120,
    )
    assert second_attempt is False



