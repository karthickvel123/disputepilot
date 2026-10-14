"""Deterministic deadline reminder generation and SQLite persistence.

Computes reminder timestamps at T-48h, T-24h, and T-12h before the merchant
response deadline and stores them in an SQLite table. Does NOT send external notifications.
"""

import sqlite3
import time
from pathlib import Path
from typing import Any

from disputepilot.core.deadlines import calculate_deadline
from disputepilot.core.models import DisputeCase

DEFAULT_REMINDERS_DB_PATH = Path("data/reminders.db")


def init_reminders_db(db_path: Path | str = DEFAULT_REMINDERS_DB_PATH) -> None:
    """Initialize the reminders SQLite table."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dispute_id TEXT NOT NULL,
                case_id TEXT NOT NULL,
                reminder_type TEXT NOT NULL,
                due_epoch INTEGER NOT NULL,
                is_due BOOLEAN NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                UNIQUE(dispute_id, reminder_type)
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders (is_due, due_epoch);")
        conn.commit()


def compute_and_record_reminders(
    case: DisputeCase,
    now: int | None = None,
    db_path: Path | str = DEFAULT_REMINDERS_DB_PATH,
) -> list[dict[str, Any]]:
    """Compute T-48h, T-24h, and T-12h reminders for a dispute and record them in SQLite.

    Args:
        case: DisputeCase to evaluate.
        now: Optional current unix timestamp in seconds.
        db_path: Path to SQLite reminders database.

    Returns:
        List of generated reminder records.
    """
    init_reminders_db(db_path)
    current_time = int(time.time()) if now is None else int(now)
    deadline_info = calculate_deadline(case.dispute, now=current_time)

    records: list[dict[str, Any]] = []
    if not deadline_info.respond_by:
        return records

    # Reminder intervals in seconds
    intervals = [
        ("T-48h", deadline_info.respond_by - 48 * 3600),
        ("T-24h", deadline_info.respond_by - 24 * 3600),
        ("T-12h", deadline_info.respond_by - 12 * 3600),
    ]

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        for r_type, due_epoch in intervals:
            is_due = 1 if current_time >= due_epoch else 0
            cursor.execute(
                """
                INSERT INTO reminders (dispute_id, case_id, reminder_type, due_epoch, is_due, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(dispute_id, reminder_type) DO UPDATE SET
                    is_due = excluded.is_due;
                """,
                (
                    case.dispute.id,
                    case.case_id,
                    r_type,
                    due_epoch,
                    is_due,
                    current_time,
                ),
            )
            records.append(
                {
                    "dispute_id": case.dispute.id,
                    "case_id": case.case_id,
                    "reminder_type": r_type,
                    "due_epoch": due_epoch,
                    "is_due": bool(is_due),
                    "created_at": current_time,
                }
            )
        conn.commit()

    return records


def get_due_reminders(
    now: int | None = None,
    db_path: Path | str = DEFAULT_REMINDERS_DB_PATH,
) -> list[dict[str, Any]]:
    """Retrieve all reminders that are currently due."""
    init_reminders_db(db_path)
    current_time = int(time.time()) if now is None else int(now)

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, dispute_id, case_id, reminder_type, due_epoch, is_due, created_at
            FROM reminders
            WHERE due_epoch <= ?
            ORDER BY due_epoch ASC;
            """,
            (current_time,),
        )
        rows = cursor.fetchall()

    return [
        {
            "id": r[0],
            "dispute_id": r[1],
            "case_id": r[2],
            "reminder_type": r[3],
            "due_epoch": r[4],
            "is_due": bool(r[5]),
            "created_at": r[6],
        }
        for r in rows
    ]
