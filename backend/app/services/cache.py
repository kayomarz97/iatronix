import hashlib
import logging
import re

import orjson

from app.config import settings

logger = logging.getLogger(__name__)


def normalize_query(query: str) -> str:
    """Normalize query for cache key generation."""
    q = query.lower().strip()
    q = re.sub(r"\s+", " ", q)
    q = re.sub(r"[?.!,;:]", "", q)  # strip internal + trailing punctuation
    q = q.strip()
    return q


def make_cache_key(query: str, query_type: str, model_id: str) -> str:
    """Build complete cache key: v{version}:{model}:{type}:{hash}."""
    normalized = normalize_query(query)
    query_hash = hashlib.sha256(normalized.encode()).hexdigest()
    return f"v{settings.prompt_version}:{model_id}:{query_type}:{query_hash}"


def _ttl_for_type(query_type: str) -> int:
    if query_type in ("drug", "disease", "comparative"):
        return settings.cache_ttl_structured
    return settings.cache_ttl_general


async def cache_get(
    redis_client, query: str, query_type: str, model_id: str
) -> dict | None:
    """Try to get a cached response. Returns None on miss or Redis failure."""
    if not redis_client:
        return None
    key = make_cache_key(query, query_type, model_id)
    try:
        data = await redis_client.get(key)
        if data:
            return orjson.loads(data)
    except Exception:
        logger.warning("Redis cache get failed", exc_info=True)
    return None


async def cache_set(
    redis_client, query: str, query_type: str, model_id: str, response: dict
) -> None:
    """Write response to cache. Silently skips on Redis failure."""
    if not redis_client:
        return
    key = make_cache_key(query, query_type, model_id)
    ttl = _ttl_for_type(query_type)
    try:
        await redis_client.setex(key, ttl, orjson.dumps(response))
    except Exception:
        logger.warning("Redis cache set failed", exc_info=True)


async def cache_get_any_version(
    redis_client, query: str, query_type: str, model_id: str
) -> dict | None:
    """Attempt to find any cached version of this query (for circuit breaker fallback)."""
    if not redis_client:
        return None
    normalized = normalize_query(query)
    query_hash = hashlib.sha256(normalized.encode()).hexdigest()
    pattern = f"v*:{model_id}:{query_type}:{query_hash}"
    try:
        async for key in redis_client.scan_iter(match=pattern, count=10):
            data = await redis_client.get(key)
            if data:
                return orjson.loads(data)
    except Exception:
        logger.warning("Redis cache scan failed", exc_info=True)
    return None
