"""Request body-size cap — enforced even without a Content-Length header.

Pure ASGI middleware. The Content-Length header is a fast reject, but a chunked
(Transfer-Encoding) request has no Content-Length, so we also count body bytes as
they stream in and reject once the cap is exceeded. Bodies are buffered only up to
the cap (then replayed to the app), so memory stays bounded — that is the whole
point: an attacker cannot stream an unbounded body past the limit.
"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import settings

# Paths that allow larger payloads (e.g. file uploads).
# Matched by prefix against the request path.
_LARGE_PAYLOAD_PREFIXES = ("/api/v1/documents/upload",)
_LARGE_PAYLOAD_MAX_BYTES = 25 * 1024 * 1024  # 25 MB (matches nginx)


class PayloadLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") not in ("POST", "PUT", "PATCH"):
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        limit = (
            _LARGE_PAYLOAD_MAX_BYTES
            if any(path.startswith(p) for p in _LARGE_PAYLOAD_PREFIXES)
            else settings.max_request_body_bytes
        )

        # Fast path: trust an explicit Content-Length to reject before reading.
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    if int(value) > limit:
                        await self._reject(send, limit)
                        return
                except ValueError:
                    pass
                break

        # Streaming path: buffer-and-count. Stops as soon as the cap is exceeded,
        # so no more than `limit` bytes are ever held in memory.
        buffered: list[Message] = []
        total = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                buffered.append(message)
                break
            total += len(message.get("body", b""))
            buffered.append(message)
            if total > limit:
                await self._reject(send, limit)
                return
            if not message.get("more_body", False):
                break

        # Replay the buffered messages first, then defer to the live receive.
        index = 0

        async def replay_receive() -> Message:
            nonlocal index
            if index < len(buffered):
                message = buffered[index]
                index += 1
                return message
            return await receive()

        await self.app(scope, replay_receive, send)

    async def _reject(self, send: Send, limit: int) -> None:
        body = (
            b'{"detail":"Request body too large. Maximum size: '
            + str(limit).encode()
            + b' bytes"}'
        )
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
