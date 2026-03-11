"""
ASTRA — Audit Middleware
=========================
File: backend/app/middleware/audit_middleware.py   ← NEW

Captures request metadata (client IP, User-Agent) into a
``contextvars`` context so the audit service can read it
from anywhere in the call stack without explicit plumbing.
"""

import contextvars
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# Context variable — set per request
_request_ctx: contextvars.ContextVar[dict] = contextvars.ContextVar(
    "audit_request_ctx", default={}
)


def get_request_context() -> dict:
    """Read the current request's IP + UA from the context."""
    return _request_ctx.get()


class AuditContextMiddleware(BaseHTTPMiddleware):
    """
    Extracts IP address and User-Agent from every incoming request
    and stores them in a ``contextvars`` variable.  The audit service
    calls ``get_request_context()`` to retrieve them.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        ip = ""
        if request.client:
            ip = request.client.host

        # Prefer X-Forwarded-For when behind a reverse proxy
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            ip = forwarded.split(",")[0].strip()

        ctx = {
            "ip": ip,
            "user_agent": request.headers.get("user-agent", ""),
        }
        token = _request_ctx.set(ctx)
        try:
            response = await call_next(request)
        finally:
            _request_ctx.reset(token)
        return response
