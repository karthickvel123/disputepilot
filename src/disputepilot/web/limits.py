"""Hard request-body cap for the evidence upload route.

Counts bytes as they arrive and aborts with 413 as soon as the cap is exceeded, so an oversized
body is never fully buffered - regardless of whether Content-Length is missing, understated or
the request is chunked. Pure ASGI: no framework imports.
"""

from __future__ import annotations

import json
from typing import Any

SLACK_BYTES = 64 * 1024  # multipart framing/field overhead on top of the file limit


class _BodyTooLarge(Exception):
    pass


class BodyLimitMiddleware:
    def __init__(self, app: Any, max_bytes: int, path_suffix: str = "/evidence") -> None:
        self.app = app
        self.limit = max_bytes + SLACK_BYTES
        self.path_suffix = path_suffix

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http" or scope.get("method") != "POST" or not scope.get("path", "").endswith(self.path_suffix):
            await self.app(scope, receive, send)
            return

        declared = dict(scope.get("headers", [])).get(b"content-length", b"")
        if declared.isdigit() and int(declared) > self.limit:
            await self._reject(send)
            return

        seen = 0
        started = False

        async def limited_receive() -> dict[str, Any]:
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.limit:
                    raise _BodyTooLarge
            return message

        async def tracking_send(message: dict[str, Any]) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyTooLarge:
            if not started:
                await self._reject(send)

    @staticmethod
    async def _reject(send: Any) -> None:
        body = json.dumps({"detail": "Upload exceeds the maximum allowed size."}).encode()
        await send({"type": "http.response.start", "status": 413, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
