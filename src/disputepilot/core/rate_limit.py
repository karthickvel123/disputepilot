"""In-memory sliding window rate limiter for security-sensitive endpoints (webhooks, auth).

Pure Python implementation using monotonic clock with thread locking.
Supports per-key sliding windows (e.g. client IP or username).
"""

import threading
import time
from collections import defaultdict


class SlidingWindowRateLimiter:
    """Thread-safe sliding window rate limiter."""

    def __init__(self, max_requests: int, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def is_allowed(self, key: str) -> bool:
        """Check if request for `key` is allowed and record the timestamp if allowed."""
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            timestamps = self._requests[key]
            # Prune timestamps older than window
            valid = [t for t in timestamps if t > cutoff]
            if len(valid) >= self.max_requests:
                self._requests[key] = valid
                return False
            valid.append(now)
            self._requests[key] = valid
            return True

    def get_remaining(self, key: str) -> int:
        """Get remaining allowed requests in current window."""
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            timestamps = self._requests.get(key, [])
            valid = [t for t in timestamps if t > cutoff]
            return max(0, self.max_requests - len(valid))

    def reset(self, key: str | None = None) -> None:
        """Reset limiter for a single key or all keys."""
        with self._lock:
            if key is None:
                self._requests.clear()
            else:
                self._requests.pop(key, None)
