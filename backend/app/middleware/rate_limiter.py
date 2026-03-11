"""
ASTRA — Rate Limiter Middleware
================================
File: backend/app/middleware/rate_limiter.py   ← NEW

In-memory token-bucket rate limiter with three tiers:
  - Default API:      100 req/min per IP
  - Auth endpoints:    10 req/min per IP   (brute-force protection)
  - Import endpoints:   5 req/min per IP

All limits are configurable via environment variables.

NIST 800-53 controls: SC-5 (Denial of Service Protection),
AC-7 (Unsuccessful Logon Attempts — complementary to account lockout).
"""

import os
import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class _TokenBucket:
    """Simple per-key token bucket."""

    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.refill_rate = refill_rate          # tokens per second
        self._buckets: dict[str, list] = {}     # key → [tokens, last_refill]

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        if key not in self._buckets:
            self._buckets[key] = [self.capacity, now]

        tokens, last = self._buckets[key]
        # Refill
        elapsed = now - last
        tokens = min(self.capacity, tokens + elapsed * self.refill_rate)
        self._buckets[key][1] = now

        if tokens >= 1.0:
            self._buckets[key][0] = tokens - 1.0
            return True

        self._buckets[key][0] = tokens
        return False

    def cleanup(self, max_age: float = 300.0):
        """Evict buckets not seen in *max_age* seconds."""
        now = time.monotonic()
        stale = [k for k, (_, ts) in self._buckets.items() if now - ts > max_age]
        for k in stale:
            del self._buckets[k]


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """
    Attach to the FastAPI app to enforce per-IP rate limits.

    Uses three tiers determined by URL path prefix:
      /auth/*     → auth_rpm
      /import*    → import_rpm
      everything  → default_rpm
    """

    def __init__(self, app, **kwargs):
        super().__init__(app)
        default_rpm = int(os.getenv("RATE_LIMIT_DEFAULT", "100"))
        auth_rpm = int(os.getenv("RATE_LIMIT_AUTH", "10"))
        import_rpm = int(os.getenv("RATE_LIMIT_IMPORT", "5"))

        self._default = _TokenBucket(default_rpm, default_rpm / 60.0)
        self._auth = _TokenBucket(auth_rpm, auth_rpm / 60.0)
        self._import = _TokenBucket(import_rpm, import_rpm / 60.0)

        self._last_cleanup = time.monotonic()

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"

    def _select_bucket(self, path: str) -> _TokenBucket:
        if "/auth/" in path or path.endswith("/auth"):
            return self._auth
        if "/import" in path:
            return self._import
        return self._default

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Periodic cleanup (every 5 min)
        now = time.monotonic()
        if now - self._last_cleanup > 300:
            self._default.cleanup()
            self._auth.cleanup()
            self._import.cleanup()
            self._last_cleanup = now

        ip = self._get_client_ip(request)
        bucket = self._select_bucket(request.url.path)

        if not bucket.allow(ip):
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please try again later."},
                headers={"Retry-After": "60"},
            )

        response = await call_next(request)
        return response
