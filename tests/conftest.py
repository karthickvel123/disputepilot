"""Pytest test configuration and fixtures."""

import os

# The app reads DATA_MODE at import time. The existing suite exercises the synthetic fixtures,
# so default it to "sim"; live-mode tests build their own app wiring explicitly.
os.environ.setdefault("DATA_MODE", "sim")

import pytest


@pytest.fixture(autouse=True)
def offline_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure pytest tests strictly run offline with FakeLLMClient."""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
