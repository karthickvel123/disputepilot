"""Approval service and token validation for sensitive dispute operations."""

import hashlib
import json
import secrets
import time
from typing import Any

from pydantic import BaseModel, Field


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

    def __init__(self, token_ttl_seconds: int = 1800) -> None:
        """Initialize the approval service.

        Args:
            token_ttl_seconds: Lifetime of an approval token in seconds (default 30 minutes).
        """
        self.token_ttl_seconds = token_ttl_seconds
        self._tokens: dict[str, ApprovalToken] = {}

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
        self._tokens[token_str] = record
        return token_str

    def get_token_record(self, token: str | None) -> ApprovalToken | None:
        """Retrieve token record if it exists."""
        if not token:
            return None
        return self._tokens.get(token)

    def verify_token(
        self,
        token: str | None,
        action: str,
        dispute_id: str,
        expected_payload_hash: str | None = None,
        now: int | None = None,
        consume: bool = True,
    ) -> bool:
        """Verify that a given approval token is valid, unused, unexpired, and matches content.

        Args:
            token: The token string to verify.
            action: Expected action ('accept' or 'submit').
            dispute_id: Expected dispute ID.
            expected_payload_hash: SHA-256 hash recomputed at call time.
            now: Current unix timestamp in seconds (injectable).
            consume: Whether to mark the token as used upon successful verification.

        Returns:
            True if valid, False otherwise.
        """
        if not token or token not in self._tokens:
            return False

        record = self._tokens[token]
        current_time = int(time.time()) if now is None else int(now)

        if record.used:
            return False
        if record.expires_at < current_time:
            return False
        if record.dispute_id != dispute_id:
            return False
        if record.action != action.lower():
            return False
        if expected_payload_hash is not None and record.payload_hash != expected_payload_hash:
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
        now: int | None = None,
    ) -> None:
        """Validate approval token and content binding or raise ApprovalRequired.

        Args:
            token: The token string to check.
            action: Expected action ('accept' or 'submit').
            dispute_id: Expected dispute ID.
            expected_payload_hash: Recomputed hash of exact payload being acted on.
            now: Current unix timestamp in seconds.

        Raises:
            ApprovalRequired: If token is missing, invalid, expired, used, or payload hash mismatches.
        """
        if not self.verify_token(
            token=token,
            action=action,
            dispute_id=dispute_id,
            expected_payload_hash=expected_payload_hash,
            now=now,
        ):
            raise ApprovalRequired(
                f"Action '{action}' on dispute '{dispute_id}' requires a valid human approval token "
                f"matching the approved content."
            )
