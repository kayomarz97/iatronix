"""KeyStore abstraction — storage-agnostic BYOK key access.

The pipeline and auth routes call ``keystore.get(user, provider)`` /
``keystore.set(...)`` instead of touching ``users.<provider>_api_key`` columns
directly. Backends (Postgres, Firestore) live behind this so neither datastore
is hardcoded and migration between them is a config flag, not a code change.

Provider -> column / provider set come from the registry (config/providers.yaml),
so adding a provider needs no edits here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from app.services.byok import decrypt_key, encrypt_key
from app.services.provider_registry import get_registry


class KeyStore(ABC):
    """Stores Fernet-encrypted BYOK keys. Subclasses implement the raw read/write."""

    # -- raw (encrypted) ops implemented by backends -------------------------
    @abstractmethod
    def get_encrypted(self, user: Any, provider: str) -> Optional[str]:
        ...

    @abstractmethod
    async def set_encrypted(self, user: Any, provider: str, encrypted: str, session: Any) -> None:
        ...

    @abstractmethod
    async def clear(self, user: Any, provider: str, session: Any) -> None:
        ...

    # -- convenience (decrypt/encrypt + status) ------------------------------
    def get(self, user: Any, provider: str) -> Optional[str]:
        """Decrypted key for ``provider`` (or None)."""
        enc = self.get_encrypted(user, provider)
        return decrypt_key(enc) if enc else None

    async def set(self, user: Any, provider: str, plaintext: str, session: Any) -> None:
        await self.set_encrypted(user, provider, encrypt_key(plaintext), session)

    def status(self, user: Any) -> dict[str, bool]:
        """{provider: is_set} for every provider that has a key column in the registry."""
        reg = get_registry()
        return {
            p: bool(self.get_encrypted(user, p))
            for p in reg.allowed_providers()
            if reg.key_column(p)
        }
