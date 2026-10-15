"""DisputePilot package."""

import os
from pathlib import Path

__version__ = "0.1.0"


def _load_env_file() -> None:
    """Load variables from .env if present and not already in environment."""
    for candidate in (Path(".env"), Path(__file__).resolve().parent.parent.parent / ".env"):
        if candidate.exists() and candidate.is_file():
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
                break
            except OSError:
                pass


_load_env_file()
