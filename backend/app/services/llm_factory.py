import logging
from typing import Optional

from fastapi import HTTPException, status
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from app.config import settings

logger = logging.getLogger(__name__)


def handle_llm_api_error(e: Exception, model_id: str, provider: str) -> None:
    """Convert LLM provider errors to user-friendly HTTP exceptions.

    Raises HTTPException on known errors; re-raises on unknown.
    """
    error_msg = str(e).lower()

    if provider == "anthropic":
        # Check for NotFoundError or 404 in error message
        if "notfound" in error_msg or "404" in error_msg or "model" in error_msg and "does not exist" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "model_not_found",
                    "message": f"Model '{model_id}' not found on Anthropic. Check your API plan or update the model name via MODEL_HAIKU / MODEL_SONNET environment variables.",
                    "settings_url": "/settings",
                },
            ) from e
        elif "authentication" in error_msg or "401" in error_msg or "invalid api key" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": "auth_failed",
                    "message": "Anthropic API key is invalid or expired. Check Settings → LLM API Key.",
                    "settings_url": "/settings",
                },
            ) from e
    # Re-raise unknown errors as 500
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={
            "error": "llm_error",
            "message": f"{provider} API error: {error_msg[:100]}",
        },
    ) from e


def get_provider(model_id: str) -> str:
    """Determine provider from model ID."""
    if "/" in model_id:
        return "openrouter"
    if model_id.startswith("gemini") or model_id.startswith("models/gemini"):
        return "gemini"
    # Cerebras models must be checked before OpenAI (gpt-oss-* is Cerebras-exclusive)
    if (
        model_id.startswith("gpt-oss")
        or model_id.startswith("llama")
        or model_id.startswith("qwen")
        or model_id.startswith("mistral")
    ):
        return "cerebras"
    if model_id.startswith("gpt-") or model_id.startswith("o1") or model_id.startswith("o3"):
        return "openai"
    return "anthropic"


def create_llm(
    model_id: str,
    max_tokens: int | None = None,
    user_key: Optional[str] = None,
    user_provider: Optional[str] = None,
):
    """Create LLM client.

    Uses only the user's own BYOK key.
    """
    effective_max_tokens = (
        max_tokens if max_tokens is not None else settings.llm_max_tokens
    )

    provider = user_provider or get_provider(model_id)
    api_key = user_key

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "no_api_key",
                "message": "No API key configured. Please add your Cerebras, Anthropic, OpenAI, or OpenRouter API key in Settings → LLM API Key.",
                "settings_url": "/settings",
            },
        )

    if provider == "anthropic":
        return ChatAnthropic(
            model=model_id if "/" not in model_id else settings.model_sonnet,
            api_key=api_key,
            max_tokens=effective_max_tokens,
            timeout=settings.llm_timeout_seconds,
            max_retries=2,  # LangChain handles exponential backoff; reduces transient 429/overload errors
        )
    elif provider == "gemini":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "gemini_unavailable",
                    "message": "Gemini support requires langchain-google-genai. Contact support.",
                },
            ) from exc
        return ChatGoogleGenerativeAI(
            model=model_id,
            google_api_key=api_key,
            max_output_tokens=effective_max_tokens,
            timeout=settings.llm_timeout_seconds,
        )
    elif provider == "openai":
        return ChatOpenAI(
            model=model_id if "/" not in model_id else settings.openai_default_model,
            api_key=api_key,
            max_tokens=effective_max_tokens,
            timeout=settings.llm_timeout_seconds,
            max_retries=1,
        )
    elif provider == "openrouter":
        return ChatOpenAI(
            model=model_id if "/" in model_id else settings.openrouter_default_model,
            api_key=api_key,
            base_url=settings.openrouter_api_base,
            max_tokens=effective_max_tokens,
            timeout=settings.llm_timeout_seconds,
        )
    elif provider == "cerebras":
        effective_model = model_id if model_id else settings.cerebras_default_model
        return ChatOpenAI(
            model=effective_model,
            api_key=api_key,
            base_url=settings.cerebras_api_base,
            max_tokens=effective_max_tokens,         # paid tier: no artificial cap needed
            timeout=settings.llm_timeout_seconds,
            max_retries=1,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "unsupported_provider",
                "message": f"Provider '{provider}' is not supported. Use 'anthropic', 'openai', 'cerebras', or 'openrouter'.",
            },
        )


def get_alternative_model(model_id: str) -> str | None:
    """No alternative provider in BYOK-only mode."""
    return None
