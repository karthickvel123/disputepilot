"""Append-only SQLite audit log with cryptographic hash chain integrity verification."""

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

DEFAULT_AUDIT_DB_PATH = Path("data/audit.db")


def compute_hash(data: Any) -> str:
    """Compute deterministic SHA-256 hex digest of string or JSON-serializable data."""
    if isinstance(data, (dict, list)):
        serialized = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    elif isinstance(data, bytes):
        serialized = data
    else:
        serialized = str(data).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def init_audit_db(db_path: Path | str = DEFAULT_AUDIT_DB_PATH) -> None:
    """Initialize the append-only SQLite audit log database."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                case_id TEXT NOT NULL,
                action TEXT NOT NULL,
                actor TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                details_json TEXT NOT NULL,
                prev_hash TEXT NOT NULL,
                entry_hash TEXT NOT NULL
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_case ON audit_log (case_id);")
        conn.commit()


def compute_entry_hash(
    timestamp: int,
    case_id: str,
    action: str,
    actor: str,
    payload_hash: str,
    prev_hash: str,
) -> str:
    """Compute cryptographic hash linking this entry to the preceding entry hash."""
    payload_str = f"{timestamp}:{case_id}:{action}:{actor}:{payload_hash}:{prev_hash}"
    return hashlib.sha256(payload_str.encode("utf-8")).hexdigest()


def record_audit_event(
    case_id: str,
    action: str,
    actor: str = "system",
    details: dict[str, Any] | None = None,
    timestamp: int | None = None,
    db_path: Path | str = DEFAULT_AUDIT_DB_PATH,
) -> str:
    """Append a tamper-evident audit record to the SQLite audit log.

    Actions include: viewed, edited, saved_draft, approved, accepted,
    extracted, recommended, verified.

    Args:
        case_id: The dispute case ID.
        action: The human or pipeline action name.
        actor: Identity of reviewer or system component.
        details: Metadata/payload details to be hashed and stored.
        timestamp: Optional injectable unix timestamp in seconds.
        db_path: SQLite database path.

    Returns:
        The cryptographic entry_hash of the recorded event.
    """
    init_audit_db(db_path)
    current_time = int(time.time()) if timestamp is None else int(timestamp)
    details_dict = details or {}
    details_json = json.dumps(details_dict, sort_keys=True)
    payload_hash = compute_hash(details_dict)

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        # Fetch the most recent entry hash across the log for chaining
        cursor.execute("SELECT entry_hash FROM audit_log ORDER BY id DESC LIMIT 1;")
        row = cursor.fetchone()
        prev_hash = row[0] if row else "GENESIS_ROOT_00000000000000000000"

        entry_hash = compute_entry_hash(
            timestamp=current_time,
            case_id=case_id,
            action=action,
            actor=actor,
            payload_hash=payload_hash,
            prev_hash=prev_hash,
        )

        cursor.execute(
            """
            INSERT INTO audit_log (timestamp, case_id, action, actor, payload_hash, details_json, prev_hash, entry_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                current_time,
                case_id,
                action,
                actor,
                payload_hash,
                details_json,
                prev_hash,
                entry_hash,
            ),
        )
        conn.commit()

    return entry_hash


def verify_audit_trail(db_path: Path | str = DEFAULT_AUDIT_DB_PATH) -> bool:
    """Verify cryptographic integrity of the entire append-only audit log hash chain.

    Returns:
        True if the hash chain is intact and un-tampered, False if any record
        was modified, deleted, inserted out of order, or forged.
    """
    path = Path(db_path)
    if not path.exists():
        return True

    with sqlite3.connect(path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, timestamp, case_id, action, actor, payload_hash, details_json, prev_hash, entry_hash
            FROM audit_log
            ORDER BY id ASC;
            """
        )
        rows = cursor.fetchall()

    if not rows:
        return True

    expected_prev = "GENESIS_ROOT_00000000000000000000"
    for r in rows:
        _id, ts, cid, act, actor, p_hash, det_json, prev_h, ent_h = r

        # 1. Verify prev_hash matches expected preceding hash
        if prev_h != expected_prev:
            return False

        # 2. Verify payload hash matches stored details_json
        try:
            details_obj = json.loads(det_json)
        except json.JSONDecodeError:
            return False
        if compute_hash(details_obj) != p_hash:
            return False

        # 3. Recompute and verify entry_hash
        recomputed_hash = compute_entry_hash(
            timestamp=ts,
            case_id=cid,
            action=act,
            actor=actor,
            payload_hash=p_hash,
            prev_hash=prev_h,
        )
        if recomputed_hash != ent_h:
            return False

        expected_prev = ent_h

    return True


def get_audit_events(case_id: str, db_path: Path | str = DEFAULT_AUDIT_DB_PATH) -> list[dict[str, Any]]:
    """Retrieve audit history for a specific dispute case."""
    path = Path(db_path)
    if not path.exists():
        return []

    with sqlite3.connect(path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, timestamp, case_id, action, actor, payload_hash, details_json, prev_hash, entry_hash
            FROM audit_log
            WHERE case_id = ?
            ORDER BY id ASC;
            """,
            (case_id,),
        )
        rows = cursor.fetchall()

    events: list[dict[str, Any]] = []
    for r in rows:
        events.append(
            {
                "id": r[0],
                "timestamp": r[1],
                "case_id": r[2],
                "action": r[3],
                "actor": r[4],
                "payload_hash": r[5],
                "details": json.loads(r[6]),
                "prev_hash": r[7],
                "entry_hash": r[8],
            }
        )
    return events
