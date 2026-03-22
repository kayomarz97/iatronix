"""User authentication and BYOK key management endpoints."""

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import generate_api_key
from app.db.session import get_session as get_async_session
from app.models.user import User, UserRole
from app.services.byok import encrypt_key, validate_user_key

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    api_key: str
    email: str
    message: str = "Success"


class LLMKeyRequest(BaseModel):
    key: str
    provider: str  # 'anthropic' or 'openai'


class LLMKeyResponse(BaseModel):
    provider: str
    is_set: bool
    message: str = "Success"


def _get_authenticated_user(request: Request) -> User:
    """Extract authenticated user from request state (set by ApiKeyAuthMiddleware)."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(401, "Authentication required")
    return user


@router.post("/register", response_model=AuthResponse)
async def register(
    req: RegisterRequest,
    session: AsyncSession = Depends(get_async_session),
):
    """Register a new user account."""
    existing = await session.execute(select(User).where(User.email == req.email))
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Email already registered")

    password_hash = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()
    full_key, key_id, key_hash = generate_api_key()

    user = User(
        key_id=key_id,
        key_hash=key_hash,
        email=req.email,
        password_hash=password_hash,
        role=UserRole.user,
        scopes={},
    )
    session.add(user)
    await session.commit()

    return AuthResponse(api_key=full_key, email=req.email, message="Account created")


@router.post("/login", response_model=AuthResponse)
async def login(
    req: LoginRequest,
    session: AsyncSession = Depends(get_async_session),
):
    """Login with email and password. Returns API key."""
    result = await session.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    if not user or not user.password_hash:
        raise HTTPException(401, "Invalid email or password")

    if not bcrypt.checkpw(req.password.encode(), user.password_hash.encode()):
        raise HTTPException(401, "Invalid email or password")

    # Regenerate API key on login
    full_key, key_id, key_hash = generate_api_key()
    user.key_id = key_id
    user.key_hash = key_hash
    await session.commit()

    return AuthResponse(api_key=full_key, email=req.email)


@router.put("/llm-key", response_model=LLMKeyResponse)
async def set_llm_key(
    req: LLMKeyRequest,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    """Store user's own LLM API key (encrypted)."""
    user = _get_authenticated_user(request)

    if req.provider not in ("anthropic", "openai"):
        raise HTTPException(400, "Provider must be 'anthropic' or 'openai'")

    is_valid = await validate_user_key(req.key, req.provider)
    if not is_valid:
        raise HTTPException(400, f"Invalid {req.provider} API key")

    # Encrypt and store
    encrypted = encrypt_key(req.key)

    # Re-fetch user in this session for update
    result = await session.execute(select(User).where(User.id == user.id))
    db_user = result.scalar_one()
    db_user.encrypted_llm_key = encrypted
    db_user.llm_provider = req.provider
    await session.commit()

    return LLMKeyResponse(provider=req.provider, is_set=True)


@router.delete("/llm-key", response_model=LLMKeyResponse)
async def delete_llm_key(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    """Remove user's stored LLM API key."""
    user = _get_authenticated_user(request)

    result = await session.execute(select(User).where(User.id == user.id))
    db_user = result.scalar_one()
    db_user.encrypted_llm_key = None
    db_user.llm_provider = None
    await session.commit()

    return LLMKeyResponse(provider="none", is_set=False, message="Key removed")


@router.get("/llm-key", response_model=LLMKeyResponse)
async def get_llm_key_status(request: Request):
    """Check if user has an LLM key set."""
    user = _get_authenticated_user(request)
    return LLMKeyResponse(
        provider=user.llm_provider or "none",
        is_set=bool(user.encrypted_llm_key),
    )
