import logging
import time
from collections import defaultdict
from threading import Lock

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import settings

WINDOW_SECONDS = 60

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
    redis_client, key: str, max_requests: int, window: int = WINDOW_SECONDS
) -> tuple[bool, int, int]:
    """Returns (is_limited, remaining, reset_ts)."""
    try:
        pipe = redis_client.pipeline()
        now = time.time()
        reset_ts = int(now) + window
        pipe.zremrangebyscore(key, 0, now - window)
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, window)
        results = await pipe.execute()
        count = results[2]
        remaining = max(0, max_requests - count)
        return count > max_requests, remaining, reset_ts
    except Exception:
        logger.warning("Redis rate limit failed, falling back to in-memory")
        limited = _fallback_limiter.is_rate_limited(key, max_requests, window)
        return limited, 0, int(time.time()) + window


class PreAuthRateLimitMiddleware(BaseHTTPMiddleware):
    """IP-based rate limiting that runs BEFORE auth."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Robust IP extraction order:
        # 1. CF-Connecting-IP (Directly from Cloudflare)
        # 2. X-Forwarded-For (First entry is the original client)
        # 3. X-Real-IP (Set by Nginx)
        # 4. request.client.host (Fallback to direct connection)
        cf_ip = request.headers.get("cf-connecting-ip")
        forwarded = request.headers.get("x-forwarded-for")
        real_ip = request.headers.get("x-real-ip")

        if cf_ip:
            client_ip = cf_ip
        elif forwarded:
            client_ip = forwarded.split(",")[0].strip()
        elif real_ip:
            client_ip = real_ip
        else:
            client_ip = request.client.host if request.client else "unknown"

        key = f"rate:ip:{client_ip}"
        limit = settings.rate_limit_ip_per_minute

        redis_client = getattr(request.app.state, "redis", None)
        if redis_client:
            limited, remaining, reset_ts = await _check_redis_rate_limit(
                redis_client, key, limit
            )
        else:
            limited = _fallback_limiter.is_rate_limited(key, limit)
            remaining, reset_ts = 0, int(time.time()) + WINDOW_SECONDS

        if limited:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."},
                headers={
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_ts),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_ts)
        return response


# ---------------------------------------------------------------------------
# Per-key (post-auth) rate limiting — path-aware tiered buckets
# ---------------------------------------------------------------------------

# GET-only endpoints that the UI polls constantly — never count against any bucket.
# These are idempotent reads; charging them would make the settings page unusable.
_EXEMPT_PATHS: frozenset[str] = frozenset({
    "/api/v1/auth/me",
    "/api/v1/auth/llm-key",
    "/api/v1/auth/openrouter/status",
    "/api/v1/service-keys",
    "/api/v1/service_keys",
})


def _is_exempt(method: str, path: str) -> bool:
    if method != "GET":
        return False
    return path in _EXEMPT_PATHS or path.startswith("/api/v1/history")


def _resolve_bucket(path: str, uid: str, is_premium: bool) -> tuple[str, int]:
    """Return (redis_key, limit) for the appropriate rate-limit bucket."""
    if path.startswith("/api/v1/query"):
        limit = (
            settings.rate_limit_query_premium_per_minute
            if is_premium
            else settings.rate_limit_query_free_per_minute
        )
        return f"rate:query:{uid}", limit

    if path.startswith("/api/v1/suggestions"):
        limit = (
            settings.rate_limit_suggest_premium_per_minute
            if is_premium
            else settings.rate_limit_suggest_free_per_minute
        )
        return f"rate:suggest:{uid}", limit

    # General bucket — everything else (auth writes, document uploads, etc.)
    limit = (
        settings.rate_limit_premium_key_per_minute
        if is_premium
        else settings.rate_limit_free_key_per_minute
    )
    return f"rate:key:{uid}", limit


async def check_per_key_rate_limit(
    request: Request,
    key_id: str,
    user=None,
) -> bool:
    """Post-auth per-key rate limit check.

    Routes each request into one of three independent Redis buckets (query /
    suggestions / general) based on path, with per-bucket per-tier limits.
    Idempotent GET reads used by the UI are exempt entirely.

    `user` must be passed by the caller — request.state.user is not yet set
    when this function runs inside FirebaseAuthMiddleware.
    """
    path = request.url.path

    if _is_exempt(request.method, path):
        return False

    is_premium = getattr(user, "tier", "free") == "premium"
    redis_key, limit = _resolve_bucket(path, key_id, is_premium)

    redis_client = getattr(request.app.state, "redis", None)
    if redis_client:
        limited, remaining, reset_ts = await _check_redis_rate_limit(
            redis_client, redis_key, limit
        )
        request.state.ratelimit_limit = limit
        request.state.ratelimit_remaining = remaining
        request.state.ratelimit_reset = reset_ts
        return limited

    return _fallback_limiter.is_rate_limited(redis_key, limit)
