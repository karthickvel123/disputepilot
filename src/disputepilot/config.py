"""Environment-driven configuration for DisputePilot.

Nothing secret lives in code. Every key, endpoint and mode switch is read from the
process environment (optionally populated from a local, git-ignored ``.env``).

Modes
-----
``DATA_MODE=live`` (default)
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

    data_mode: str = "live"
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
        """Why reviewers cannot log in (live mode only)."""
        out: list[str] = []
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


def load_settings() -> Settings:
    """Read settings from the environment right now (call again after changing env in tests)."""
    _load_dotenv_if_present()
    raw_mode = _env("DATA_MODE")
    if not raw_mode:
        has_rzp = bool(_env("RAZORPAY_KEY_ID"))
        mode = "live" if has_rzp else "sim"
    else:
        mode = raw_mode.lower()

    return Settings(
        data_mode=mode,
        razorpay_key_id=_env("RAZORPAY_KEY_ID"),

        razorpay_key_secret=_env("RAZORPAY_KEY_SECRET"),
        razorpay_base_url=_env("RAZORPAY_BASE_URL", DEFAULT_RAZORPAY_BASE_URL).rstrip("/"),
        razorpay_webhook_secret=_env("RAZORPAY_WEBHOOK_SECRET"),
        allow_live_keys=_flag("ALLOW_LIVE_KEYS"),
        session_secret=_env("SESSION_SECRET"),
        reviewer_user=_env("REVIEWER_USER"),
        reviewer_password_hash=_env("REVIEWER_PASSWORD_HASH"),
        cookie_secure=_flag(
            "COOKIE_SECURE", default=_env("APP_ENV").lower() in {"production", "prod"}
        ),
        llm_api_key=_env("LLM_API_KEY") or _env("GEMINI_API_KEY"),
        data_dir=Path(_env("DATA_DIR", "data")),
        max_upload_bytes=int(_env("MAX_UPLOAD_BYTES", str(4 * 1024 * 1024))),
        disputes_cache_ttl=int(_env("DISPUTES_CACHE_TTL", "30")),
        push_draft_on_process=_flag("PUSH_DRAFT_ON_PROCESS"),
    )
