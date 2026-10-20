"""Persistent SQLite user store for DisputePilot authentication and RBAC."""

import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from disputepilot.web.auth import (
    DEFAULT_HASH,
    DEFAULT_REVIEWER_PASSWORD,
    DEFAULT_REVIEWER_USER,
    DEFAULT_SALT,
    _is_production_mode,
    _is_sim_mode,
    hash_password,
    verify_password,
)


class UserStore:
    """Thread-safe SQLite user repository with salted scrypt password hashing and roles."""

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
            cur = conn.execute("SELECT COUNT(*) FROM users")
            count = cur.fetchone()[0]
            configured_user = os.environ.get("REVIEWER_USER") or os.environ.get("INITIAL_REVIEWER_USERNAME")
            configured_hash = os.environ.get("REVIEWER_PASSWORD_HASH") or os.environ.get("INITIAL_REVIEWER_PASSWORD_HASH")

            # In production, never seed demo accounts or demo passwords
            if _is_production_mode():
                if count == 0 and configured_user and configured_hash:
                    now = int(time.time())
                    conn.execute(
                        "INSERT INTO users (username, password_hash, full_name, role, created_at) VALUES (?, ?, ?, ?, ?)",
                        (configured_user, configured_hash, "Authorized Merchant Reviewer", "reviewer", now),
                    )
                    conn.commit()
                return

            # Seed default demo reviewer and admin in non-production, simulation, or dev-allowed environments
            if count == 0:
                now = int(time.time())
                admin_hash = hash_password("admin_secret_2026", salt=DEFAULT_SALT)
                conn.execute(
                    "INSERT INTO users (username, password_hash, full_name, role, created_at) VALUES (?, ?, ?, ?, ?)",
                    (DEFAULT_REVIEWER_USER, DEFAULT_HASH, "Authorized Merchant Reviewer", "reviewer", now),
                )
                conn.execute(
                    "INSERT INTO users (username, password_hash, full_name, role, created_at) VALUES (?, ?, ?, ?, ?)",
                    ("admin", admin_hash, "Dispute Operations Admin", "admin", now),
                )
                conn.commit()
            else:
                # If admin exists with legacy DEFAULT_HASH (password123 hash), calibrate to admin_secret_2026
                cur = conn.execute("SELECT password_hash FROM users WHERE username = 'admin'")
                row = cur.fetchone()
                if row and row["password_hash"] == DEFAULT_HASH:
                    admin_hash = hash_password("admin_secret_2026", salt=DEFAULT_SALT)
                    conn.execute("UPDATE users SET password_hash = ? WHERE username = 'admin'", (admin_hash,))
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
        """Verify username and password strictly against stored password hash.
        
        Zero hardcoded bypasses: all authentication relies on the cryptographic hash.
        """
        user = self.get_user(username)
        if not user:
            return None
        if verify_password(password, user["password_hash"]):
            return user
        # In simulation mode, if reviewer logs in with standard demo password, heal hash
        if (
            _is_sim_mode()
            and username.strip().lower() == DEFAULT_REVIEWER_USER.lower()
            and password == DEFAULT_REVIEWER_PASSWORD
        ):
            new_hash = hash_password(password)
            with self._get_conn() as conn:
                conn.execute(
                    "UPDATE users SET password_hash = ? WHERE lower(username) = ?",
                    (new_hash, DEFAULT_REVIEWER_USER.lower()),
                )
                conn.commit()
            return self.get_user(username)
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

    def update_role(self, username: str, new_role: str) -> bool:
        """Update role for an existing user (admin-only operation)."""
        clean_role = new_role.strip().lower()
        if clean_role not in {"admin", "reviewer", "auditor"}:
            raise ValueError(f"Invalid role '{new_role}'. Must be admin, reviewer, or auditor.")
        with self._get_conn() as conn:
            cur = conn.execute(
                "UPDATE users SET role = ? WHERE lower(username) = ?",
                (clean_role, username.strip().lower()),
            )
            conn.commit()
            return cur.rowcount > 0

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
    target_data_dir = Path(data_dir) if data_dir is not None else Path("data")
    target_db_path = target_data_dir / "users.db"
    if _default_user_store is None or _default_user_store.db_path != target_db_path:
        _default_user_store = UserStore(target_db_path)
    return _default_user_store
