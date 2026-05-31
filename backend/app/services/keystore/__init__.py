"""KeyStore factory — Postgres authoritative, optional Firestore mirror.

``get_keystore()`` returns a process-wide singleton:
  - Firestore disabled -> PostgresKeyStore
  - Firestore enabled  -> DualKeyStore(primary=config.keystore_primary), which
    reads from the configured primary and dual-writes to both. Switching
    ``keystore_primary`` postgres<->firestore is a config flip (data already
    mirrored), so migration needs no backfill.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Optional

from app.config import settings
from app.services.keystore.base import KeyStore
from app.services.keystore.postgres import PostgresKeyStore

logger = logging.getLogger(__name__)


class DualKeyStore(KeyStore):
    """Reads from the configured primary; writes to both (secondary best-effort)."""

    def __init__(self, postgres: PostgresKeyStore, firestore, primary: str = "postgres"):
        self._pg = postgres
        self._fs = firestore
        self._primary_name = primary if primary in ("postgres", "firestore") else "postgres"
        self._primary = self._pg if self._primary_name == "postgres" else self._fs
        self._secondary = self._fs if self._primary_name == "postgres" else self._pg

    def get_encrypted(self, user: Any, provider: str) -> Optional[str]:
        val = self._primary.get_encrypted(user, provider)
        if val is None and self._secondary is not None:
            # Migration safety: fall back to the other store if primary lacks it.
            val = self._secondary.get_encrypted(user, provider)
        return val

    async def set_encrypted(self, user: Any, provider: str, encrypted: str, session: Any) -> None:
        await self._pg.set_encrypted(user, provider, encrypted, session)
        await self._fs.set_encrypted(user, provider, encrypted, session)

    async def clear(self, user: Any, provider: str, session: Any) -> None:
        await self._pg.clear(user, provider, session)
        await self._fs.clear(user, provider, session)


@lru_cache(maxsize=1)
def get_keystore() -> KeyStore:
    pg = PostgresKeyStore()
    if not settings.keystore_firestore_enabled:
        return pg
    try:
        from app.services.keystore.firestore import FirestoreKeyStore

        ks = DualKeyStore(pg, FirestoreKeyStore(), primary=settings.keystore_primary)
        logger.info("KeyStore: dual (postgres + firestore), primary=%s", settings.keystore_primary)
        return ks
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Firestore KeyStore unavailable, falling back to Postgres only: %s", exc)
        return pg


__all__ = ["KeyStore", "PostgresKeyStore", "DualKeyStore", "get_keystore"]
