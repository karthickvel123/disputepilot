"""Append-only SQLite audit log with cryptographic hash chain integrity verification."""

import hashlib
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("disputepilot.audit")

DEFAULT_AUDIT_DB_PATH = Path("data/audit.db")
DEFAULT_DEAD_LETTER_PATH = Path("data/audit_dead_letter.jsonl")


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
    with sqlite3.connect(path, timeout=30.0) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
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


def _sanitize_audit_details(val: Any) -> Any:
    """Ensure raw approval tokens are never persisted in plaintext in audit logs."""
    if isinstance(val, dict):
        cleaned: dict[str, Any] = {}
        for k, v in val.items():
            if k == "approval_token":
                raw_str = str(v)
                token_hash = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()
                cleaned["approval_token_hash"] = token_hash
            else:
                cleaned[k] = _sanitize_audit_details(v)
        return cleaned
    if isinstance(val, list):
        return [_sanitize_audit_details(item) for item in val]
    if isinstance(val, str) and val.startswith("appr_"):
        return hashlib.sha256(val.encode("utf-8")).hexdigest()
    return val


def record_audit_event(
    case_id: str,
    action: str,
    actor: str = "system",
    details: dict[str, Any] | None = None,
    timestamp: int | None = None,
    dead_letter_path: Path | str = DEFAULT_DEAD_LETTER_PATH,
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
        dead_letter_path: Path to emergency JSONL dead-letter log.
        db_path: SQLite database path.

    Returns:
        The cryptographic entry_hash of the recorded event.
    """
    current_time = int(time.time()) if timestamp is None else int(timestamp)
    details_dict = _sanitize_audit_details(details or {})
    details_json = json.dumps(details_dict, sort_keys=True)
    payload_hash = compute_hash(details_dict)

    try:
        init_audit_db(db_path)
        with sqlite3.connect(db_path, timeout=30.0) as conn:
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
    except (sqlite3.Error, OSError) as exc:
        logger.error(
            "SQLite audit log error for case '%s' (action '%s'): %s. Appending to dead-letter log.",
            case_id,
            action,
            exc,
        )
        dl_path = Path(dead_letter_path)
        dl_path.parent.mkdir(parents=True, exist_ok=True)
        dead_record = {
            "timestamp": current_time,
            "case_id": case_id,
            "action": action,
            "actor": actor,
            "details": details_dict,
            "payload_hash": payload_hash,
            "error": str(exc),
        }
        with open(dl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(dead_record) + "\n")
        return compute_hash(dead_record)


def reconcile_audit_log(
    dead_letter_path: Path | str = DEFAULT_DEAD_LETTER_PATH,
    db_path: Path | str = DEFAULT_AUDIT_DB_PATH,
) -> int:
    """Reconcile unwritten audit records from dead-letter JSONL into the SQLite audit DB.

    Returns:
        Number of successfully reconciled entries.
    """
    dl_path = Path(dead_letter_path)
    if not dl_path.exists():
        return 0

    lines = dl_path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return 0

    reconciled = 0
    unprocessed_lines: list[str] = []
    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue
        try:
            item = json.loads(line_str)
            init_audit_db(db_path)
            with sqlite3.connect(db_path, timeout=30.0) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT entry_hash FROM audit_log ORDER BY id DESC LIMIT 1;")
                row = cursor.fetchone()
                prev_hash = row[0] if row else "GENESIS_ROOT_00000000000000000000"
                det_dict = item.get("details", {})
                det_json = json.dumps(det_dict, sort_keys=True)
                p_hash = item.get("payload_hash") or compute_hash(det_dict)
                e_hash = compute_entry_hash(
                    timestamp=int(item["timestamp"]),
                    case_id=item["case_id"],
                    action=item["action"],
                    actor=item["actor"],
                    payload_hash=p_hash,
                    prev_hash=prev_hash,
                )
                cursor.execute(
                    """
                    INSERT INTO audit_log (timestamp, case_id, action, actor, payload_hash, details_json, prev_hash, entry_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        int(item["timestamp"]),
                        item["case_id"],
                        item["action"],
                        item["actor"],
                        p_hash,
                        det_json,
                        prev_hash,
                        e_hash,
                    ),
                )
                conn.commit()
            reconciled += 1
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to reconcile audit entry (%d bytes), error: %s", len(line_str), exc)
            unprocessed_lines.append(line_str)

    if unprocessed_lines:
        dl_path.write_text("\n".join(unprocessed_lines) + "\n", encoding="utf-8")
    else:
        dl_path.unlink(missing_ok=True)

    return reconciled


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


def get_all_audit_events(
    limit: int = 100, offset: int = 0, db_path: Path | str = DEFAULT_AUDIT_DB_PATH
) -> tuple[list[dict[str, Any]], int]:
    """Retrieve paginated global audit events across all cases."""
    path = Path(db_path)
    if not path.exists():
        return [], 0

    with sqlite3.connect(path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM audit_log;")
        total = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT id, timestamp, case_id, action, actor, payload_hash, details_json, prev_hash, entry_hash
            FROM audit_log
            ORDER BY id DESC
            LIMIT ? OFFSET ?;
            """,
            (limit, offset),
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
    return events, total

