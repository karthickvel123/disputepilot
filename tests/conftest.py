"""Pytest test configuration and fixtures."""

import pytest


@pytest.fixture(autouse=True)
def offline_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure pytest tests strictly run offline with FakeLLMClient."""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
