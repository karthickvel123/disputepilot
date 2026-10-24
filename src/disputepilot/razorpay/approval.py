import hashlib
import json
import logging
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("disputepilot.razorpay.approval")


class ApprovalRequired(Exception):
    """Raised when an accept or submit action is attempted without valid human approval."""

    def __init__(self, message: str = "Human approval token required for accept or submit operations.") -> None:
        super().__init__(message)
        self.message = message


def compute_payload_hash(data: Any) -> str:
    """Compute deterministic SHA-256 hex digest of payload data."""
    if isinstance(data, (dict, list)):
        serialized = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    elif isinstance(data, bytes):
        serialized = data
    else:
        serialized = str(data).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def compute_contest_payload_hash(payload: dict[str, Any]) -> str:
    """Compute SHA-256 hash of the exact contest payload for submission."""
    return compute_payload_hash(payload)


def compute_accept_payload_hash(dispute_id: str, amount: int | None = None) -> str:
    """Compute SHA-256 hash of dispute ID and amount for acceptance."""
    data = {"dispute_id": dispute_id, "amount": amount}
    return compute_payload_hash(data)


class ApprovalToken(BaseModel):
    """Record of an issued human approval token bound to exact payload content."""

    token: str
    dispute_id: str
    action: str  # "accept" or "submit"
    payload_hash: str  # SHA-256 hash of exact approved payload
    approver: str
    created_at: int
    expires_at: int
    used: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApprovalService:
    """Service responsible for issuing and verifying human approval tokens.

    Non-negotiable #1: Nothing is submitted or accepted without a human approval token.
    Tokens are cryptographically bound to the exact payload content being approved.
    """

    def __init__(self, token_ttl_seconds: int = 1800, db_path: Path | str | None = None) -> None:
        """Initialize the approval service.

        Args:
            token_ttl_seconds: Lifetime of an approval token in seconds (default 30 minutes).
            db_path: Optional path to SQLite database for durable token persistence across restarts.
        """
        self.token_ttl_seconds = token_ttl_seconds
        self.db_path = Path(db_path) if db_path is not None else None
        self._lock = threading.RLock()
        self._tokens: dict[str, ApprovalToken] = {}
        if self.db_path:
            self._init_db()

    def _init_db(self) -> None:
        if self.db_path:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(str(self.db_path), timeout=30.0) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=30000")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS approval_tokens (
                        token TEXT PRIMARY KEY,
                        dispute_id TEXT NOT NULL,
                        action TEXT NOT NULL,
                        payload_hash TEXT NOT NULL,
                        approver TEXT NOT NULL,
                        created_at INTEGER NOT NULL,
                        expires_at INTEGER NOT NULL,
                        used INTEGER NOT NULL DEFAULT 0,
                        metadata TEXT NOT NULL DEFAULT '{}'
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_approval_dispute ON approval_tokens (dispute_id)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_approval_used ON approval_tokens (used)"
                )
                conn.commit()

    def issue_token(
        self,
        dispute_id: str,
        action: str,
        payload: dict[str, Any] | None = None,
        payload_hash: str | None = None,
        amount: int | None = None,
        approver: str = "merchant_compliance_officer",
        now: int | None = None,
    ) -> str:
        """Issue a single-use human approval token bound to exact content hash.

        Args:
            dispute_id: The ID of the dispute (e.g. disp_...).
            action: Either 'accept' or 'submit'.
            payload: Exact contest payload dictionary (for submit) or payload data.
            payload_hash: Explicit SHA-256 hash (if pre-computed).
            amount: Dispute amount in paise (used to compute accept hash if payload omitted).
            approver: Identity or role of the human approver.
            now: Current unix timestamp in seconds (injectable).

        Returns:
            The issued approval token string.
        """
        if not approver or not approver.strip():
            raise ValueError("A named human approver is strictly required to issue an approval token.")

        act = action.lower()
        if payload_hash is None:
            if act == "submit":
                if payload is None:
                    raise ValueError("Submit action requires 'payload' or 'payload_hash' to bind approval.")
                computed_hash = compute_contest_payload_hash(payload)
            elif act == "accept":
                amt = amount if amount is not None else (payload.get("amount") if isinstance(payload, dict) else None)
                computed_hash = compute_accept_payload_hash(dispute_id=dispute_id, amount=amt)
            else:
                computed_hash = compute_payload_hash(payload or dispute_id)
        else:
            computed_hash = payload_hash

        current_time = int(time.time()) if now is None else int(now)
        token_str = f"appr_{secrets.token_urlsafe(24)}"

        record = ApprovalToken(
            token=token_str,
            dispute_id=dispute_id,
            action=act,
            payload_hash=computed_hash,
            approver=approver,
            created_at=current_time,
            expires_at=current_time + self.token_ttl_seconds,
            used=False,
        )

        with self._lock:
            self._tokens[token_str] = record

            if self.db_path:
                with sqlite3.connect(str(self.db_path), timeout=30.0) as conn:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO approval_tokens
                        (token, dispute_id, action, payload_hash, approver, created_at, expires_at, used, metadata)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            record.token,
                            record.dispute_id,
                            record.action,
                            record.payload_hash,
                            record.approver,
                            record.created_at,
                            record.expires_at,
                            1 if record.used else 0,
                            json.dumps(record.metadata),
                        ),
                    )
                    conn.commit()

        return token_str

    def get_token_record(self, token: str | None) -> ApprovalToken | None:
        """Retrieve token record if it exists, reading fresh state from persistent storage."""
        if not token:
            return None

        with self._lock:
            if self.db_path:
                with sqlite3.connect(str(self.db_path), timeout=30.0) as conn:
                    cursor = conn.execute(
                        "SELECT token, dispute_id, action, payload_hash, approver, created_at, expires_at, used, metadata "
                        "FROM approval_tokens WHERE token = ?",
                        (token,),
                    )
                    row = cursor.fetchone()
                    if row:
                        record = ApprovalToken(
                            token=row[0],
                            dispute_id=row[1],
                            action=row[2],
                            payload_hash=row[3],
                            approver=row[4],
                            created_at=row[5],
                            expires_at=row[6],
                            used=bool(row[7]),
                            metadata=json.loads(row[8]) if row[8] else {},
                        )
                        self._tokens[token] = record
                        return record
                return None

            return self._tokens.get(token)

    def verify_token(
        self,
        token: str | None,
        action: str,
        dispute_id: str,
        expected_payload_hash: str | None = None,
        expected_approver: str | None = None,
        now: int | None = None,
        consume: bool = True,
    ) -> bool:
        """Verify that a given approval token is valid, unused, unexpired, and matches content.

        Atomic execution:
        - When persistent DB is configured, uses an atomic conditional UPDATE with rowcount check
          to prevent double-consumption race conditions across concurrent processes/threads.
        - When in-memory, guarded by thread lock.

        Args:
            token: The token string to verify.
            action: Expected action ('accept' or 'submit').
            dispute_id: Expected dispute ID.
            expected_payload_hash: SHA-256 hash recomputed at call time.
            expected_approver: Optional expected approver identity.
            now: Current unix timestamp in seconds (injectable).
            consume: Whether to mark the token as used upon successful verification.

        Returns:
            True if valid and successfully consumed, False otherwise.
        """
        if not token or not str(token).strip():
            return False

        current_time = int(time.time()) if now is None else int(now)
        act = action.lower().strip()

        if self.db_path:
            with self._lock:
                try:
                    with sqlite3.connect(str(self.db_path), timeout=30.0, isolation_level="EXCLUSIVE") as conn:
                        cursor = conn.cursor()
                        if consume:
                            query = """
                                UPDATE approval_tokens
                                SET used = 1
                                WHERE token = ?
                                  AND used = 0
                                  AND expires_at >= ?
                                  AND dispute_id = ?
                                  AND action = ?
                            """
                            params: list[Any] = [token, current_time, dispute_id, act]
                            if expected_payload_hash is not None:
                                query += " AND payload_hash = ?"
                                params.append(expected_payload_hash)
                            if expected_approver is not None:
                                query += " AND approver = ?"
                                params.append(expected_approver)

                            cursor.execute(query, tuple(params))
                            conn.commit()
                            if cursor.rowcount == 1:
                                if token in self._tokens:
                                    self._tokens[token].used = True
                                return True
                            return False
                        else:
                            query = """
                                SELECT 1 FROM approval_tokens
                                WHERE token = ?
                                  AND used = 0
                                  AND expires_at >= ?
                                  AND dispute_id = ?
                                  AND action = ?
                            """
                            params = [token, current_time, dispute_id, act]
                            if expected_payload_hash is not None:
                                query += " AND payload_hash = ?"
                                params.append(expected_payload_hash)
                            if expected_approver is not None:
                                query += " AND approver = ?"
                                params.append(expected_approver)

                            cursor.execute(query, tuple(params))
                            return cursor.fetchone() is not None
                except sqlite3.Error as exc:
                    logger.error("Database error during token verification for token %s: %s", token, exc)
                    return False
        else:
            with self._lock:
                record = self._tokens.get(token)
                if record is None:
                    return False
                if record.used:
                    return False
                if record.expires_at < current_time:
                    return False
                if record.dispute_id != dispute_id:
                    return False
                if record.action != act:
                    return False
                if expected_payload_hash is not None and record.payload_hash != expected_payload_hash:
                    return False
                if expected_approver is not None and record.approver != expected_approver:
                    return False

                if consume:
                    record.used = True
                return True

    def require_approval(
        self,
        token: str | None,
        action: str,
        dispute_id: str,
        expected_payload_hash: str | None = None,
        expected_approver: str | None = None,
        now: int | None = None,
        consume: bool = True,
    ) -> None:
        """Validate approval token and content binding or raise ApprovalRequired.

        Args:
            token: The token string to check.
            action: Expected action ('accept' or 'submit').
            dispute_id: Expected dispute ID.
            expected_payload_hash: Recomputed hash of exact payload being acted on.
            expected_approver: Optional expected approver identity.
            now: Current unix timestamp in seconds.
            consume: Whether to consume the token on successful verification.

        Raises:
            ApprovalRequired: If token is missing, invalid, expired, used, or payload hash mismatches.
        """
        if not self.verify_token(
            token=token,
            action=action,
            dispute_id=dispute_id,
            expected_payload_hash=expected_payload_hash,
            expected_approver=expected_approver,
            now=now,
            consume=consume,
        ):
            raise ApprovalRequired(
                f"Action '{action}' on dispute '{dispute_id}' requires a valid human approval token "
                f"matching the approved content."
            )
