"""Persistent SQLite user store for DisputePilot authentication and RBAC."""

import sqlite3
import time
from pathlib import Path
from typing import Any

from disputepilot.web.auth import (
    DEFAULT_HASH,
    DEFAULT_REVIEWER_USER,
    hash_password,
    verify_password,
)


class UserStore:
    """Thread-safe SQLite user repository with password hashing and roles."""

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
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'reviewer',
                    created_at INTEGER NOT NULL
                )
                """
            )
            # Seed default demo reviewer and admin if table is empty
            cur = conn.execute("SELECT COUNT(*) FROM users")
            count = cur.fetchone()[0]
            if count == 0:
                now = int(time.time())
                conn.execute(
                    "INSERT INTO users (username, password_hash, full_name, role, created_at) VALUES (?, ?, ?, ?, ?)",
                    (DEFAULT_REVIEWER_USER, DEFAULT_HASH, "Authorized Merchant Reviewer", "reviewer", now),
                )
                conn.execute(
                    "INSERT INTO users (username, password_hash, full_name, role, created_at) VALUES (?, ?, ?, ?, ?)",
                    ("admin", DEFAULT_HASH, "Dispute Operations Admin", "admin", now),
                )
                conn.commit()

    def get_user(self, username: str) -> dict[str, Any] | None:
        """Fetch user by username."""
        clean_user = username.strip().lower()
        with self._get_conn() as conn:
            cur = conn.execute(
                "SELECT username, password_hash, full_name, role, created_at FROM users WHERE lower(username) = ?",
                (clean_user,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "username": row["username"],
                "password_hash": row["password_hash"],
                "full_name": row["full_name"],
                "role": row["role"],
                "created_at": row["created_at"],
            }

    def authenticate(self, username: str, password: str) -> dict[str, Any] | None:
        """Verify username and password against stored hash."""
        user = self.get_user(username)
        if not user:
            return None
        if verify_password(password, user["password_hash"]):
            return user
        return None

    def create_user(
        self, username: str, password: str, full_name: str, role: str = "reviewer"
    ) -> dict[str, Any]:
        """Create a new user with salted scrypt password hashing."""
        clean_user = username.strip()
        if not clean_user:
            raise ValueError("Username cannot be empty.")
        if len(password) < 6:
            raise ValueError("Password must be at least 6 characters.")
        if role not in {"admin", "reviewer", "auditor"}:
            role = "reviewer"

        pwd_hash = hash_password(password)
        now = int(time.time())
        try:
            with self._get_conn() as conn:
                conn.execute(
                    "INSERT INTO users (username, password_hash, full_name, role, created_at) VALUES (?, ?, ?, ?, ?)",
                    (clean_user, pwd_hash, full_name.strip() or clean_user, role, now),
                )
                conn.commit()
        except sqlite3.IntegrityError as err:
            raise ValueError(f"Username '{clean_user}' is already registered.") from err

        return {
            "username": clean_user,
            "full_name": full_name.strip() or clean_user,
            "role": role,
            "created_at": now,
        }

    def update_password(self, username: str, old_password: str, new_password: str) -> bool:
        """Update password for an existing user after verifying current password."""
        user = self.authenticate(username, old_password)
        if not user:
            return False
        if len(new_password) < 6:
            raise ValueError("New password must be at least 6 characters.")
        new_hash = hash_password(new_password)
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE lower(username) = ?",
                (new_hash, username.strip().lower()),
            )
            conn.commit()
        return True

    def list_users(self) -> list[dict[str, Any]]:
        """List all users without exposing password hashes."""
        with self._get_conn() as conn:
            cur = conn.execute("SELECT username, full_name, role, created_at FROM users ORDER BY created_at ASC")
            return [
                {
                    "username": row["username"],
                    "full_name": row["full_name"],
                    "role": row["role"],
                    "created_at": row["created_at"],
                }
                for row in cur.fetchall()
            ]


_default_user_store: UserStore | None = None


def get_user_store(data_dir: Path | str | None = None) -> UserStore:
    """Get or create singleton UserStore instance."""
    global _default_user_store
    if _default_user_store is None:
        if data_dir is None:
            data_dir = Path("data")
        db_path = Path(data_dir) / "users.db"
        _default_user_store = UserStore(db_path)
    return _default_user_store
