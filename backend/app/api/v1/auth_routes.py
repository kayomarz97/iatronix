"""User authentication and BYOK key management endpoints."""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session as get_async_session
from app.models.user import User, UserRole
from app.schemas.auth import (
    UpdateProfileRequest,
    UpdatePreferencesRequest,
    UserProfileResponse,
    LlmKeyRequest,
)
from app.middleware.firebase_auth import invalidate_user_cache
from app.services.byok import encrypt_key, validate_user_key

router = APIRouter(prefix="/auth", tags=["auth"])


class LLMKeyResponse(BaseModel):
    provider: str
    is_set: bool
    message: str = "Success"


def _get_authenticated_user(request: Request) -> User:
    """Extract authenticated user from request state (set by FirebaseAuthMiddleware)."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(401, "Authentication required")
    return user


@router.get("/me", response_model=UserProfileResponse)
async def get_me(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    """Return the current user's full profile."""
    user = _get_authenticated_user(request)
    result = await session.execute(select(User).where(User.id == user.id))
    db_user = result.scalar_one()
    return UserProfileResponse(
        id=db_user.id,
        email=db_user.email,
        username=db_user.username,
        full_name=db_user.full_name,
        country=db_user.country,
        position=db_user.position,
        institute=db_user.institute,
        specialty=db_user.specialty,
        institution_type=db_user.institution_type,
        age=db_user.age,
        gender=db_user.gender,
        role=db_user.role.value
        if hasattr(db_user.role, "value")
        else str(db_user.role),
        tier=db_user.tier or "free",
        llm_provider=db_user.llm_provider,
        has_llm_key=bool(db_user.encrypted_llm_key),
        preferences=db_user.preferences or {},
        newsletter_consent=db_user.newsletter_consent or False,
        last_login=db_user.last_login.isoformat() if db_user.last_login else None,
        created_at=db_user.created_at.isoformat() if db_user.created_at else None,
    )


@router.put("/profile", response_model=UserProfileResponse)
async def update_profile(
    req: UpdateProfileRequest,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    """Update user profile fields."""
    user = _get_authenticated_user(request)
    result = await session.execute(select(User).where(User.id == user.id))
    db_user = result.scalar_one()

    if req.username is not None:
        # Check uniqueness if changing username
        if req.username != db_user.username:
            existing = await session.execute(
                select(User).where(User.username == req.username)
            )
            if existing.scalar_one_or_none():
                raise HTTPException(409, "Username already taken")
        db_user.username = req.username
    if req.full_name is not None:
        db_user.full_name = req.full_name
    if req.country is not None:
        db_user.country = req.country
    if req.position is not None:
        db_user.position = req.position
    if req.institute is not None:
        db_user.institute = req.institute
    if req.specialty is not None:
        db_user.specialty = req.specialty
    if req.institution_type is not None:
        db_user.institution_type = req.institution_type
    if req.age is not None:
        db_user.age = req.age
    if req.gender is not None:
        db_user.gender = req.gender
    if req.newsletter_consent is not None:
        db_user.newsletter_consent = req.newsletter_consent

    await session.commit()
    await session.refresh(db_user)

    return UserProfileResponse(
        id=db_user.id,
        email=db_user.email,
        username=db_user.username,
        full_name=db_user.full_name,
        country=db_user.country,
        position=db_user.position,
        institute=db_user.institute,
        specialty=db_user.specialty,
        institution_type=db_user.institution_type,
        age=db_user.age,
        gender=db_user.gender,
        role=db_user.role.value
        if hasattr(db_user.role, "value")
        else str(db_user.role),
        tier=db_user.tier or "free",
        llm_provider=db_user.llm_provider,
        has_llm_key=bool(db_user.encrypted_llm_key),
        preferences=db_user.preferences or {},
        newsletter_consent=db_user.newsletter_consent or False,
        last_login=db_user.last_login.isoformat() if db_user.last_login else None,
        created_at=db_user.created_at.isoformat() if db_user.created_at else None,
    )


@router.post("/settings")
async def update_preferences(
    req: UpdatePreferencesRequest,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    """Merge user preferences (arbitrary JSON). Existing keys not in the request are preserved."""
    user = _get_authenticated_user(request)
    result = await session.execute(select(User).where(User.id == user.id))
    db_user = result.scalar_one()

    current = dict(db_user.preferences or {})
    current.update(req.preferences)
    db_user.preferences = current
    await session.commit()
    return {"preferences": current, "message": "Preferences updated"}


@router.put("/llm-key", response_model=LLMKeyResponse)
async def set_llm_key(
    req: LlmKeyRequest,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    """Store user's own LLM API key (encrypted)."""
    user = _get_authenticated_user(request)

    if req.provider not in ("anthropic", "openai", "openrouter"):
        raise HTTPException(
            400, "Provider must be 'anthropic', 'openai', or 'openrouter'"
        )

    validation_result = await validate_user_key(req.key, req.provider)
    if not validation_result["valid"]:
        error_detail = validation_result.get("detail", "Invalid API key")
        raise HTTPException(422, error_detail)

    encrypted = encrypt_key(req.key)

    result = await session.execute(select(User).where(User.id == user.id))
    db_user = result.scalar_one()
    db_user.encrypted_llm_key = encrypted
    db_user.llm_provider = req.provider
    await session.commit()
    invalidate_user_cache(user.firebase_uid)

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
    invalidate_user_cache(user.firebase_uid)

    return LLMKeyResponse(provider="none", is_set=False, message="Key removed")


@router.get("/llm-key", response_model=LLMKeyResponse)
async def get_llm_key_status(request: Request):
    """Check if user has an LLM key set."""
    user = _get_authenticated_user(request)
    return LLMKeyResponse(
        provider=user.llm_provider or "none",
        is_set=bool(user.encrypted_llm_key),
    )


@router.delete("/account")
async def delete_account(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    """Delete user account and all associated data (documents, search history, query logs)."""
    user = _get_authenticated_user(request)
    result = await session.execute(select(User).where(User.id == user.id))
    db_user = result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(404, "User not found")

    # Also clean up R2 files for user's documents
    from app.models.document import Document
    from app.services import r2_storage

    doc_result = await session.execute(
        select(Document).where(Document.uploaded_by_user_id == user.id)
    )
    docs = doc_result.scalars().all()
    for doc in docs:
        if doc.r2_key:
            try:
                await r2_storage.delete_pdf(doc.r2_key)
            except Exception:
                pass

    await session.delete(db_user)
    await session.commit()
    return {"deleted": True, "message": "Account and all associated data deleted"}
