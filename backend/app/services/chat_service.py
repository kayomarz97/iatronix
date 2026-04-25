"""Primary/fallback model routing for OpenRouter Gemma 4 queries.

Tries models in a 3-model chain: Gemma 4 paid → Gemma 4 free → Meta Llama 3.3 free.
On specific error codes moves to the next model in the chain and returns is_fallback=True
so callers can signal this to the frontend via a model_info SSE event.
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
) -> tuple[Any, bool, str]:
    """Invoke an OpenRouter LLM with automatic 3-model fallback chain.

    Chain: model_id (or gemma_primary) → gemma_fallback → meta_fallback.

    Returns (response, is_fallback, used_model).
    is_fallback=True whenever the first model in the chain was not used.
    """
    chain = [
        model_id or settings.openrouter_gemma_primary,
        settings.openrouter_gemma_fallback,
        settings.openrouter_meta_fallback,
    ]
    # Deduplicate while preserving order (in case model_id equals one of the fallbacks)
    seen: set[str] = set()
    chain = [m for m in chain if not (m in seen or seen.add(m))]  # type: ignore[func-returns-value]

    last_exc: Exception | None = None
    for i, model in enumerate(chain):
        try:
            llm = create_llm(model, max_tokens, user_key, "openrouter")
            result = await llm.ainvoke(messages)
            return result, i > 0, model
        except Exception as exc:
            if _is_fallback_trigger(exc):
                logger.warning(
                    "OpenRouter model %s failed (%s) — trying next in chain",
                    model,
                    type(exc).__name__,
                )
                last_exc = exc
                continue
            raise

    # All models exhausted
    raise last_exc  # type: ignore[misc]
