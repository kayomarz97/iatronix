from fastapi import APIRouter

from app.services.provider_registry import get_registry

router = APIRouter()


@router.get("/models")
async def list_models():
    """All models across ENABLED providers (registry-backed).

    Replaces the static schemas.models.AVAILABLE_MODELS catalog so this endpoint
    can never advertise a model the backend cannot route/price.
    """
    reg = get_registry()
    models = []
    for pid, p in reg.enabled_providers().items():
        for m in p.get("models", []) or []:
            models.append(
                {
                    "id": m["id"],
                    "provider": pid,
                    "display": m.get("display"),
                    "input": m.get("input"),
                    "output": m.get("output"),
                    "context_window": m.get("context_window"),
                }
            )
    return {"models": models}
