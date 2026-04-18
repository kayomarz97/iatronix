from fastapi import APIRouter, Request
from app.config import settings

router = APIRouter()

@router.get("/version")
async def version(request: Request):
    frontend_version = "2.1"
    return {"backend": settings.backend_version, "frontend": frontend_version}
