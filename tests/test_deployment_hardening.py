"""Regression tests for safe deployment defaults and artifact packaging."""
from pathlib import Path

from disputepilot.web.auth import verify_password
from disputepilot.web.user_store import UserStore
from scripts.setup_keys import make_password_hash

ROOT = Path(__file__).resolve().parents[1]


def test_setup_password_hash_is_compatible_with_auth_verifier() -> None:
    password = "a-strong-reviewer-password"
    encoded = make_password_hash(password)
    assert verify_password(password, encoded)
    assert not verify_password("wrong-password", encoded)


def test_setup_script_does_not_switch_to_live_mode_automatically() -> None:
    source = (ROOT / "scripts" / "setup_keys.py").read_text(encoding="utf-8")
    assert 'data_mode = "sim"' in source
    assert 'data_mode = "live"' not in source
    assert "REVIEWER_PASSWORD_HASH={reviewer_password_hash}" in source
    assert "scrypt:32768:8:1$73367b" not in source


def test_dockerfile_copies_only_synthetic_fixtures() -> None:
    source = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY data ./data" not in source
    assert "COPY data/cases ./data/cases" in source
    assert "COPY data/cases_messy ./data/cases_messy" in source
    assert "COPY data/org_settings.json ./data/org_settings.json" in source


def test_production_cors_is_explicit_allowlist_only() -> None:
    source = (ROOT / "src" / "disputepilot" / "web" / "app.py").read_text(encoding="utf-8")
    assert 'https://.*\\.vercel\\.app' not in source
    assert 'https://.*\\.onrender\\.com' not in source
    assert "CORS_ALLOWED_ORIGINS" in (ROOT / "render.yaml").read_text(encoding="utf-8")


def test_production_user_store_removes_known_demo_accounts(tmp_path, monkeypatch) -> None:
    from disputepilot.web.auth import DEFAULT_HASH, DEFAULT_SALT, hash_password

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATA_MODE", "sim")
    db_path = tmp_path / "users.db"
    store = UserStore(db_path)
    # Production-mode migration should remove exact seeded demo identities.
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("REVIEWER_USER", "reviewer")
    configured_hash = hash_password("different-secure-password")
    monkeypatch.setenv("REVIEWER_PASSWORD_HASH", configured_hash)
    UserStore(db_path)
    with store._get_conn() as conn:
        rows = conn.execute("SELECT username, password_hash FROM users").fetchall()
    assert not any(row["username"].lower() == "admin" for row in rows)
    reviewer = next((row for row in rows if row["username"].lower() == "reviewer"), None)
    assert reviewer is not None
    assert reviewer["password_hash"] == configured_hash


def test_frontend_production_api_has_render_backend_fallback() -> None:
    """A production Vercel build must not fall back to same-origin /api/v1."""
    from pathlib import Path

    api_source = Path("frontend/src/api.js").read_text(encoding="utf-8")
    assert "https://disputepilot.onrender.com/api/v1" in api_source
    assert "import.meta.env.PROD ? DEFAULT_PRODUCTION_API : '/api/v1'" in api_source
    assert "Unable to reach the DisputePilot API" in api_source


def test_render_uses_persistent_writable_data_directory() -> None:
    """Production SQLite/evidence storage must be mounted on persistent storage."""
    from pathlib import Path

    render_config = Path("render.yaml").read_text(encoding="utf-8")
    assert "plan: starter" in render_config
    assert "mountPath: /var/data/disputepilot" in render_config
    assert "key: DATA_DIR\n        value: /var/data/disputepilot" in render_config


def test_sim_gateway_uses_configured_data_dir() -> None:
    """The simulator reads cases and writes drafts beneath DATA_DIR, not ephemeral defaults."""
    from pathlib import Path

    app_source = Path("src/disputepilot/web/app.py").read_text(encoding="utf-8")
    assert 'data_dir=settings.data_dir / "cases"' in app_source
    assert 'drafts_dir=settings.data_dir / "drafts"' in app_source
    assert "DATA_DIR is not writable" in app_source
