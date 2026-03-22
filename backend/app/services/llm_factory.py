import logging
from typing import Optional

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from app.config import settings

logger = logging.getLogger(__name__)


def get_provider(model_id: str) -> str:
    """Determine provider from model ID."""
    if "/" in model_id:
        return "openrouter"
    return "anthropic"


def create_llm(
    model_id: str,
    max_tokens: int | None = None,
    user_key: Optional[str] = None,
    user_provider: Optional[str] = None,
):
    """Create an LLM instance for the given model ID.

    If user_key + user_provider are provided (BYOK), use the user's key.
    Falls back to server keys if no user key is given.
    """
    provider = get_provider(model_id)
    effective_max_tokens = (
        max_tokens if max_tokens is not None else settings.llm_max_tokens
    )

    # BYOK: if user has their own key, use it
    if user_key and user_provider:
        if user_provider == "anthropic":
            return ChatAnthropic(
                model=model_id
                if provider == "anthropic"
                else "claude-sonnet-4-20250514",
                api_key=user_key,
                max_tokens=effective_max_tokens,
                timeout=settings.llm_timeout_seconds,
                max_retries=0,
            )
        elif user_provider == "openai":
            return ChatOpenAI(
                model=model_id if provider == "openrouter" else "gpt-4o",
                api_key=user_key,
                max_tokens=effective_max_tokens,
                timeout=settings.llm_timeout_seconds,
            )

    if provider == "anthropic":
        return ChatAnthropic(
            model=model_id,
            api_key=settings.anthropic_api_key,
            max_tokens=effective_max_tokens,
            timeout=settings.llm_timeout_seconds,
            max_retries=0,  # pipeline handles retries; SDK retries cause 90s hangs on rate limits
        )
    else:
        return ChatOpenAI(
            model=model_id,
            api_key=settings.openrouter_api_key,
            base_url="https://openrouter.ai/api/v1",
            max_tokens=effective_max_tokens,
            timeout=settings.llm_timeout_seconds,
            default_headers={
                "HTTP-Referer": "https://iatronix.local",
                "X-Title": "Iatronix Medical RAG",
            },
            model_kwargs={"response_format": {"type": "json_object"}},
        )


def get_alternative_model(model_id: str) -> str | None:
    """Get a fallback model from the other provider."""
    provider = get_provider(model_id)
    if provider == "anthropic":
        return "anthropic/claude-sonnet-4-20250514"
    return "claude-sonnet-4-20250514"
