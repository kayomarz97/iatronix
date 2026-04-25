import logging
import time
from datetime import datetime, timezone

from fastapi import Request, Response
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

import firebase_admin
from firebase_admin import auth, credentials
from app.db.session import async_session
from app.middleware.rate_limit import check_per_key_rate_limit
from app.models.user import User

logger = logging.getLogger(__name__)

# Initialize Firebase Admin if not already initialized
try:
    firebase_admin.get_app()
except ValueError:
    import os
    cred_path = os.getenv("FIREBASE_CREDENTIALS")
    if cred_path and os.path.exists(cred_path):
        firebase_admin.initialize_app(credentials.Certificate(cred_path))
    else:
        firebase_admin.initialize_app()  # ADC fallback for local dev

EXEMPT_PATHS = {
    "/api/v1/health",
    "/api/v1/health/",
    "/api/v1/auth/openrouter/login",
    "/api/v1/auth/openrouter/callback",
}

_USER_CACHE_TTL = 300  # seconds
_USER_CACHE_MAX = 500
_user_cache: dict[str, tuple[User, float]] = {}


def _cache_get(uid: str) -> User | None:
    entry = _user_cache.get(uid)
    if entry and time.monotonic() < entry[1]:
        return entry[0]
    _user_cache.pop(uid, None)
    return None


def _cache_set(uid: str, user: User) -> None:
    if len(_user_cache) >= _USER_CACHE_MAX:
        # Evict oldest quarter when full
        cutoff = time.monotonic()
        expired = [k for k, (_, exp) in _user_cache.items() if exp < cutoff]
        for k in expired[:_USER_CACHE_MAX // 4]:
            _user_cache.pop(k, None)
    _user_cache[uid] = (user, time.monotonic() + _USER_CACHE_TTL)


def invalidate_user_cache(uid: str) -> None:
    """Call this when a user's role or LLM key changes."""
    _user_cache.pop(uid, None)


class FirebaseAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(status_code=401, content={"detail": "Missing or invalid Authorization header"})

        token = auth_header.split(" ")[1]

        try:
            # Verify Firebase token
            decoded_token = auth.verify_id_token(token)
            uid = decoded_token.get("uid")
        except Exception as e:
            logger.warning(f"Firebase token verification failed: {e}")
            return JSONResponse(status_code=401, content={"detail": "Invalid or expired token"})

        user = _cache_get(uid)
        if user is None:
            async with async_session() as session:
                from app.services.user_service import get_or_create_user
                email = decoded_token.get("email")
                user = await get_or_create_user(session, uid, email)
                _cache_set(uid, user)

        if user.expires_at and user.expires_at < datetime.now(timezone.utc):
            return JSONResponse(status_code=401, content={"detail": "User account expired"})

        # Per-key rate limit (post-auth) - using uid as key
        if await check_per_key_rate_limit(request, uid):
            return JSONResponse(
                status_code=429,
                content={"detail": "Per-user rate limit exceeded"},
            )

        # Attach user info to request state
        request.state.user = user
        request.state.key_id = uid  # Keeping 'key_id' naming for backward compatibility in rate_limit and query endpoints

        return await call_next(request)