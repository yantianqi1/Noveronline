"""Reject oversized HTTP bodies before multipart parsing allocates them."""

from __future__ import annotations

from collections.abc import Callable


class RequestSizeLimitMiddleware:
    def __init__(self, app: Callable, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max(1, int(max_bytes))

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope.get("type") == "http":
            content_length = next(
                (
                    value
                    for key, value in scope.get("headers", [])
                    if key.lower() == b"content-length"
                ),
                b"",
            )
            try:
                too_large = int(content_length) > self.max_bytes
            except (TypeError, ValueError):
                too_large = False
            if too_large:
                await send({
                    "type": "http.response.start",
                    "status": 413,
                    "headers": [(b"content-type", b"application/json"), (b"cache-control", b"no-store")],
                })
                await send({
                    "type": "http.response.body",
                    "body": b'{"success":false,"error":"request body is too large"}',
                })
                return
        await self.app(scope, receive, send)
