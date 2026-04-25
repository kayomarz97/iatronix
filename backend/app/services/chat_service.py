"""Primary/fallback model routing for OpenRouter Gemma 4 queries.

Tries the primary model first; on specific error codes falls back to the
free fallback model and returns is_fallback=True so callers can signal
this to the frontend via a model_info SSE event.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
import openai
from fastapi import HTTPException

from app.config import settings
from app.services.llm_factory import create_llm

logger = logging.getLogger(__name__)

_FALLBACK_STATUS_CODES = {402, 429, 500}


def _is_fallback_trigger(exc: Exception) -> bool:
    """Return True if this exception should trigger a model fallback."""
    if isinstance(exc, HTTPException) and exc.status_code in _FALLBACK_STATUS_CODES:
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _FALLBACK_STATUS_CODES
    if isinstance(exc, (openai.RateLimitError, openai.InternalServerError)):
        return True
    return False


async def chat_with_fallback(
    messages: list,
    user_key: str,
    max_tokens: int,
    model_id: str | None = None,
) -> tuple[Any, bool]:
    """Invoke an OpenRouter LLM with automatic fallback.

    Returns (response, is_fallback).
    """
    primary = model_id or settings.openrouter_gemma_primary
    fallback = settings.openrouter_gemma_fallback

    try:
        llm = create_llm(primary, max_tokens, user_key, "openrouter")
        result = await llm.ainvoke(messages)
        return result, False
    except Exception as exc:
        if _is_fallback_trigger(exc):
            logger.warning(
                "Primary model %s failed (%s) — falling back to %s",
                primary,
                type(exc).__name__,
                fallback,
            )
            llm = create_llm(fallback, max_tokens, user_key, "openrouter")
            result = await llm.ainvoke(messages)
            return result, True
        raise
