import logging
from typing import Optional

from fastapi import HTTPException, status
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from app.config import settings

logger = logging.getLogger(__name__)


def get_provider(model_id: str) -> str:
    """Determine provider from model ID."""
    if "/" in model_id:
        return "openai"
    return "anthropic"


def create_llm(
    model_id: str,
    max_tokens: int | None = None,
    user_key: Optional[str] = None,
    user_provider: Optional[str] = None,
):
    """Create LLM using the user's own API key (BYOK only).

    Raises HTTP 402 if user has no key configured.
    This ensures zero server-side LLM cost.
    """
    if not user_key or not user_provider:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "no_api_key",
                "message": "No API key configured. Please add your Anthropic or OpenAI API key in Settings.",
                "settings_url": "/settings",
            },
        )

    effective_max_tokens = max_tokens if max_tokens is not None else settings.llm_max_tokens

    if user_provider == "anthropic":
        return ChatAnthropic(
            model=model_id if "/" not in model_id else settings.model_sonnet,
            api_key=user_key,
            max_tokens=effective_max_tokens,
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
        )
    elif user_provider == "openai":
        return ChatOpenAI(
            model=model_id if "/" not in model_id else "gpt-4o",
            api_key=user_key,
            max_tokens=effective_max_tokens,
            timeout=settings.llm_timeout_seconds,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "unsupported_provider",
                "message": f"Provider '{user_provider}' is not supported. Use 'anthropic' or 'openai'.",
            },
        )


def get_alternative_model(model_id: str) -> str | None:
    """No alternative provider in BYOK-only mode."""
    return None
