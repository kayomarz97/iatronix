import logging
import time
from collections import defaultdict
from threading import Lock

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)


class InMemorySlidingWindow:
    """Fallback rate limiter when Redis is unavailable."""

    def __init__(self):
        self._windows: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def is_rate_limited(
        self, key: str, max_requests: int, window_seconds: int = 60
    ) -> bool:
        now = time.time()
        cutoff = now - window_seconds
        with self._lock:
            self._windows[key] = [t for t in self._windows[key] if t > cutoff]
            if len(self._windows[key]) >= max_requests:
                return True
            self._windows[key].append(now)
            return False


_fallback_limiter = InMemorySlidingWindow()


async def _check_redis_rate_limit(
    redis_client, key: str, max_requests: int, window: int = 60
) -> bool:
    try:
        pipe = redis_client.pipeline()
        now = time.time()
        pipe.zremrangebyscore(key, 0, now - window)
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, window)
        results = await pipe.execute()
        return results[2] > max_requests
    except Exception:
        logger.warning("Redis rate limit failed, falling back to in-memory")
        return _fallback_limiter.is_rate_limited(key, max_requests, window)


class PreAuthRateLimitMiddleware(BaseHTTPMiddleware):
    """IP-based rate limiting that runs BEFORE auth."""

    async def dispatch(self, request: Request, call_next) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        key = f"rate:ip:{client_ip}"

        redis_client = getattr(request.app.state, "redis", None)
        if redis_client:
            limited = await _check_redis_rate_limit(
                redis_client, key, settings.rate_limit_ip_per_minute
            )
        else:
            limited = _fallback_limiter.is_rate_limited(
                key, settings.rate_limit_ip_per_minute
            )

        if limited:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."},
            )

        return await call_next(request)


async def check_per_key_rate_limit(request: Request, key_id: str) -> bool:
    """Post-auth per-key rate limit check. Called from auth middleware."""
    key = f"rate:key:{key_id}"
    redis_client = getattr(request.app.state, "redis", None)
    if redis_client:
        return await _check_redis_rate_limit(
            redis_client, key, settings.rate_limit_key_per_minute
        )
    return _fallback_limiter.is_rate_limited(key, settings.rate_limit_key_per_minute)
