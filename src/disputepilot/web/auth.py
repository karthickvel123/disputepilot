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


def is_demo_password_hash(stored_hash: str) -> bool:
    """Check if the provided hash is the default demo hash or resolves to 'password123'."""
    if not stored_hash:
        return False
    if stored_hash == DEFAULT_HASH:
        return True
    return verify_password(DEFAULT_REVIEWER_PASSWORD, stored_hash)


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a plain password against a stored scrypt or sha256 hash."""
    if not stored_hash:
        return False
    try:
        if "$" in stored_hash:
            parts = stored_hash.split("$")
            if len(parts) >= 3 and parts[0].startswith("scrypt"):
                params = parts[0].split(":")
                n = int(params[1]) if len(params) > 1 and params[1].isdigit() else 16384
                r = int(params[2]) if len(params) > 2 and params[2].isdigit() else 8
                p = int(params[3]) if len(params) > 3 and params[3].isdigit() else 1
                salt = bytes.fromhex(parts[1])
                expected_key = bytes.fromhex(parts[2])
                derived = hashlib.scrypt(
                    password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=128 * 1024 * 1024
                )
                return hmac.compare_digest(derived, expected_key)
        if ":" in stored_hash:
            salt_hex, key_hex = stored_hash.split(":", 1)
            salt = bytes.fromhex(salt_hex)
            expected_key = bytes.fromhex(key_hex)
            derived = hashlib.scrypt(
                password.encode("utf-8"), salt=salt, n=16384, r=8, p=1, maxmem=128 * 1024 * 1024
            )
            return hmac.compare_digest(derived, expected_key)
        # Fallback for plain sha256 hex
        candidate_sha = hashlib.sha256(password.encode("utf-8")).hexdigest()
        return hmac.compare_digest(candidate_sha, stored_hash)
    except (ValueError, TypeError):
        return False


def _is_sim_mode() -> bool:
    return os.environ.get("DATA_MODE", "sim").strip().lower() == "sim"


def _is_production_mode() -> bool:
    return os.environ.get("APP_ENV", "").strip().lower() in {"production", "prod"}


def allow_dev_users() -> bool:
    """Return whether development/demo-user credentials are permitted.

    Disabled when APP_ENV is production/prod, or when DISPUTEPILOT_ALLOW_DEV_USERS is
    explicitly set to 'false' / '0' / 'no'.
    """
    if _is_production_mode():
        return False
    val = os.environ.get("DISPUTEPILOT_ALLOW_DEV_USERS", "").strip().lower()
    return val not in ("false", "0", "no")


def get_configured_credentials() -> tuple[str, str]:
    """Retrieve the reviewer username and password hash from the environment.

    Live mode has NO built-in fallback: without REVIEWER_USER / REVIEWER_PASSWORD_HASH nobody can
    log in. The well-known demo credentials exist only when DATA_MODE=sim and dev users are allowed.
    """
    user = os.environ.get("REVIEWER_USER", "").strip() or os.environ.get("INITIAL_REVIEWER_USERNAME", "").strip()
    pwd_hash = (
        os.environ.get("REVIEWER_PASSWORD_HASH", "").strip()
        or os.environ.get("INITIAL_REVIEWER_PASSWORD_HASH", "").strip()
    )
    if user and pwd_hash:
        if _is_production_mode() and is_demo_password_hash(pwd_hash):
            return "", ""
        return user, pwd_hash
    # Never expose well-known demo credentials on a public production deployment,
    # or when dev users are disabled, even when DATA_MODE=sim. Missing configured credentials must fail closed.
    if _is_sim_mode() and allow_dev_users():
        return user or DEFAULT_REVIEWER_USER, pwd_hash or DEFAULT_HASH
    return "", ""


SESSION_COOKIE_NAME = "disputepilot_session"


_EPHEMERAL_SECRET = secrets.token_hex(32)


def get_session_secret() -> str:
    """Retrieve the session signing key from the environment.

    If SESSION_SECRET is unset, a random per-process key is used (sessions then do not survive a
    restart) rather than a key committed to source. Only non-production sim mode with dev users uses a fixed dev key
    so local tests stay deterministic.
    """
    configured = os.environ.get("SESSION_SECRET", "").strip()
    if configured:
        return configured
    if _is_sim_mode() and allow_dev_users():
        return "disputepilot_dev_only_session_key_sim_mode"
    return _EPHEMERAL_SECRET


def create_session_cookie_value(user: str, role: str = "reviewer") -> tuple[str, str]:
    """Create a signed session cookie containing user identity, role, and a unique CSRF token.

    Returns:
        Tuple of (cookie_value, csrf_token).
    """
    csrf_token = secrets.token_hex(32)
    payload = {
        "user": user,
        "role": role,
        "csrf_token": csrf_token,
        "created_at": int(time.time()),
    }
    payload_json = json.dumps(payload, separators=(",", ":"))
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("ascii")

    secret = get_session_secret().encode("utf-8")
    sig = hmac.new(secret, payload_b64.encode("ascii"), hashlib.sha256).hexdigest()
    cookie_value = f"{payload_b64}.{sig}"
    return cookie_value, csrf_token


def get_session_max_age_seconds() -> int:
    """Retrieve session maximum age in seconds from environment or default to 86400 (24 hours)."""
    try:
        val = int(os.environ.get("SESSION_TTL_SECONDS", "86400"))
        return max(300, val)
    except (ValueError, TypeError):
        return 86400


SESSION_MAX_AGE_SECONDS = get_session_max_age_seconds()


def validate_password_strength(password: str, username: str = "", is_production: bool | None = None) -> None:
    """Validate password meets complexity requirements for financial review access.

    In development / simulation: minimum 8 characters, letters and digits.
    In production: minimum 10 characters, mixed case, and digits or special characters.
    """
    if is_production is None:
        is_production = _is_production_mode()

    if not password:
        raise ValueError("Password cannot be empty.")

    min_len = 10 if is_production else 8
    if len(password) < min_len:
        raise ValueError(f"Password must be at least {min_len} characters long.")

    if username and password.strip().lower() == username.strip().lower():
        raise ValueError("Password cannot match username.")

    has_letter = any(c.isalpha() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_symbol = any(not c.isalnum() for c in password)

    if not (has_letter and (has_digit or has_symbol)):
        raise ValueError("Password must contain both letters and numbers or symbols.")

    if is_production:
        if is_demo_password_hash(hash_password(password, salt=DEFAULT_SALT)):
            raise ValueError("Demo passwords are prohibited in production.")
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        if not (has_upper and has_lower):
            raise ValueError("Production password must contain both uppercase and lowercase letters.")


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
            max_age = get_session_max_age_seconds()
            if not isinstance(created, int | float) or created > current + 60 or current - created > max_age:
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


def get_cookie_samesite_and_secure(cookie_secure: bool = False) -> tuple[str, bool]:
    """Determine the SameSite and Secure attributes for session cookies.

    If COOKIE_SAMESITE is explicitly configured ('none', 'lax', 'strict'), that is used.
    Otherwise, if cookie_secure is True (HTTPS in production), default to 'none' to allow
    cross-origin session transmission (e.g., Vercel frontend calling Render backend).
    Note: Modern browsers reject SameSite=None unless Secure=True.
    """
    env_samesite = os.environ.get("COOKIE_SAMESITE", "").strip().lower()
    if env_samesite in ("none", "lax", "strict"):
        samesite = env_samesite
    elif cookie_secure:
        samesite = "none"
    else:
        samesite = "lax"

    if samesite == "none":
        cookie_secure = True

    return samesite, cookie_secure

