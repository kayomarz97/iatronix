import logging

from fastapi import APIRouter, Request

from app.db.init_db import check_db_connection

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
async def health_check(request: Request):
    db_status = "connected" if await check_db_connection() else "disconnected"

    redis_status = "not_configured"
    redis_client = getattr(request.app.state, "redis", None)
    if redis_client:
        try:
            await redis_client.ping()
            redis_status = "connected"
        except Exception:
            redis_status = "degraded"

    status_code = 200 if db_status == "connected" else 503
    return {
        "status": "healthy" if status_code == 200 else "unhealthy",
        "db": db_status,
        "redis": redis_status,
    }
