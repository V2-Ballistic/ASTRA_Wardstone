"""
ASTRA — Security Headers Middleware
=====================================
File: backend/app/middleware/security_headers.py   ← NEW

Adds OWASP-recommended HTTP response headers on every response.
Maps to NIST 800-53 controls: SC-8 (Transmission Confidentiality),
SI-11 (Error Handling), SC-28 (Protection of Information at Rest).
"""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Injects security headers into every HTTP response.
    In development mode, CSP is relaxed to allow hot-reload.
    """

    def __init__(self, app, environment: str = "production"):
        super().__init__(app)
        self.environment = environment

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        # ── Transport security ──
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains; preload"
        )

        # ── Content sniffing prevention ──
        response.headers["X-Content-Type-Options"] = "nosniff"

        # ── Clickjacking prevention ──
        response.headers["X-Frame-Options"] = "DENY"

        # ── XSS filter (legacy browsers) ──
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # ── Content Security Policy ──
        if self.environment == "development":
            # Relaxed for Next.js hot-reload + inline styles
            csp = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-eval' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: blob:; "
                "connect-src 'self' ws: wss: http://localhost:*"
            )
        else:
            csp = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; "
                "connect-src 'self'; "
                "frame-ancestors 'none'; "
                "form-action 'self'; "
                "base-uri 'self'"
            )
        response.headers["Content-Security-Policy"] = csp

        # ── Referrer policy ──
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # ── Permissions policy (disable unnecessary browser APIs) ──
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), "
            "payment=(), usb=(), magnetometer=(), gyroscope=()"
        )

        # ── Prevent caching of authenticated responses ──
        if "authorization" in {k.lower() for k in request.headers.keys()}:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"

        return response
