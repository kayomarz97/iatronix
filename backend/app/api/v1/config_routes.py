from fastapi import APIRouter
from app.config import settings
from app.services.model_registry import lookup

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/llm")
async def llm_config():
    """Return the current default model per provider. Frontend reads this on page load
    so display name, cost, and provider all stay in sync with backend env vars."""
    cb = lookup(settings.cerebras_default_model)
    an = lookup(settings.model_haiku)
    return {
        "default_provider": "cerebras",
        "providers": {
            "cerebras":  {"model_id": settings.cerebras_default_model, **cb},
            "anthropic": {"model_id": settings.model_haiku,            **an},
        },
    }
