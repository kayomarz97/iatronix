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


def create_llm(model_id: str):
    """Create an LLM instance for the given model ID."""
    provider = get_provider(model_id)

    if provider == "anthropic":
        return ChatAnthropic(
            model=model_id,
            api_key=settings.anthropic_api_key,
            max_tokens=settings.llm_max_tokens,
            timeout=settings.llm_timeout_seconds,
        )
    else:
        return ChatOpenAI(
            model=model_id,
            api_key=settings.openrouter_api_key,
            base_url="https://openrouter.ai/api/v1",
            max_tokens=settings.llm_max_tokens,
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
