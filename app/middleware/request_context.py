"""Pure-ASGI middleware that assigns a request ID and logs request lifecycle.

Uses a raw ASGI implementation (not ``BaseHTTPMiddleware``) so it works
correctly with streaming responses such as SSE.

The request ID is stored in a :class:`contextvars.ContextVar` that structlog
picks up automatically via ``merge_contextvars``, so every log line emitted
during request processing includes the ``request_id`` field.
"""

import logging
import time
from contextvars import ContextVar
from uuid import uuid4

import structlog
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")

logger = logging.getLogger(__name__)


class RequestContextMiddleware:
    """Attach a unique request ID, bind structlog context, and log timing."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # Honour an incoming X-Request-ID header; generate one otherwise
        raw_headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
        rid = ""
        for name, value in raw_headers:
            if name == b"x-request-id":
                rid = value.decode("latin-1")
                break
        if not rid:
            rid = str(uuid4())

        token = request_id_ctx.set(rid)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=rid)

        method = scope.get("method", "")
        path = scope.get("path", "")
        start = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.append("x-request-id", rid)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            log = logger.info if method != "GET" else logger.debug
            log(
                "%s %s completed in %.1fms",
                method,
                path,
                duration_ms,
                extra={"method": method, "path": path, "duration_ms": round(duration_ms, 1)},
            )
            request_id_ctx.reset(token)
            structlog.contextvars.clear_contextvars()
