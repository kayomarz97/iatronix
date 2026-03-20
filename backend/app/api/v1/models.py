from fastapi import APIRouter

from app.schemas.models import AVAILABLE_MODELS

router = APIRouter()


@router.get("/models")
async def list_models():
    return {"models": [m.model_dump() for m in AVAILABLE_MODELS]}
