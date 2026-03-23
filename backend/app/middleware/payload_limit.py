from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import settings

# Paths that allow larger payloads (e.g. file uploads).
# Matched by prefix against request.url.path.
_LARGE_PAYLOAD_PREFIXES = ("/api/v1/documents/upload",)
_LARGE_PAYLOAD_MAX_BYTES = 25 * 1024 * 1024  # 25 MB (matches nginx)


class PayloadLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method in ("POST", "PUT", "PATCH"):
            content_length = request.headers.get("content-length")
            if content_length:
                length = int(content_length)
                if any(request.url.path.startswith(p) for p in _LARGE_PAYLOAD_PREFIXES):
                    limit = _LARGE_PAYLOAD_MAX_BYTES
                else:
                    limit = settings.max_request_body_bytes
                if length > limit:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "detail": f"Request body too large. Maximum size: {limit} bytes"
                        },
                    )
        return await call_next(request)
