"""Firestore KeyStore backend (Firebase Admin SDK — server-side only).

Stores Fernet-encrypted keys in ``user_llm_keys/{firebase_uid}`` documents, one
field per provider. Access is via the Admin SDK only; Firestore security rules
must DENY all client access (these are encrypted secrets, never client-readable).

Defensive by design: any Firestore error is logged and swallowed so a Firestore
outage can never break the authoritative Postgres path. Enabled via
``keystore_firestore_enabled``.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_COLLECTION = "user_llm_keys"


def _client():
    # Reuse the already-initialised firebase_admin app (see middleware/firebase_auth.py).
    from firebase_admin import firestore

    return firestore.client()


def _uid(user: Any) -> Optional[str]:
    return getattr(user, "firebase_uid", None)


class FirestoreKeyStore:
    """NOTE: not registered as a KeyStore ABC subclass on purpose — it is only ever
    used as the secondary mirror inside DualKeyStore, never standalone."""

    def get_encrypted(self, user: Any, provider: str) -> Optional[str]:
        uid = _uid(user)
        if not uid:
            return None
        try:
            doc = _client().collection(_COLLECTION).document(uid).get()
            if not doc.exists:
                return None
            return (doc.to_dict() or {}).get(provider)
        except Exception as exc:  # pragma: no cover - network/SDK dependent
            logger.warning("Firestore key read failed (%s): %s", provider, exc)
            return None

    async def set_encrypted(self, user: Any, provider: str, encrypted: str, session: Any) -> None:
        uid = _uid(user)
        if not uid:
            return
        try:
            _client().collection(_COLLECTION).document(uid).set({provider: encrypted}, merge=True)
        except Exception as exc:  # pragma: no cover
            logger.warning("Firestore key write failed (%s): %s", provider, exc)

    async def clear(self, user: Any, provider: str, session: Any) -> None:
        uid = _uid(user)
        if not uid:
            return
        try:
            from firebase_admin import firestore

            _client().collection(_COLLECTION).document(uid).update({provider: firestore.DELETE_FIELD})
        except Exception as exc:  # pragma: no cover
            logger.warning("Firestore key delete failed (%s): %s", provider, exc)
