import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.core.auth import generate_api_key, parse_api_key, verify_key_secret
from app.db.session import async_session
from app.models.user import User
from app.schemas.auth import RotateKeyRequest, RotateKeyResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/auth/rotate-key", response_model=RotateKeyResponse)
async def rotate_key(request: Request, body: RotateKeyRequest):
    parsed = parse_api_key(body.current_key)
    if not parsed:
        return JSONResponse(status_code=401, content={"detail": "Invalid key format"})

    key_id, secret = parsed

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.key_id == key_id)
        )
        user = result.scalar_one_or_none()

        if not user or not verify_key_secret(secret, user.key_hash):
            return JSONResponse(status_code=401, content={"detail": "Invalid API key"})

        new_full_key, new_key_id, new_key_hash = generate_api_key()
        user.key_id = new_key_id
        user.key_hash = new_key_hash
        await session.commit()

    return RotateKeyResponse(new_key=new_full_key)
