"""Postgres KeyStore backend — wraps the per-provider ``users.*_api_key`` columns.

Reads are plain attribute access on an already-loaded ``User`` ORM object (hot
path, no extra DB round-trip). The provider->column mapping comes from the
registry, so this never hardcodes a provider name.
"""

from __future__ import annotations

from typing import Any, Optional

from app.services.keystore.base import KeyStore
from app.services.provider_registry import get_registry


class PostgresKeyStore(KeyStore):
    def get_encrypted(self, user: Any, provider: str) -> Optional[str]:
        col = get_registry().key_column(provider)
        if not col:
            return None
        return getattr(user, col, None)

    async def set_encrypted(self, user: Any, provider: str, encrypted: str, session: Any) -> None:
        col = get_registry().key_column(provider)
        if not col:
            raise ValueError(f"provider '{provider}' has no key_column in the registry")
        setattr(user, col, encrypted)
        await session.commit()

    async def clear(self, user: Any, provider: str, session: Any) -> None:
        col = get_registry().key_column(provider)
        if not col:
            return
        setattr(user, col, None)
        await session.commit()
