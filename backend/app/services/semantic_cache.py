"""
semantic_cache.py — pgvector-backed semantic query cache with SWR.

Lookup: embed the incoming query, search query_cache for cosine similarity
≥ semantic_cache_threshold. If hit and fresh → return cached response.
If hit and stale → return cached response + fire background revalidation.
If miss → run pipeline normally, store result asynchronously.

Pure utility functions (is_stale, is_cache_hit) are tested independently
with no DB dependency.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


# ── Pure utility functions (testable without DB) ──────────────────────────────


def is_stale(last_verified_at: Optional[datetime], swr_ttl_seconds: int) -> bool:
    """Return True if the cache entry is older than swr_ttl_seconds."""
    if last_verified_at is None:
        return True
    if last_verified_at.tzinfo is None:
        last_verified_at = last_verified_at.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - last_verified_at).total_seconds()
    return age > swr_ttl_seconds


def is_cache_hit(similarity: float, threshold: float) -> bool:
    """Return True if cosine similarity meets or exceeds the required threshold."""
    return similarity >= threshold


# ── DB-backed service functions ───────────────────────────────────────────────


async def semantic_cache_get(
    query: str,
    query_type: str,
    model_id: str,
) -> tuple[Optional[dict], Optional[int]]:
    """
    Look up a semantically similar cached response.

    Returns (response_dict, cache_id) on hit, or (None, None) on miss.
    The caller should check is_stale(entry.last_verified_at) to decide
    whether to trigger background revalidation.
    """
    if not settings.semantic_cache_enabled:
        return None, None

    try:
        import asyncio as _asyncio
        from sqlalchemy import select

        from app.db.session import async_session as session_factory
        from app.models.query_cache import QueryCache
        from app.services.embedder import Embedder

        embedder = Embedder.get_instance()
        embedding = await _asyncio.to_thread(embedder.embed_text, query)

        async with session_factory() as session:
            # pgvector cosine distance: 1 - cosine_similarity
            distance_expr = QueryCache.query_embedding.cosine_distance(embedding)
            similarity_expr = (1 - distance_expr).label("similarity")

            stmt = (
                select(QueryCache, similarity_expr)
                .where(QueryCache.query_type == query_type)
                .where(QueryCache.model_id == model_id)
                .where(1 - distance_expr >= settings.semantic_cache_threshold)
                .order_by(distance_expr)
                .limit(1)
            )

            result = await session.execute(stmt)
            row = result.first()

            if row is None:
                return None, None

            entry, similarity = row
            logger.debug(
                "Semantic cache hit: similarity=%.4f query_type=%s id=%d",
                similarity,
                query_type,
                entry.id,
            )
            return entry.response_json, entry.id

    except Exception:
        logger.debug("Semantic cache get failed — treating as miss", exc_info=True)
        return None, None


async def semantic_cache_set(
    query: str,
    query_type: str,
    model_id: str,
    response: dict,
) -> None:
    """
    Store a query response in the semantic cache (fire-and-forget safe).
    Silently skips on any failure.
    """
    if not settings.semantic_cache_enabled:
        return

    try:
        import asyncio as _asyncio

        from app.db.session import async_session as session_factory
        from app.models.query_cache import QueryCache
        from app.services.embedder import Embedder

        embedder = Embedder.get_instance()
        embedding = await _asyncio.to_thread(embedder.embed_text, query)

        async with session_factory() as session:
            entry = QueryCache(
                query_text=query,
                query_type=query_type,
                model_id=model_id,
                query_embedding=embedding,
                response_json=response,
                last_verified_at=datetime.now(timezone.utc),
            )
            session.add(entry)
            await session.commit()

        logger.debug("Semantic cache stored for query_type=%s", query_type)

    except Exception:
        logger.debug("Semantic cache set failed — skipping", exc_info=True)


async def semantic_cache_revalidate(
    cache_id: int,
    new_response: dict,
) -> None:
    """
    Update an existing cache entry with a fresh response and bump last_verified_at.
    Called after background revalidation completes.
    """
    if not settings.semantic_cache_enabled:
        return

    try:
        from sqlalchemy import update

        from app.db.session import async_session as session_factory
        from app.models.query_cache import QueryCache

        async with session_factory() as session:
            await session.execute(
                update(QueryCache)
                .where(QueryCache.id == cache_id)
                .values(
                    response_json=new_response,
                    last_verified_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()

        logger.debug("Semantic cache revalidated entry id=%d", cache_id)

    except Exception:
        logger.debug("Semantic cache revalidate failed", exc_info=True)
