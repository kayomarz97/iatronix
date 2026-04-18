import logging
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from cryptography.fernet import Fernet
from sqlalchemy import select, delete
from app.db.session import async_session
from app.models.service_key import ServiceKey
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

def _fernet() -> Fernet:
    key = settings.encryption_key
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)

class ServiceKeyIn(BaseModel):
    service: str  # e.g. "ncbi", "europe_pmc", "openfda"
    api_key: str

class ServiceKeyOut(BaseModel):
    id: int
    service_name: str

@router.post("/service_keys", response_model=ServiceKeyOut, status_code=201)
async def upsert_service_key(body: ServiceKeyIn, request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    f = _fernet()
    encrypted = f.encrypt(body.api_key.encode()).decode()
    async with async_session() as session:
        # Upsert: delete existing for this service then insert
        await session.execute(
            delete(ServiceKey).where(
                ServiceKey.user_id == user.id,
                ServiceKey.service_name == body.service,
            )
        )
        sk = ServiceKey(user_id=user.id, service_name=body.service, encrypted_key=encrypted)
        session.add(sk)
        await session.commit()
        await session.refresh(sk)
    return ServiceKeyOut(id=sk.id, service_name=sk.service_name)

@router.get("/service_keys", response_model=list[ServiceKeyOut])
async def list_service_keys(request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    async with async_session() as session:
        result = await session.execute(
            select(ServiceKey).where(ServiceKey.user_id == user.id)
        )
        keys = result.scalars().all()
    return [ServiceKeyOut(id=k.id, service_name=k.service_name) for k in keys]

@router.delete("/service_keys/{service_name}", status_code=204)
async def delete_service_key(service_name: str, request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    async with async_session() as session:
        await session.execute(
            delete(ServiceKey).where(
                ServiceKey.user_id == user.id,
                ServiceKey.service_name == service_name,
            )
        )
        await session.commit()

async def get_service_key(user_id: int, service_name: str) -> Optional[str]:
    """Decrypt and return a service API key for a user. Returns None if not set."""
    async with async_session() as session:
        result = await session.execute(
            select(ServiceKey).where(
                ServiceKey.user_id == user_id,
                ServiceKey.service_name == service_name,
            )
        )
        sk = result.scalar_one_or_none()
    if not sk:
        return None
    f = _fernet()
    return f.decrypt(sk.encrypted_key.encode()).decode()
