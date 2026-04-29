"""
ASTRA — Request Body Size Limit Middleware
===========================================
File: backend/app/middleware/body_size_limit.py

ASGI middleware enforcing a per-request body size cap. Rejects oversized
uploads with 413 Payload Too Large *before* the route handler reads any
data, preventing memory-exhaustion DoS via large file uploads.

Limit configurable via the ``MAX_UPLOAD_BYTES`` env var; default 50 MB.

Covers AUDIT_FINDINGS F-018.

Notes:
  - Inspects the ``Content-Length`` header. Chunked / streaming uploads
    that omit Content-Length are passed through; route handlers must
    enforce their own limit (e.g. via streaming reads with a byte counter).
  - Register in ``main.py`` ABOVE the routers so the rejection happens
    before any handler-level dependency runs.
"""

import os

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


_DEFAULT_MAX_BYTES = 52_428_800  # 50 MB


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose Content-Length exceeds *max_bytes*."""

    def __init__(self, app, max_bytes: int | None = None):
        super().__init__(app)
        self.max_bytes = (
            max_bytes
            if max_bytes is not None
            else int(os.getenv("MAX_UPLOAD_BYTES", str(_DEFAULT_MAX_BYTES)))
        )

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        cl = request.headers.get("content-length")
        if cl:
            try:
                size = int(cl)
            except ValueError:
                size = 0
            if size > self.max_bytes:
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": (
                            f"Request body too large "
                            f"({size:,} bytes > limit {self.max_bytes:,} bytes)"
                        )
                    },
                )
        return await call_next(request)
