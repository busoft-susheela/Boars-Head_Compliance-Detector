"""Correlation ID middleware.

Attaches a unique ``correlation_id`` to every HTTP request so that all log
lines emitted during request handling (including downstream service calls,
worker calls via context propagation) carry the same ID.

Flow
----
1. Read ``X-Correlation-ID`` from the incoming request headers.
   If absent, generate a new UUID4.
2. Clear any stale structlog context from a previous request on this
   thread/task (``clear_contextvars``).
3. Bind ``correlation_id`` to the structlog context (``bind_contextvars``).
   Because ``_SHARED_PROCESSORS`` already includes ``merge_contextvars``,
   the ID appears automatically in every log event for this request.
4. Echo the correlation ID back in the ``X-Correlation-ID`` response header
   so callers can correlate their own logs with server logs.

asyncio safety
--------------
``structlog.contextvars`` is built on Python's ``contextvars.ContextVar``
which is copy-on-write per asyncio Task.  Each request runs in its own Task
so context changes here never bleed into other concurrent requests.
"""
from __future__ import annotations

import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

CORRELATION_ID_HEADER = "X-Correlation-ID"

logger = structlog.get_logger(__name__)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Bind a per-request correlation ID to the structlog context."""

    async def dispatch(self, request: Request, call_next) -> Response:
        correlation_id = (
            request.headers.get(CORRELATION_ID_HEADER) or str(uuid.uuid4())
        )

        # Start each request with a clean context, then bind the ID.
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        response = await call_next(request)
        response.headers[CORRELATION_ID_HEADER] = correlation_id
        return response
