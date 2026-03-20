from pydantic import BaseModel


class ModelInfo(BaseModel):
    id: str
    name: str
    provider: str
    description: str


AVAILABLE_MODELS = [
    ModelInfo(
        id="claude-sonnet-4-20250514",
        name="Claude Sonnet 4",
        provider="anthropic",
        description="Balanced performance and speed",
    ),
    ModelInfo(
        id="claude-opus-4-20250514",
        name="Claude Opus 4",
        provider="anthropic",
        description="Most capable, slower responses",
    ),
    ModelInfo(
        id="anthropic/claude-sonnet-4-20250514",
        name="Claude Sonnet 4 (OpenRouter)",
        provider="openrouter",
        description="Claude Sonnet 4 via OpenRouter",
    ),
    ModelInfo(
        id="google/gemini-2.5-pro-preview",
        name="Gemini 2.5 Pro (OpenRouter)",
        provider="openrouter",
        description="Google Gemini 2.5 Pro via OpenRouter",
    ),
]
