"""Authentication, signed session cookie management, and CSRF protection for DisputePilot."""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any

from fastapi import Request

SESSION_COOKIE_NAME = "disputepilot_session"
SESSION_MAX_AGE_SECONDS = 8 * 3600  # 8 hours


def hash_password(password: str, salt: bytes | None = None) -> str:
    """Hash a password using hashlib.scrypt with a 16-byte salt."""
    if salt is None:
        salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1)
    return f"{salt.hex()}:{key.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a plain password against a stored scrypt or sha256 hash."""
    if not stored_hash:
        return False
    try:
        if ":" in stored_hash:
            salt_hex, key_hex = stored_hash.split(":", 1)
            salt = bytes.fromhex(salt_hex)
            expected_key = bytes.fromhex(key_hex)
            derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1)
            return hmac.compare_digest(derived, expected_key)
        # Fallback for plain sha256 hex
        candidate_sha = hashlib.sha256(password.encode("utf-8")).hexdigest()
        return hmac.compare_digest(candidate_sha, stored_hash)
    except (ValueError, TypeError):
        return False


def get_configured_credentials() -> tuple[str | None, str | None]:
    """Retrieve expected username and password hash from environment. No default fallbacks."""
    user = os.environ.get("REVIEWER_USER", "").strip() or None
    pwd_hash = os.environ.get("REVIEWER_PASSWORD_HASH", "").strip() or None
    return user, pwd_hash


def get_session_secret() -> str | None:
    """Retrieve session signing key from environment. Must be at least 32 characters.

    Returns None if unset, empty, or shorter than 32 characters.
    """
    secret = os.environ.get("SESSION_SECRET", "").strip()
    if not secret or len(secret) < 32:
        return None
    return secret


def is_auth_configured() -> bool:
    """Return True if all required authentication and session variables are present and valid."""
    user, pwd_hash = get_configured_credentials()
    secret = get_session_secret()
    return bool(user and pwd_hash and secret)


def get_missing_auth_env_vars() -> list[str]:
    """Return a list of missing or invalid auth environment variables for startup warnings."""
    missing: list[str] = []
    if not os.environ.get("REVIEWER_USER", "").strip():
        missing.append("REVIEWER_USER")
    if not os.environ.get("REVIEWER_PASSWORD_HASH", "").strip():
        missing.append("REVIEWER_PASSWORD_HASH")
    sec = os.environ.get("SESSION_SECRET", "").strip()
    if not sec:
        missing.append("SESSION_SECRET")
    elif len(sec) < 32:
        missing.append("SESSION_SECRET (shorter than 32 characters)")
    return missing


def create_session_cookie_value(user: str) -> tuple[str, str]:
    """Create a signed session cookie containing user identity, unique CSRF token, and creation timestamp.

    Returns:
        Tuple of (cookie_value, csrf_token).

    Raises:
        RuntimeError if SESSION_SECRET is unset or invalid (< 32 chars).
    """
    secret_str = get_session_secret()
    if not secret_str:
        raise RuntimeError("SESSION_SECRET is unset or invalid (< 32 characters). Cannot issue session cookies.")

    csrf_token = secrets.token_hex(32)
    payload = {
        "user": user,
        "csrf_token": csrf_token,
        "created_at": int(time.time()),
    }
    payload_json = json.dumps(payload, separators=(",", ":"))
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("ascii")

    secret = secret_str.encode("utf-8")
    sig = hmac.new(secret, payload_b64.encode("ascii"), hashlib.sha256).hexdigest()
    cookie_value = f"{payload_b64}.{sig}"
    return cookie_value, csrf_token


def parse_session_cookie(cookie_value: str | None) -> dict[str, Any] | None:
    """Verify HMAC signature and decode session data. Rejects expired sessions (> 8h).

    Returns None if secret is unset/invalid or if signature/data/expiry check fails.
    """
    secret_str = get_session_secret()
    if not secret_str:
        return None
    if not cookie_value or "." not in cookie_value:
        return None

    payload_b64, sig = cookie_value.split(".", 1)
    secret = secret_str.encode("utf-8")
    expected_sig = hmac.new(secret, payload_b64.encode("ascii"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(sig, expected_sig):
        return None

    try:
        raw_json = base64.urlsafe_b64decode(payload_b64.encode("ascii")).decode("utf-8")
        data = json.loads(raw_json)
        if isinstance(data, dict) and "user" in data and "csrf_token" in data and "created_at" in data:
            created_at = int(data.get("created_at", 0))
            now = int(time.time())
            # Enforce 8-hour expiry and clock drift protection
            if (now - created_at > SESSION_MAX_AGE_SECONDS) or (created_at > now + 300):
                return None
            return data
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return None


def get_session(request: Request) -> dict[str, Any] | None:
    """Extract and validate current session from FastAPI request cookies."""
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    return parse_session_cookie(cookie)


def validate_csrf(session: dict[str, Any], submitted_token: str | None) -> bool:
    """Verify submitted CSRF token matches the session CSRF token."""
    if not submitted_token:
        return False
    expected = session.get("csrf_token", "")
    if not expected:
        return False
    return hmac.compare_digest(submitted_token.strip(), expected.strip())
