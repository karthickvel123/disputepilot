"""Persistent SQLite comments and notes store for reviewer collaboration."""

import sqlite3
import time
from pathlib import Path
from typing import Any


class CommentsStore:
    """Thread-safe SQLite store for reviewer notes and dispute comments."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dispute_comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT NOT NULL,
                    author TEXT NOT NULL,
                    comment TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_comments_case_id ON dispute_comments(case_id)"
            )
            conn.commit()

    def add_comment(self, case_id: str, author: str, comment: str) -> dict[str, Any]:
        """Add a comment for a case."""
        clean_text = comment.strip()
        if not clean_text:
            raise ValueError("Comment cannot be empty.")
        now = int(time.time())
        with self._get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO dispute_comments (case_id, author, comment, created_at) VALUES (?, ?, ?, ?)",
                (case_id, author, clean_text, now),
            )
            comment_id = cur.lastrowid
            conn.commit()

        return {
            "id": comment_id,
            "case_id": case_id,
            "author": author,
            "comment": clean_text,
            "created_at": now,
        }

    def list_comments(self, case_id: str) -> list[dict[str, Any]]:
        """List comments for a case in chronological order."""
        with self._get_conn() as conn:
            cur = conn.execute(
                "SELECT id, case_id, author, comment, created_at FROM dispute_comments WHERE case_id = ? ORDER BY created_at ASC",
                (case_id,),
            )
            return [
                {
                    "id": row["id"],
                    "case_id": row["case_id"],
                    "author": row["author"],
                    "comment": row["comment"],
                    "created_at": row["created_at"],
                }
                for row in cur.fetchall()
            ]


_default_comments_store: CommentsStore | None = None


def get_comments_store(data_dir: Path | str | None = None) -> CommentsStore:
    """Get or create singleton CommentsStore instance."""
    global _default_comments_store
    if _default_comments_store is None:
        if data_dir is None:
            data_dir = Path("data")
        db_path = Path(data_dir) / "comments.db"
        _default_comments_store = CommentsStore(db_path)
    return _default_comments_store
