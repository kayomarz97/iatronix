import logging
from datetime import datetime, timezone

from fastapi import Request, Response
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.auth import parse_api_key, verify_key_secret
from app.db.session import async_session
from app.middleware.rate_limit import check_per_key_rate_limit
from app.models.user import User

logger = logging.getLogger(__name__)

EXEMPT_PATHS = {
    "/api/v1/health",
    "/api/v1/health/",
    "/api/v1/auth/register",
    "/api/v1/auth/register/",
    "/api/v1/auth/login",
    "/api/v1/auth/login/",
}


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        api_key = request.headers.get("X-API-Key")
        if not api_key:
            return JSONResponse(status_code=401, content={"detail": "Missing API key"})

        parsed = parse_api_key(api_key)
        if not parsed:
            return JSONResponse(
                status_code=401, content={"detail": "Invalid API key format"}
            )

        key_id, secret = parsed

        async with async_session() as session:
            result = await session.execute(select(User).where(User.key_id == key_id))
            user = result.scalar_one_or_none()

        if not user:
            return JSONResponse(status_code=401, content={"detail": "Invalid API key"})

        if not verify_key_secret(secret, user.key_hash):
            return JSONResponse(status_code=401, content={"detail": "Invalid API key"})

        if user.expires_at and user.expires_at < datetime.now(timezone.utc):
            return JSONResponse(status_code=401, content={"detail": "API key expired"})

        # Per-key rate limit (post-auth)
        if await check_per_key_rate_limit(request, key_id):
            return JSONResponse(
                status_code=429,
                content={"detail": "Per-key rate limit exceeded"},
            )

        # Attach user info to request state
        request.state.user = user
        request.state.key_id = key_id

        return await call_next(request)
