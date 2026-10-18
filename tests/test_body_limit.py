"""BodyLimitMiddleware enforces a hard cap by counting received bytes (pure ASGI, no HTTP stack)."""

import asyncio

from disputepilot.web.limits import SLACK_BYTES, BodyLimitMiddleware

LIMIT = 1000


async def _echo_app(scope, receive, send):  # consumes the whole body, then answers 200
    total = 0
    while True:
        msg = await receive()
        total += len(msg.get("body", b""))
        if not msg.get("more_body"):
            break
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": str(total).encode()})


def _run(chunks: list[bytes], headers=None, path="/cases/x/evidence", method="POST") -> tuple[int, bytes]:
    app = BodyLimitMiddleware(_echo_app, max_bytes=LIMIT)
    queue = [{"type": "http.request", "body": c, "more_body": i < len(chunks) - 1} for i, c in enumerate(chunks)]
    sent: list[dict] = []

    async def receive():
        return queue.pop(0)

    async def send(m):
        sent.append(m)

    scope = {"type": "http", "method": method, "path": path, "headers": headers or []}
    asyncio.run(app(scope, receive, send))
    return sent[0]["status"], sent[1]["body"]


def test_small_body_passes() -> None:
    assert _run([b"x" * 500]) == (200, b"500")


def test_chunked_body_without_content_length_is_cut_off() -> None:
    status, _ = _run([b"x" * 20000] * 4)  # 80000 bytes, no Content-Length header
    assert status == 413


def test_understated_content_length_does_not_bypass_the_limit() -> None:
    status, _ = _run([b"x" * 70000], headers=[(b"content-length", b"10")])
    assert status == 413


def test_declared_oversize_rejected_before_reading() -> None:
    status, _ = _run([b"x"], headers=[(b"content-length", str(LIMIT + SLACK_BYTES + 1).encode())])
    assert status == 413


def test_other_routes_are_untouched() -> None:
    assert _run([b"x" * 70000], path="/cases/x/review")[0] == 200
