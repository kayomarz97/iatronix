"""OpenRouter OAuth PKCE flow.

Routes:
  GET  /auth/openrouter/login     — initiate PKCE; redirect to OpenRouter
  GET  /auth/openrouter/callback  — receive code; exchange for key; save encrypted
  DELETE /auth/openrouter/key     — disconnect (authenticated)
  GET  /auth/openrouter/status    — check connection status (authenticated)
"""

import base64
import hashlib
import json
import logging
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_session as get_async_session
from app.middleware.firebase_auth import invalidate_user_cache
from app.models.user import User
from app.services.byok import decrypt_key, encrypt_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/openrouter", tags=["openrouter-oauth"])

_PKCE_TTL = 600  # seconds


def _code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _get_authenticated_user(request: Request) -> User:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(401, "Authentication required")
    return user


@router.get("/login")
async def openrouter_login(request: Request):
    """Start PKCE flow — redirect to OpenRouter auth page."""
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(503, "Redis unavailable — cannot initiate OAuth flow")

    code_verifier = secrets.token_urlsafe(32)
    state = secrets.token_urlsafe(32)
    code_challenge = _code_challenge(code_verifier)

    await redis.setex(f"pkce:{state}", _PKCE_TTL, code_verifier)

    callback_base = settings.openrouter_callback_base.rstrip("/")
    callback_url = f"{callback_base}/api/v1/auth/openrouter/callback?state={state}"

    params = urlencode({
        "callback_url": callback_url,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    })
    redirect_to = f"{settings.openrouter_oauth_url}?{params}"
    return RedirectResponse(url=redirect_to, status_code=302)


@router.get("/callback")
async def openrouter_callback(
    request: Request,
    state: str = "",
    code: str = "",
    session: AsyncSession = Depends(get_async_session),
):
    """OpenRouter redirects here after user authorizes.

    Validates state, exchanges code for key, encrypts and saves it.
    """
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(503, "Redis unavailable")

    # Validate state (CSRF check)
    if not state or not code:
        raise HTTPException(400, "Missing state or code parameters")

    code_verifier = await redis.get(f"pkce:{state}")
    if not code_verifier:
        raise HTTPException(400, "Invalid or expired state parameter")

    await redis.delete(f"pkce:{state}")

    # Exchange code for OpenRouter key
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                settings.openrouter_token_url,
                json={
                    "code": code,
                    "code_verifier": code_verifier,
                    "code_challenge_method": "S256",
                },
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        logger.error("OpenRouter token exchange failed: %s", exc.response.status_code)
        raise HTTPException(502, "OpenRouter token exchange failed") from exc
    except Exception as exc:
        logger.error("OpenRouter token exchange error: %s", type(exc).__name__)
        raise HTTPException(502, "OpenRouter token exchange failed") from exc

    raw_key = data.get("key")
    if not raw_key:
        raise HTTPException(502, "OpenRouter did not return a key")

    # The callback is unauthenticated (browser redirect), so we must identify
    # the user by firebase_uid embedded in the state payload.
    # Since we only store code_verifier in Redis (not uid), we rely on the
    # user being logged in via cookie / Firebase auth middleware.
    user = getattr(request.state, "user", None)
    if user is None:
        # Cannot save key without knowing who the user is — redirect to login
        return RedirectResponse(
            url="/settings?openrouter=auth_required", status_code=302
        )

    encrypted = encrypt_key(raw_key)

    result = await session.execute(select(User).where(User.id == user.id))
    db_user = result.scalar_one()
    db_user.openrouter_key = encrypted
    await session.commit()
    invalidate_user_cache(user.firebase_uid)

    callback_base = settings.openrouter_callback_base.rstrip("/")
    return RedirectResponse(
        url=f"{callback_base}/settings?openrouter=connected", status_code=302
    )


@router.delete("/key")
async def disconnect_openrouter(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    """Remove stored OpenRouter key."""
    user = _get_authenticated_user(request)
    result = await session.execute(select(User).where(User.id == user.id))
    db_user = result.scalar_one()
    db_user.openrouter_key = None
    await session.commit()
    invalidate_user_cache(user.firebase_uid)
    return {"disconnected": True}


@router.get("/status")
async def openrouter_status(request: Request):
    """Check if user has an OpenRouter key stored."""
    user = _get_authenticated_user(request)
    return {"connected": bool(getattr(user, "openrouter_key", None))}
