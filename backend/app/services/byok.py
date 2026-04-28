"""BYOK (Bring Your Own Key) — encrypt/decrypt user LLM API keys.

Uses Fernet symmetric encryption. Key stored in ENCRYPTION_KEY env var.
User keys are never logged or included in error responses.
"""

import logging
from typing import Optional

import httpx
from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

import re

logger = logging.getLogger(__name__)

_fernet: Optional[Fernet] = None

# Item 3: BYOK key format regex patterns
_KEY_PATTERNS = {
    "anthropic": re.compile(r"^.+$"),
    "openai": re.compile(r"^.+$"),
    "openrouter": re.compile(r"^.+$"),
    "cerebras": re.compile(r"^.+$"),
}


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key = settings.encryption_key
        if key == "CHANGE_ME":
            # Auto-generate for development; log warning
            key = Fernet.generate_key().decode()
            logger.warning(
                "ENCRYPTION_KEY not set — using auto-generated key. "
                "Set ENCRYPTION_KEY in .env for production."
            )
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def encrypt_key(plaintext_key: str) -> str:
    """Encrypt a user's LLM API key for storage."""
    f = _get_fernet()
    return f.encrypt(plaintext_key.encode()).decode()


def decrypt_key(encrypted_key: str) -> Optional[str]:
    """Decrypt a user's stored LLM API key."""
    try:
        f = _get_fernet()
        return f.decrypt(encrypted_key.encode()).decode()
    except InvalidToken:
        logger.error("Failed to decrypt user LLM key — invalid token")
        return None


def validate_key_format(key: str, provider: str) -> bool:
    """Synchronous version of key format validation."""
    key = key.strip()
    if not key:
        return False

    if provider not in _KEY_PATTERNS:
        return False

    return True


async def validate_user_key(key: str, provider: str) -> dict:
    """Validate a user's LLM API key by making a real API call.

    Returns a dict with 'valid' (bool), 'error' (str or None), and 'detail' (str or None).
    """
    # First check format
    if not validate_key_format(key, provider):
        return {
            "valid": False,
            "error": "invalid_format",
            "detail": f"Invalid API key format for {provider}. Please check your key.",
        }

    # Live validation via actual API call
    try:
        if provider == "anthropic":
            return await _validate_anthropic_key(key)
        elif provider in ("openai", "openrouter", "cerebras"):
            return await _validate_openai_key(key, provider)
        else:
            return {
                "valid": False,
                "error": "unsupported_provider",
                "detail": f"Provider '{provider}' is not supported.",
            }
    except Exception as e:
        logger.error(f"Key validation error for {provider}", exc_info=True)
        return {
            "valid": False,
            "error": "validation_error",
            "detail": f"Could not validate key: {str(e)}",
        }


async def _validate_anthropic_key(key: str) -> dict:
    """Test Anthropic key by making a minimal API call."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": ""}],
                },
            )
            if response.status_code == 401:
                return {
                    "valid": False,
                    "error": "unauthorized",
                    "detail": "Anthropic API key is invalid or has insufficient permissions.",
                }
            elif response.status_code == 403:
                return {
                    "valid": False,
                    "error": "forbidden",
                    "detail": "Anthropic API key is forbidden or revoked.",
                }
            elif response.status_code in (200, 400, 422):
                # 200 = success, 400/422 = bad request (but auth passed)
                return {
                    "valid": True,
                    "error": None,
                    "detail": "Anthropic API key is valid.",
                }
            else:
                return {
                    "valid": False,
                    "error": "api_error",
                    "detail": f"Unexpected Anthropic API response: {response.status_code}.",
                }
    except httpx.ConnectError:
        return {
            "valid": False,
            "error": "network_error",
            "detail": "Could not reach Anthropic API. Check your internet connection.",
        }
    except httpx.TimeoutException:
        return {
            "valid": False,
            "error": "timeout",
            "detail": "Anthropic API validation timed out. Try again later.",
        }


async def _validate_openai_key(key: str, provider: str) -> dict:
    """Test OpenAI or OpenRouter key by making a minimal API call."""
    try:
        if provider == "openrouter":
            base_url = "https://openrouter.ai/api/v1"
        elif provider == "cerebras":
            base_url = "https://api.cerebras.ai/v1"
        else:
            base_url = "https://api.openai.com/v1"

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{base_url}/models",
                headers={"Authorization": f"Bearer {key}"},
            )
            if response.status_code == 401:
                return {
                    "valid": False,
                    "error": "unauthorized",
                    "detail": f"{provider.title()} API key is invalid or has insufficient permissions.",
                }
            elif response.status_code == 403:
                return {
                    "valid": False,
                    "error": "forbidden",
                    "detail": f"{provider.title()} API key is forbidden or revoked.",
                }
            elif response.status_code == 200:
                return {
                    "valid": True,
                    "error": None,
                    "detail": f"{provider.title()} API key is valid.",
                }
            else:
                return {
                    "valid": False,
                    "error": "api_error",
                    "detail": f"Unexpected {provider.title()} API response: {response.status_code}.",
                }
    except httpx.ConnectError:
        return {
            "valid": False,
            "error": "network_error",
            "detail": f"Could not reach {provider.title()} API. Check your internet connection.",
        }
    except httpx.TimeoutException:
        return {
            "valid": False,
            "error": "timeout",
            "detail": f"{provider.title()} API validation timed out. Try again later.",
        }
