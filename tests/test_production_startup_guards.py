"""Tests for production startup guards (Phase 2, Tasks 6 & 7).

Verifies that when APP_ENV=production, startup fails fast with a clear ConfigError
if any of the following are true:
1. SESSION_SECRET is default or under 32 chars.
2. COOKIE_SECURE is not true.
3. Demo credentials are in use.
4. DATA_MODE=live but Razorpay key, secret or webhook secret is missing.
5. CORS allows a wildcard with credentials.
"""

import pytest

from disputepilot.config import ConfigError, Settings, validate_production_startup
from disputepilot.web.auth import hash_password


def _valid_prod_settings(**overrides) -> Settings:
    """Helper returning a valid production Settings object."""
    # A valid 64-char hex secret
    valid_secret = "a" * 32
    valid_hash = hash_password("prod_strong_password_2026!")
    defaults = {
        "app_env": "production",
        "data_mode": "sim",
        "session_secret": valid_secret,
        "cookie_secure": True,
        "reviewer_user": "ops_admin",
        "reviewer_password_hash": valid_hash,
        "cors_allowed_origins": "https://merchant.example.com",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_production_startup_passes_with_valid_config() -> None:
    """A properly configured production environment passes all checks."""
    settings = _valid_prod_settings()
    # Should not raise
    validate_production_startup(settings)


def test_production_startup_skips_in_development() -> None:
    """Non-production environments (e.g. development) are not blocked."""
    dev_settings = Settings(
        app_env="development",
        session_secret="short",
        cookie_secure=False,
        reviewer_user="reviewer",
        reviewer_password_hash="",
    )
    # Should not raise in development
    validate_production_startup(dev_settings, cors_origins=["*"])


def test_rule_1_session_secret_under_32_chars_fails() -> None:
    """SESSION_SECRET under 32 chars raises ConfigError in production."""
    settings = _valid_prod_settings(session_secret="too_short_secret_123")
    with pytest.raises(ConfigError) as exc_info:
        validate_production_startup(settings)
    assert "SESSION_SECRET" in str(exc_info.value)
    assert "at least 32 characters" in str(exc_info.value)


def test_rule_1_session_secret_default_value_fails() -> None:
    """SESSION_SECRET set to default/placeholder raises ConfigError in production."""
    settings = _valid_prod_settings(session_secret="change_me")
    with pytest.raises(ConfigError) as exc_info:
        validate_production_startup(settings)
    assert "SESSION_SECRET" in str(exc_info.value)


def test_rule_2_cookie_secure_not_true_fails() -> None:
    """COOKIE_SECURE=False raises ConfigError in production."""
    settings = _valid_prod_settings(cookie_secure=False)
    with pytest.raises(ConfigError) as exc_info:
        validate_production_startup(settings)
    assert "COOKIE_SECURE" in str(exc_info.value)
    assert "unencrypted HTTP" in str(exc_info.value)


def test_rule_3_demo_credentials_reviewer_user_fails() -> None:
    """Using username 'reviewer' raises ConfigError in production."""
    settings = _valid_prod_settings(reviewer_user="reviewer")
    with pytest.raises(ConfigError) as exc_info:
        validate_production_startup(settings)
    assert "Demo credentials are in use" in str(exc_info.value)


def test_rule_3_demo_password_hash_fails() -> None:
    """Using default demo password hash raises ConfigError in production."""
    demo_hash = hash_password("password123")
    settings = _valid_prod_settings(
        reviewer_user="lead_merchant",
        reviewer_password_hash=demo_hash,
    )
    with pytest.raises(ConfigError) as exc_info:
        validate_production_startup(settings)
    assert "Demo credentials are in use" in str(exc_info.value) or "demo password hash" in str(exc_info.value)


def test_rule_4_live_mode_missing_razorpay_key_id_fails() -> None:
    """DATA_MODE=live without RAZORPAY_KEY_ID raises ConfigError."""
    settings = _valid_prod_settings(
        data_mode="live",
        razorpay_key_id="",
        razorpay_key_secret="secret_123",
        razorpay_webhook_secret="whsec_123",
    )
    with pytest.raises(ConfigError) as exc_info:
        validate_production_startup(settings)
    assert "DATA_MODE=live" in str(exc_info.value)
    assert "RAZORPAY_KEY_ID" in str(exc_info.value)


def test_rule_4_live_mode_missing_razorpay_key_secret_fails() -> None:
    """DATA_MODE=live without RAZORPAY_KEY_SECRET raises ConfigError."""
    settings = _valid_prod_settings(
        data_mode="live",
        razorpay_key_id="rzp_test_123",
        razorpay_key_secret="",
        razorpay_webhook_secret="whsec_123",
    )
    with pytest.raises(ConfigError) as exc_info:
        validate_production_startup(settings)
    assert "DATA_MODE=live" in str(exc_info.value)
    assert "RAZORPAY_KEY_SECRET" in str(exc_info.value)


def test_rule_4_live_mode_missing_webhook_secret_fails() -> None:
    """DATA_MODE=live without RAZORPAY_WEBHOOK_SECRET raises ConfigError."""
    settings = _valid_prod_settings(
        data_mode="live",
        razorpay_key_id="rzp_test_123",
        razorpay_key_secret="secret_123",
        razorpay_webhook_secret="",
    )
    with pytest.raises(ConfigError) as exc_info:
        validate_production_startup(settings)
    assert "DATA_MODE=live" in str(exc_info.value)
    assert "RAZORPAY_WEBHOOK_SECRET" in str(exc_info.value)


def test_rule_4_live_mode_all_razorpay_secrets_provided_passes() -> None:
    """DATA_MODE=live with all secrets configured passes startup validation."""
    settings = _valid_prod_settings(
        data_mode="live",
        razorpay_key_id="rzp_test_abc123",
        razorpay_key_secret="secret_abc123",
        razorpay_webhook_secret="whsec_abc123",
    )
    # Should not raise
    validate_production_startup(settings)


def test_rule_5_cors_wildcard_with_credentials_fails() -> None:
    """CORS with wildcard '*' raises ConfigError in production."""
    settings = _valid_prod_settings(cors_allowed_origins="*")
    with pytest.raises(ConfigError) as exc_info:
        validate_production_startup(settings, cors_origins=["*"])
    assert "wildcard origin '*'" in str(exc_info.value)
