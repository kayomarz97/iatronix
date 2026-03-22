import logging

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from app.config import settings

logger = logging.getLogger(__name__)


def get_provider(model_id: str) -> str:
    """Determine provider from model ID."""
    if "/" in model_id:
        return "openrouter"
    return "anthropic"


def create_llm(model_id: str, max_tokens: int | None = None):
    """Create an LLM instance for the given model ID."""
    provider = get_provider(model_id)
    effective_max_tokens = (
        max_tokens if max_tokens is not None else settings.llm_max_tokens
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
