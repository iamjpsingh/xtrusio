"""Request-scoped middlewares — request id + body-size cap (PAR-B M13, L16).

The ASGI middlewares are written against Starlette's
:class:`~starlette.types.ASGIApp` protocol (no FastAPI-isms) so they compose
cleanly with the rest of the middleware stack.

``RequestIdMiddleware`` runs FIRST in the stack so every downstream handler
(including the global exception handler) sees ``request.state.request_id`` and
binds it on structlog's contextvars for the log line.

``BodySizeLimitMiddleware`` rejects oversize bodies BEFORE they are buffered
into memory by Starlette's request reader — saves us from a 100MB POST
chewing up a worker even though Pydantic would have rejected it on shape.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Generate or accept ``X-Request-ID`` per request; surface on response.

    Reads the inbound ``X-Request-ID`` header so an upstream proxy / curl
    --header can pin the id; generates a fresh UUIDv4 otherwise. The id is:
      - stored on ``request.state.request_id`` for downstream handlers;
      - bound onto structlog's ``contextvars`` for the duration of the request
        so every log line carries it;
      - echoed in ``X-Request-ID`` on the response so clients can correlate.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        rid = request.headers.get("x-request-id") or str(uuid4())
        request.state.request_id = rid
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=rid)
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


class BodySizeLimitMiddleware:
    """Reject requests whose ``Content-Length`` exceeds ``max_bytes``.

    Hard-rejects with 413 ``payload_too_large`` BEFORE the body is read so
    a hostile upload can't pin a worker. Requests without a Content-Length
    header (chunked transfer) are inspected via a streaming counter that
    aborts the receive cycle when the threshold is crossed.
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        # Cheap path: Content-Length advertised — reject outright.
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    if int(value) > self.max_bytes:
                        await _send_413(send)
                        return
                except ValueError:
                    pass
                break
        # Streaming-chunked path: count bytes as they arrive; abort the
        # downstream receive if the cap is crossed mid-flight.
        received_bytes = 0
        cap = self.max_bytes

        async def _wrapped_receive() -> Any:
            nonlocal received_bytes
            message = await receive()
            if message.get("type") == "http.request":
                body = message.get("body", b"")
                received_bytes += len(body)
                if received_bytes > cap:
                    # Surface as a transport error so the ASGI app sees a
                    # truncated body and the global handler can format a 413.
                    return {"type": "http.disconnect"}
            return message

        await self.app(scope, _wrapped_receive, send)


async def _send_413(send: Any) -> None:
    """Emit a 413 JSON response via raw ASGI ``send`` calls.

    We bypass Starlette's Response object because it expects a populated
    ``scope`` dict; at this point we're cleaner just emitting the two
    ``http.response.*`` messages directly.
    """
    body = json.dumps({"detail": "payload_too_large"}).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
