from fastapi import APIRouter

from app.services.provider_registry import get_registry

router = APIRouter(prefix="/config", tags=["config"])


def _provider_entry(reg, provider: str) -> dict:
    dm = reg.default_model(provider)
    m = reg.model_meta(dm) or {}
    return {
        "model_id": dm,
        "display": m.get("display"),
        "input": m.get("input"),
        "output": m.get("output"),
    }


@router.get("/llm")
async def llm_config():
    """Default model per enabled provider (registry-backed).

    Kept for the current frontend; GET /api/v1/providers is the canonical
    replacement. Both derive from config/providers.yaml — one source of truth.
    """
    reg = get_registry()
    return {
        "default_provider": reg.default_provider,
        "providers": {p: _provider_entry(reg, p) for p in reg.enabled_providers()},
    }
