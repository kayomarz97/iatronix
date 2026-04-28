"""Model metadata + pricing registry. Add new models here only — no other file changes needed."""
from app.config import settings

# All prices in USD per 1,000,000 tokens.
_REGISTRY: dict[str, dict] = {
    # Anthropic
    "claude-haiku-4-5-20251001":  {"provider": "anthropic", "display": "Claude Haiku 4.5",   "input": 0.80, "output": 4.00,  "cache_write": 1.00, "cache_read": 0.08},
    "claude-sonnet-4-6":          {"provider": "anthropic", "display": "Claude Sonnet 4.6",  "input": 3.00, "output": 15.00, "cache_write": 3.75, "cache_read": 0.30},
    "claude-sonnet-4-20250514":   {"provider": "anthropic", "display": "Claude Sonnet 4",    "input": 3.00, "output": 15.00, "cache_write": 3.75, "cache_read": 0.30},
    # Cerebras (paid tier) — verified rates per Cerebras pricing page
    "llama3.1-8b":                {"provider": "cerebras",  "display": "Llama 3.1 8B (Cerebras)",   "input": 0.10, "output": 0.10, "speed_tps": 2200},
    "llama-3.3-70b":              {"provider": "cerebras",  "display": "Llama 3.3 70B (Cerebras)",  "input": 0.85, "output": 1.20, "speed_tps": 2100},
    "gpt-oss-120b":               {"provider": "cerebras",  "display": "GPT-OSS 120B (Cerebras)",   "input": 0.35, "output": 0.75, "speed_tps": 3000},
    "qwen-3-235b-a22b-instruct-2507": {"provider": "cerebras", "display": "Qwen3 235B (Cerebras)", "input": 0.60, "output": 1.20, "speed_tps": 1800},
}


def lookup(model_id: str) -> dict:
    """Return registry entry, falling back to sensible defaults for unknown models."""
    if model_id in _REGISTRY:
        return _REGISTRY[model_id]
    if "/" in model_id:  # OpenRouter — opaque pass-through
        return {"provider": "openrouter", "display": model_id, "input": 0.0, "output": 0.0}
    return _REGISTRY.get(settings.cerebras_default_model, {
        "provider": "unknown", "display": model_id, "input": 0.0, "output": 0.0,
    })


def display_name(model_id: str) -> str:
    return lookup(model_id)["display"]


def pricing(model_id: str) -> tuple[float, float]:
    e = lookup(model_id)
    return e["input"], e["output"]
