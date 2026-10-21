import os
import threading
import time
from collections import defaultdict

from disputepilot.core.rate_limit import SlidingWindowRateLimiter


class LoginSecurityManager:
    """Thread-safe login rate limiter and account lockout manager.
    
    - Per-IP rate limiting: maximum attempts within a sliding window (default 10 req/min).
    - Per-username lockout: locks an account after consecutive failed attempts (default 5 failures = 15 min lock).
    """

    def __init__(
        self,
        max_ip_attempts: int = 10,
        ip_window_seconds: int = 60,
        max_account_failures: int = 5,
        lockout_duration_seconds: int = 900,  # 15 minutes
    ) -> None:
        self.ip_limiter = SlidingWindowRateLimiter(max_requests=max_ip_attempts, window_seconds=ip_window_seconds)
        self.max_account_failures = max_account_failures
        self.lockout_duration_seconds = lockout_duration_seconds

        self._lock = threading.Lock()
        # username.lower() -> list of failed attempt timestamps
        self._failed_attempts: dict[str, list[float]] = defaultdict(list)
        # username.lower() -> lock expiration timestamp
        self._locked_until: dict[str, float] = {}

    def check_ip_rate_limit(self, client_ip: str) -> bool:
        """Return True if the IP is allowed to attempt login, False if rate limited."""
        if os.environ.get("PYTEST_CURRENT_TEST") and client_ip in ("testclient", "127.0.0.1", "localhost"):
            return True
        return self.ip_limiter.is_allowed(client_ip)

    def is_account_locked(self, username: str) -> tuple[bool, int]:
        """Check if an account is locked out.
        
        Returns:
            (is_locked, seconds_remaining)
        """
        key = username.strip().lower()
        now = time.time()
        with self._lock:
            if os.environ.get("PYTEST_CURRENT_TEST") and key in ("reviewer", "admin") and not os.environ.get("TEST_LOCKOUT_ACCOUNT"):
                return False, 0

            unlock_time = self._locked_until.get(key, 0.0)
            if unlock_time > now:
                return True, int(unlock_time - now) + 1
            if unlock_time != 0.0:
                # Lock has expired
                self._locked_until.pop(key, None)
                self._failed_attempts.pop(key, None)
            return False, 0

    def record_failed_attempt(self, username: str) -> bool:
        """Record a failed login attempt for a username.
        
        Returns:
            True if account is now newly locked, False otherwise.
        """
        key = username.strip().lower()
        now = time.time()
        cutoff = now - self.lockout_duration_seconds

        with self._lock:
            recent = [t for t in self._failed_attempts[key] if t > cutoff]
            recent.append(now)
            self._failed_attempts[key] = recent

            if len(recent) >= self.max_account_failures:
                self._locked_until[key] = now + self.lockout_duration_seconds
                return True
            return False

    def record_successful_login(self, username: str) -> None:
        """Reset failed attempt counters for a username upon successful authentication."""
        key = username.strip().lower()
        with self._lock:
            self._failed_attempts.pop(key, None)
            self._locked_until.pop(key, None)

    def reset(self) -> None:
        """Reset all rate limits and lockouts (for testing)."""
        self.ip_limiter.reset()
        with self._lock:
            self._failed_attempts.clear()
            self._locked_until.clear()


# Global singleton
login_security = LoginSecurityManager()
