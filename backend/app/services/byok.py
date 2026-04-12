"""BYOK (Bring Your Own Key) — encrypt/decrypt user LLM API keys.

Uses Fernet symmetric encryption. Key stored in ENCRYPTION_KEY env var.
User keys are never logged or included in error responses.
"""

import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

logger = logging.getLogger(__name__)

_fernet: Optional[Fernet] = None


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


async def validate_user_key(key: str, provider: str) -> bool:
    """Validate a user's LLM API key by format.

    Only checks the key format — actual validity is confirmed on first use.
    Remote validation via /v1/models can reject keys with restricted permissions.
    """
    key = key.strip()
    if not key:
        return False

    if provider == "anthropic":
        return key.startswith("sk-ant-")

    if provider == "openai":
        return key.startswith("sk-")

    if provider == "openrouter":
        return key.startswith("sk-or-v1-")

    return False
