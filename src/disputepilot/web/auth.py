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

DEFAULT_REVIEWER_USER = "reviewer"
DEFAULT_REVIEWER_PASSWORD = "password123"

# Salt for default hash derivation (used when REVIEWER_PASSWORD_HASH is unset)
DEFAULT_SALT = b"disputepilot_default_auth_salt_2026"


def hash_password(password: str, salt: bytes | None = None) -> str:
    """Hash a password using hashlib.scrypt with a 16-byte salt."""
    if salt is None:
        salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1)
    return f"{salt.hex()}:{key.hex()}"


# Pre-computed default hash for DEFAULT_REVIEWER_PASSWORD using DEFAULT_SALT
DEFAULT_HASH = hash_password(DEFAULT_REVIEWER_PASSWORD, salt=DEFAULT_SALT)


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


def _is_sim_mode() -> bool:
    return os.environ.get("DATA_MODE", "live").strip().lower() == "sim"


def _is_production_mode() -> bool:
    return os.environ.get("APP_ENV", "").strip().lower() in {"production", "prod"}


def get_configured_credentials() -> tuple[str, str]:
    """Retrieve the reviewer username and password hash from the environment.

    Live mode has NO built-in fallback: without REVIEWER_USER / REVIEWER_PASSWORD_HASH nobody can
    log in. The well-known demo credentials exist only when DATA_MODE=sim (synthetic fixtures).
    """
    user = os.environ.get("REVIEWER_USER", "").strip()
    pwd_hash = os.environ.get("REVIEWER_PASSWORD_HASH", "").strip()
    if user and pwd_hash:
        return user, pwd_hash
    # Never expose well-known demo credentials on a public production deployment,
    # even when DATA_MODE=sim. Missing configured credentials must fail closed.
    if _is_sim_mode() and not _is_production_mode():
        return user or DEFAULT_REVIEWER_USER, pwd_hash or DEFAULT_HASH
    return "", ""


SESSION_COOKIE_NAME = "disputepilot_session"


_EPHEMERAL_SECRET = secrets.token_hex(32)


def get_session_secret() -> str:
    """Retrieve the session signing key from the environment.

    If SESSION_SECRET is unset, a random per-process key is used (sessions then do not survive a
    restart) rather than a key committed to source. DATA_MODE=sim keeps a fixed dev key so tests
    stay deterministic.
    """
    configured = os.environ.get("SESSION_SECRET", "").strip()
    if configured:
        return configured
    if _is_sim_mode():
        return "disputepilot_dev_only_session_key_sim_mode"
    return _EPHEMERAL_SECRET


def create_session_cookie_value(user: str) -> tuple[str, str]:
    """Create a signed session cookie containing user identity and a unique CSRF token.

    Returns:
        Tuple of (cookie_value, csrf_token).
    """
    csrf_token = secrets.token_hex(32)
    payload = {
        "user": user,
        "csrf_token": csrf_token,
        "created_at": int(time.time()),
    }
    payload_json = json.dumps(payload, separators=(",", ":"))
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("ascii")

    secret = get_session_secret().encode("utf-8")
    sig = hmac.new(secret, payload_b64.encode("ascii"), hashlib.sha256).hexdigest()
    cookie_value = f"{payload_b64}.{sig}"
    return cookie_value, csrf_token


SESSION_MAX_AGE_SECONDS = 86400  # keep in sync with the cookie max_age set at login


def safe_next_path(candidate: str | None, default: str = "/") -> str:
    """Return ``candidate`` only if it is a same-site relative path, else ``default``.

    Rejects absolute URLs, scheme-relative ('//host'), backslash tricks and control characters,
    which would otherwise make the login redirect an open redirect.
    """
    if not candidate:
        return default
    c = candidate.strip()
    if not c.startswith("/") or c.startswith(("//", "/\\")):
        return default

    if any(ord(ch) < 32 or ch == "\\" for ch in c):
        return default
    return c


def parse_session_cookie(cookie_value: str | None, now: float | None = None) -> dict[str, Any] | None:
    """Verify HMAC signature and decode session data from cookie value."""
    if not cookie_value or "." not in cookie_value:
        return None

    payload_b64, sig = cookie_value.split(".", 1)
    secret = get_session_secret().encode("utf-8")
    expected_sig = hmac.new(secret, payload_b64.encode("ascii"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(sig, expected_sig):
        return None

    try:
        raw_json = base64.urlsafe_b64decode(payload_b64.encode("ascii")).decode("utf-8")
        data = json.loads(raw_json)
        if isinstance(data, dict) and "user" in data and "csrf_token" in data:
            created = data.get("created_at")
            current = time.time() if now is None else now
            # Enforce lifetime on the server: a copied cookie must not outlive the session.
            if not isinstance(created, int | float) or created > current + 60 or current - created > SESSION_MAX_AGE_SECONDS:
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
