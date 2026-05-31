"""GET /api/v1/providers — canonical, registry-backed provider/model list.

Returns only ENABLED providers and their models, with no secrets (no key
columns, base URLs, validation probes, etc.). The frontend renders its key-entry
UI and model picker entirely from this response, so enabling a provider in
config/providers.yaml activates it on the frontend with no code change.
"""

from fastapi import APIRouter

from app.services.provider_registry import get_registry

router = APIRouter()


@router.get("/providers")
async def list_providers():
    return get_registry().public_view()
