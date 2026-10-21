"""Environment-driven configuration for DisputePilot.

Nothing secret lives in code. Every key, endpoint and mode switch is read from the
process environment (optionally populated from a local, git-ignored ``.env``).

Modes
-----
``DATA_MODE=live`` (explicit opt-in only)
    Disputes, payments, orders and refunds come from the Razorpay API using the
    configured credentials. Writes (draft / submit / accept / document upload) go to
    the same API. Only ``rzp_test_`` keys are accepted unless ``ALLOW_LIVE_KEYS=true``.
``DATA_MODE=sim``
    Reads the synthetic fixtures under ``data/cases`` and uses ``SimGateway``. The UI
    shows a persistent "SIMULATED DATA" banner so it can never be mistaken for live.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_RAZORPAY_BASE_URL = "https://api.razorpay.com"
TEST_KEY_PREFIX = "rzp_test_"
LIVE_KEY_PREFIX = "rzp_live_"

_TRUE = {"1", "true", "yes", "on"}


def _load_dotenv_if_present() -> None:
    for env_path in (Path(".env"), Path(__file__).resolve().parents[2] / ".env"):
        if env_path.is_file():
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip("'\"")
                    if k and k not in os.environ:
                        os.environ[k] = v
            except OSError:
                pass
            break


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in _TRUE


class ConfigError(RuntimeError):
    """Raised for configuration that is unsafe to run with (never contains secret values)."""


@dataclass(frozen=True)

class Settings:
    """Resolved runtime settings. Secrets are held in memory only and never repr'd."""

    data_mode: str = "sim"
    razorpay_key_id: str = field(default="", repr=False)
    razorpay_key_secret: str = field(default="", repr=False)
    razorpay_base_url: str = DEFAULT_RAZORPAY_BASE_URL
    razorpay_webhook_secret: str = field(default="", repr=False)
    allow_live_keys: bool = False
    session_secret: str = field(default="", repr=False)
    reviewer_user: str = ""
    reviewer_password_hash: str = field(default="", repr=False)
    cookie_secure: bool = False
    llm_api_key: str = field(default="", repr=False)
    data_dir: Path = Path("data")
    max_upload_bytes: int = 4 * 1024 * 1024
    disputes_cache_ttl: int = 30
    push_draft_on_process: bool = False
    require_independent_approval: bool = False
    cors_allowed_origins: str = ""
    app_env: str = "development"

    # ---- derived -----------------------------------------------------------------
    @property
    def is_live(self) -> bool:
        return self.data_mode == "live"

    @property
    def is_sim(self) -> bool:
        return self.data_mode == "sim"

    @property
    def has_razorpay_credentials(self) -> bool:
        return bool(self.razorpay_key_id and self.razorpay_key_secret)

    @property
    def has_llm(self) -> bool:
        return bool(self.llm_api_key)

    @property
    def key_mode(self) -> str:
        """'test', 'live' or 'unset' - derived from the key prefix only."""
        if self.razorpay_key_id.startswith(TEST_KEY_PREFIX):
            return "test"
        if self.razorpay_key_id.startswith(LIVE_KEY_PREFIX):
            return "live"
        return "unset" if not self.razorpay_key_id else "unknown"

    @property
    def locker_db_path(self) -> Path:
        return self.data_dir / "locker.db"

    @property
    def approvals_db_path(self) -> Path:
        return self.data_dir / "approvals.db"

    def razorpay_problems(self) -> list[str]:
        """Why the Razorpay connection cannot be used (empty list = ready). No secret values."""
        out: list[str] = []
        if self.data_mode not in ("live", "sim"):
            out.append(f"DATA_MODE must be 'live' or 'sim' (got '{self.data_mode}').")
            return out
        if self.is_sim:
            return out
        if not self.has_razorpay_credentials:
            out.append("RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET are not set.")
        elif self.key_mode == "live" and not self.allow_live_keys:
            out.append(
                "A rzp_live_ key was supplied. This build only runs against test mode; "
                "set ALLOW_LIVE_KEYS=true to override deliberately."
            )
        elif self.key_mode == "unknown":
            out.append("RAZORPAY_KEY_ID must start with rzp_test_ (or rzp_live_).")
        return out

    def auth_problems(self) -> list[str]:
        """Why reviewers cannot log in."""
        out: list[str] = []
        is_prod = self.app_env in ("production", "prod")

        if is_prod:
            if not self.session_secret or len(self.session_secret) < 32:
                out.append("SESSION_SECRET must be set to a random string of at least 32 characters in production.")
            from disputepilot.web.auth import is_demo_password_hash
            if not self.reviewer_user or not self.reviewer_password_hash:
                out.append(
                    "REVIEWER_USER and REVIEWER_PASSWORD_HASH must be configured in production."
                )
            elif is_demo_password_hash(self.reviewer_password_hash):
                out.append(
                    "In production, REVIEWER_PASSWORD_HASH cannot use the default demo password hash. "
                    "Generate a production password hash with: python scripts/hash_password.py"
                )
            return out

        if not self.is_live:
            return out
        if not self.session_secret or len(self.session_secret) < 32:
            out.append("SESSION_SECRET must be set to a random string of at least 32 characters.")
        if not self.reviewer_user or not self.reviewer_password_hash:
            out.append(
                "REVIEWER_USER and REVIEWER_PASSWORD_HASH must be set "
                "(generate them with: python scripts/hash_password.py)."
            )
        return out

    def problems(self) -> list[str]:
        return self.razorpay_problems() + self.auth_problems()


