import dspy

from app.config import settings

_DEPTH_TOKENS: dict[str, int] = {
    "quick": 4096,
    "standard": 6144,
    "comprehensive": 10240,
}


def get_dspy_lm(
    model_id: str,
    api_key: str,
    provider: str = "anthropic",
    depth: str = "standard",
) -> dspy.LM:
    prefix = "anthropic" if provider == "anthropic" else "openai"
    max_tokens = _DEPTH_TOKENS.get(depth, 6144)
    kwargs: dict[str, object] = {
        "api_key": api_key,
        "max_tokens": max_tokens,
    }
    if provider == "openrouter":
        kwargs["api_base"] = settings.openrouter_api_base
    return dspy.LM(f"{prefix}/{model_id}", **kwargs)
