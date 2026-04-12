from pydantic import BaseModel


class ModelInfo(BaseModel):
    id: str
    name: str
    provider: str
    description: str


AVAILABLE_MODELS = [
    ModelInfo(
        id="claude-haiku-4-5-20251001",
        name="Claude Haiku 4.5",
        provider="anthropic",
        description="Fast and efficient for drug lookups",
    ),
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
        id="google/gemini-flash-1.5",
        name="Gemini 1.5 Flash",
        provider="openrouter",
        description="OpenRouter model for low-cost adaptive responses",
    ),
    ModelInfo(
        id="google/gemini-flash-1.5-8b",
        name="Gemini 1.5 Flash 8B",
        provider="openrouter",
        description="Smaller OpenRouter Gemini 1.5 model",
    ),
]
