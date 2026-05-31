import dspy

from app.services.provider_registry import get_registry

_DEPTH_TOKENS: dict[str, int] = {
    "quick": 4096,
    "standard": 6144,
    "comprehensive": 10240,
}

# litellm provider prefix by registry client_kind
_LITELLM_PREFIX = {"anthropic": "anthropic", "google_genai": "gemini", "openai_compatible": "openai"}


def get_dspy_lm(
    model_id: str,
    api_key: str,
    provider: str = "anthropic",
    depth: str = "standard",
) -> dspy.LM:
    meta = get_registry().provider_meta(provider) or {}
    client_kind = meta.get("client_kind", "openai_compatible")
    prefix = _LITELLM_PREFIX.get(client_kind, "openai")
    max_tokens = _DEPTH_TOKENS.get(depth, 6144)
    kwargs: dict[str, object] = {
        "api_key": api_key,
        "max_tokens": max_tokens,
    }
    # OpenAI-compatible providers (Cerebras/OpenRouter/xAI/OpenAI) need their base_url
    base_url = meta.get("base_url")
    if client_kind == "openai_compatible" and base_url:
        kwargs["api_base"] = base_url
    return dspy.LM(f"{prefix}/{model_id}", **kwargs)
