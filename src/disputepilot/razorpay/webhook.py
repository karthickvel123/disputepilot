"""Razorpay webhook router with HMAC signature verification, deduplication, and SQLite storage."""

import hashlib
import hmac
import json
import logging
import os
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status

logger = logging.getLogger("disputepilot.razorpay.webhook")

DEFAULT_DB_PATH = Path("data/disputes.db")

# Callbacks invoked as (event_type, dispute_id) after a NEW (non-duplicate) event is stored.
# The web app registers one to drop its cached dispute list so the worklist reflects the event.
event_listeners: list[Callable[[str, str | None], None]] = []

# Fail-closed warning at startup if secret is unset or empty
_initial_secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET")
if not _initial_secret or not _initial_secret.strip():
    logger.warning(
        "RAZORPAY_WEBHOOK_SECRET is unset or empty at startup. "
        "Webhook endpoints will fail closed and reject all incoming requests."
    )


def init_db(db_path: Path | str = DEFAULT_DB_PATH) -> None:
    """Initialize the SQLite dispute_events table with atomic UNIQUE constraint on event_id."""
    path = Path(db_path)
    if str(db_path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(str(path)) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS dispute_events (
                event_id TEXT PRIMARY KEY UNIQUE,
                event_type TEXT NOT NULL,
                dispute_id TEXT,
                payment_id TEXT,
                payload TEXT NOT NULL,
                received_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_dispute_events_received ON dispute_events (received_at);
            CREATE INDEX IF NOT EXISTS idx_dispute_events_dispute ON dispute_events (dispute_id);
            """
        )


def is_event_processed(event_id: str, db_path: Path | str = DEFAULT_DB_PATH) -> bool:
    """Check whether a webhook event has already been recorded in SQLite."""
    init_db(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM dispute_events WHERE event_id = ?", (event_id,))
        return cursor.fetchone() is not None


def record_dispute_event_atomic(
    event_id: str,
    event_type: str,
    dispute_id: str | None,
    payment_id: str | None,
    payload_json: str,
    received_at: int,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> bool:
    """Atomically insert a new dispute event into the SQLite table.

    Deduplication is guaranteed via SQLite's UNIQUE constraint / PRIMARY KEY
    catching IntegrityError without race conditions.

    Returns:
        True if inserted, False if duplicate.
    """
    init_db(db_path)
    with sqlite3.connect(str(db_path), timeout=30.0) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO dispute_events (event_id, event_type, dispute_id, payment_id, payload, received_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (event_id, event_type, dispute_id, payment_id, payload_json, received_at),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


# Backwards compatibility alias
record_dispute_event = record_dispute_event_atomic


def sanitize_webhook_payload(event_json: dict[str, Any]) -> dict[str, Any]:
    """Prune sensitive customer information and retain only necessary fields for dispute processing."""
    if not isinstance(event_json, dict):
        return {}

    sanitized: dict[str, Any] = {
        "entity": str(event_json.get("entity", "event")),
        "event": str(event_json.get("event", "unknown")),
    }
    if "account_id" in event_json:
        sanitized["account_id"] = str(event_json["account_id"])
    if "created_at" in event_json:
        sanitized["created_at"] = event_json["created_at"]
    if "id" in event_json:
        sanitized["id"] = event_json["id"]

    # Extract only the dispute entity if present
    dispute_entity = (
        event_json.get("payload", {})
        .get("dispute", {})
        .get("entity", {})
    )
    if isinstance(dispute_entity, dict) and dispute_entity:
        allowed_dispute_fields = {
            "id",
            "entity",
            "payment_id",
            "amount",
            "currency",
            "amount_deducted",
            "reason_code",
            "status",
            "phase",
            "created_at",
            "respond_by",
        }
        sanitized_dispute = {
            k: v for k, v in dispute_entity.items() if k in allowed_dispute_fields
        }
        sanitized["payload"] = {"dispute": {"entity": sanitized_dispute}}
    else:
        sanitized["payload"] = {}

    return sanitized


def prune_dispute_events(max_age_days: int = 90, db_path: Path | str = DEFAULT_DB_PATH) -> int:
    """Prune webhook dispute events older than max_age_days for data retention compliance.

    Args:
        max_age_days: Retention horizon in days (default 90).
        db_path: Path to SQLite dispute events database.

    Returns:
        Number of pruned event rows.
    """
    cutoff = int(time.time()) - (max_age_days * 86400)
    init_db(db_path)
    with sqlite3.connect(str(db_path), timeout=30.0) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM dispute_events WHERE received_at < ?", (cutoff,))
        pruned = cursor.rowcount
        conn.commit()
        return pruned


def verify_webhook_signature(raw_body: bytes, signature: str | None, secret: str | None) -> bool:
    """Verify incoming X-Razorpay-Signature using HMAC-SHA256 over raw request body.

    Docs: https://razorpay.com/docs/webhooks/validate-test/

    Args:
        raw_body: Exact raw binary body of the HTTP request.
        signature: Hex digest from X-Razorpay-Signature header.
        secret: Configured RAZORPAY_WEBHOOK_SECRET.

    Returns:
        True if signature matches, False otherwise.
    """
    if not signature or not secret or not secret.strip():
        return False

    expected_signature = hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_signature, signature)


def create_webhook_router(
    webhook_secret: str | None = None,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> APIRouter:
    """Factory function creating a configured FastAPI webhook APIRouter."""
    r = APIRouter()

    configured_secret = (
        webhook_secret if webhook_secret is not None else os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")
    )
    if not configured_secret or not configured_secret.strip():
        logger.warning(
            "Webhook router initialized without a valid secret. "
            "Incoming requests will be rejected (fail-closed)."
        )

    @r.get("/health")
    def webhook_health() -> dict[str, Any]:
        """Unauthenticated liveness check: is the receiver armed, and how many events were stored."""
        armed = bool(
            (webhook_secret if webhook_secret is not None else os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")).strip()
        )
        init_db(db_path)
        with sqlite3.connect(str(db_path)) as conn:
            (total,) = conn.execute("SELECT COUNT(*) FROM dispute_events").fetchone()
        # Deliberately minimal: this route is unauthenticated, so no event types or dispute ids.
        return {"armed": armed, "events_received": total}

    @r.post("/webhook", status_code=status.HTTP_200_OK)
    @r.post("/", status_code=status.HTTP_200_OK)
    async def handle_webhook(
        request: Request,
        x_razorpay_signature: str | None = Header(None, alias="X-Razorpay-Signature"),
        x_razorpay_event_id: str | None = Header(None, alias="X-Razorpay-Event-Id"),
    ) -> dict[str, Any]:
        """Handle incoming Razorpay dispute webhooks."""
        secret = (
            webhook_secret if webhook_secret is not None else os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")
        )

        # 1. Fail Closed: If secret is unset or empty, reject every request
        if not secret or not secret.strip():
            logger.warning("Rejected webhook delivery: RAZORPAY_WEBHOOK_SECRET is unset or empty.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="RAZORPAY_WEBHOOK_SECRET is unset or empty. Webhook endpoint rejects all requests (fail-closed).",
            )

        raw_body = await request.body()

        # 2. Signature Verification
        if not verify_webhook_signature(raw_body, x_razorpay_signature, secret):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid webhook signature",
            )

        # 3. Extract Event payload and identifier
        try:
            event_json = json.loads(raw_body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON payload",
            )

        event_id = x_razorpay_event_id or event_json.get("id") or event_json.get("event_id")
        if not event_id:
            # Fallback deterministic hash if provider omitted event id
            event_id = f"evt_{hashlib.sha256(raw_body).hexdigest()[:16]}"

        # 4. Extract dispute details
        event_type = event_json.get("event", "unknown")
        dispute_entity = (
            event_json.get("payload", {})
            .get("dispute", {})
            .get("entity", {})
        )
        dispute_id = dispute_entity.get("id")
        payment_id = dispute_entity.get("payment_id")
        received_at = int(time.time())

        # 5. Atomic Deduplication with Sanitized Storage
        sanitized_payload = sanitize_webhook_payload(event_json)
        inserted = record_dispute_event_atomic(
            event_id=event_id,
            event_type=event_type,
            dispute_id=dispute_id,
            payment_id=payment_id,
            payload_json=json.dumps(sanitized_payload),
            received_at=received_at,
            db_path=db_path,
        )

        if not inserted:
            return {
                "status": "duplicate_ignored",
                "event_id": event_id,
                "message": "Event already processed.",
            }

        for listener in event_listeners:
            try:
                listener(event_type, dispute_id)
            except Exception:
                logger.exception("Webhook event listener failed")

        return {
            "status": "processed",
            "event_id": event_id,
            "event_type": event_type,
            "dispute_id": dispute_id,
        }

    return r


# Default package router reading RAZORPAY_WEBHOOK_SECRET from environment
default_router = create_webhook_router()