def validate_production_startup(settings: Settings, cors_origins: list[str] | None = None) -> None:
    """Validate runtime environment before booting in production.

    Fails fast with a clear ConfigError if any of these are true:
    1. SESSION_SECRET is default or under 32 chars.
    2. COOKIE_SECURE is not true.
    3. Demo credentials are in use.
    4. DATA_MODE=live but the Razorpay key, secret or webhook secret is missing.
    5. CORS allows a wildcard with credentials.
    """
    if settings.app_env.lower() not in {"production", "prod"}:
        return

    # Rule 1: SESSION_SECRET is default or under 32 chars
    known_defaults = {"", "default", "secret", "change_me", "dev_secret", "insecure_default_secret_key_1234", "password123"}
    if not settings.session_secret or len(settings.session_secret) < 32 or settings.session_secret.lower() in known_defaults:
        raise ConfigError(
            "Production startup aborted: SESSION_SECRET must be configured with a cryptographically secure random string "
            "of at least 32 characters (e.g. generate via: python -c 'import secrets; print(secrets.token_hex(32))')."
        )

    # Rule 2: COOKIE_SECURE is not true
    if not settings.cookie_secure:
        raise ConfigError(
            "Production startup aborted: COOKIE_SECURE must be enabled (COOKIE_SECURE=true) in production "
            "to prevent session cookies from being transmitted over unencrypted HTTP."
        )

    # Rule 3: Demo credentials are in use
    from disputepilot.web.auth import is_demo_password_hash
    if (
        not settings.reviewer_user
        or not settings.reviewer_password_hash
        or settings.reviewer_user.lower() == "reviewer"
        or is_demo_password_hash(settings.reviewer_password_hash)
    ):
        raise ConfigError(
            "Production startup aborted: Demo credentials are in use. REVIEWER_USER and REVIEWER_PASSWORD_HASH must be "
            "set to dedicated production credentials, and cannot use the demo account ('reviewer') or demo password hash. "
            "Generate a secure hash using: python scripts/hash_password.py"
        )

    # Rule 4: DATA_MODE=live but Razorpay key, secret or webhook secret is missing
    if settings.data_mode == "live":
        missing_rzp = []
        if not settings.razorpay_key_id:
            missing_rzp.append("RAZORPAY_KEY_ID")
        if not settings.razorpay_key_secret:
            missing_rzp.append("RAZORPAY_KEY_SECRET")
        if not settings.razorpay_webhook_secret:
            missing_rzp.append("RAZORPAY_WEBHOOK_SECRET")
        if missing_rzp:
            raise ConfigError(
                f"Production startup aborted: DATA_MODE=live requires all Razorpay integration secrets to be set. "
                f"Missing: {', '.join(missing_rzp)}."
            )

    # Rule 5: CORS allows a wildcard with credentials
    origins = cors_origins if cors_origins is not None else (
        [o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()]
        if settings.cors_allowed_origins
        else []
    )
    if "*" in origins:
        raise ConfigError(
            "Production startup aborted: CORS configuration allows wildcard origin '*' while credentials are enabled. "
            "Configure an exact origin allowlist via CORS_ALLOWED_ORIGINS (e.g. https://your-merchant-app.com)."
        )


def load_settings() -> Settings:
    """Read settings from the environment right now (call again after changing env in tests)."""
    _load_dotenv_if_present()
    # Safe by default: credentials alone must never opt a deployment into live API calls.
    # Live mode requires an explicit DATA_MODE=live setting.
    raw_mode = _env("DATA_MODE")
    mode = raw_mode.lower() if raw_mode else "sim"
    env_name = _env("APP_ENV", "development").lower()

    return Settings(
        data_mode=mode,
        app_env=env_name,
        razorpay_key_id=_env("RAZORPAY_KEY_ID"),

        razorpay_key_secret=_env("RAZORPAY_KEY_SECRET"),
        razorpay_base_url=_env("RAZORPAY_BASE_URL", DEFAULT_RAZORPAY_BASE_URL).rstrip("/"),
        razorpay_webhook_secret=_env("RAZORPAY_WEBHOOK_SECRET"),
        allow_live_keys=_flag("ALLOW_LIVE_KEYS"),
        session_secret=_env("SESSION_SECRET"),
        reviewer_user=_env("REVIEWER_USER"),
        reviewer_password_hash=_env("REVIEWER_PASSWORD_HASH"),
        cookie_secure=_flag(
            "COOKIE_SECURE", default=env_name in {"production", "prod"}
        ),
        llm_api_key=_env("LLM_API_KEY") or _env("GEMINI_API_KEY"),
        data_dir=Path(_env("DATA_DIR", "data")),
        max_upload_bytes=int(_env("MAX_UPLOAD_BYTES", str(4 * 1024 * 1024))),
        disputes_cache_ttl=int(_env("DISPUTES_CACHE_TTL", "30")),
        push_draft_on_process=_flag("PUSH_DRAFT_ON_PROCESS"),
        # Separation of duties is enabled by default in production; dev/test stays convenient.
        require_independent_approval=_flag(
            "REQUIRE_INDEPENDENT_APPROVAL",
            default=env_name in {"production", "prod"},
        ),
        cors_allowed_origins=_env("CORS_ALLOWED_ORIGINS"),
    )
