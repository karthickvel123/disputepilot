"""Smoke test for disputepilot package."""

import disputepilot


def test_smoke() -> None:
    """Verify that disputepilot can be imported successfully."""
    assert disputepilot.__version__ == "0.1.0"
