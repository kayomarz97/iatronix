"""Dynamic medical search suggestions using NCBI MeSH + RxNorm APIs + user history."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Query, Request

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/suggestions", tags=["suggestions"])


async def _fetch_rxnorm(q: str, client: httpx.AsyncClient) -> list[str]:
    try:
        url = "https://rxnav.nlm.nih.gov/REST/spellingsuggestions.json"
        r = await client.get(url, params={"name": q}, timeout=3.0)
        if r.status_code == 200:
            data = r.json()
            return data.get("suggestionGroup", {}).get("suggestionList", {}).get("suggestion", [])[:6]
    except Exception:
        pass
    return []


async def _fetch_mesh(q: str, client: httpx.AsyncClient) -> list[str]:
    try:
        url = "https://id.nlm.nih.gov/mesh/lookup/entry"
        r = await client.get(url, params={"label": q, "limit": 6, "year": "current", "format": "json"}, timeout=3.0)
        if r.status_code == 200:
            data = r.json()
            return [item.get("label", "") for item in data if item.get("label")][:6]
    except Exception:
        pass
    return []


async def _fetch_user_history(q: str, user_id: Optional[int], redis) -> list[str]:
    if not redis or not user_id:
        return []
    try:
        key = f"history:suggestions:{user_id}:{q.lower()}"
        cached = await redis.get(key)
        if cached:
            return json.loads(cached)
        # Search user history from Redis history key (if stored)
        history_key = f"history:{user_id}"
        raw = await redis.lrange(history_key, 0, 99)
        prefix = q.lower()
        matches = [item for item in raw if item and item.lower().startswith(prefix)][:3]
        if matches:
            await redis.setex(key, 300, json.dumps(matches))
        return matches
    except Exception:
        return []


def _deduplicate(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        norm = item.strip().lower()
        if norm and norm not in seen:
            seen.add(norm)
            out.append(item.strip())
    return out


@router.get("")
async def get_suggestions(
    request: Request,
    q: str = Query(..., min_length=2, max_length=100),
    limit: int = Query(5, ge=1, le=10),
):
    if len(q.strip()) < 2:
        return {"suggestions": []}

    redis = getattr(request.app.state, "redis", None)

    # Cache per prefix (not per user — shared suggestions cache)
    cache_key = f"suggestions:{q.lower()}"
    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return {"suggestions": json.loads(cached)[:limit]}
        except Exception:
            pass

    # Get user history (personalized, fast)
    user = getattr(request.state, "user", None)
    user_id = getattr(user, "id", None) if user else None

    async with httpx.AsyncClient() as client:
        rxnorm_task = _fetch_rxnorm(q, client)
        mesh_task = _fetch_mesh(q, client)
        history_task = _fetch_user_history(q, user_id, redis)

        rxnorm, mesh, history = await asyncio.gather(rxnorm_task, mesh_task, history_task)

    # History first (personalized), then drugs (RxNorm), then conditions (MeSH)
    merged = _deduplicate([*history, *rxnorm, *mesh])[:10]

    if redis and merged:
        try:
            await redis.setex(cache_key, 3600, json.dumps(merged))
        except Exception:
            pass

    return {"suggestions": merged[:limit]}
