"""KeyStore tests (Phase 3.6b).

The Postgres backend is pure attribute access over the registry's provider->column
map — testable with a fake user + fake async session. Guarded by importorskip
because keystore.base imports byok (cryptography/httpx), present in the container.
"""

import asyncio
import types

import pytest

pytest.importorskip("cryptography")
pytest.importorskip("httpx")

from app.services.keystore import get_keystore, DualKeyStore, PostgresKeyStore
from app.services.keystore.postgres import PostgresKeyStore as PG


class _FakeSession:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


def _user(**cols):
    return types.SimpleNamespace(firebase_uid="uid-1", **cols)


def test_get_encrypted_reads_registry_column():
    ks = PG()
    user = _user(anthropic_api_key="ENC_A", cerebras_api_key=None)
    assert ks.get_encrypted(user, "anthropic") == "ENC_A"
    assert ks.get_encrypted(user, "cerebras") is None
    # provider whose column attr is simply absent on the object -> None (no crash)
    assert ks.get_encrypted(user, "gemini") is None


def test_status_covers_all_registry_providers():
    ks = PG()
    user = _user(anthropic_api_key="ENC_A")
    st = ks.status(user)
    assert st["anthropic"] is True
    # every registry provider with a key column appears, defaulting to False
    for p in ("cerebras", "gemini", "xai", "openai", "openrouter"):
        assert st[p] is False


def test_set_and_clear_write_column_and_commit():
    ks = PG()
    user = _user()
    sess = _FakeSession()
    asyncio.run(ks.set_encrypted(user, "cerebras", "ENC_C", sess))
    assert user.cerebras_api_key == "ENC_C"
    assert sess.commits == 1
    asyncio.run(ks.clear(user, "cerebras", sess))
    assert user.cerebras_api_key is None
    assert sess.commits == 2


def test_set_encrypted_rejects_unknown_provider():
    ks = PG()
    with pytest.raises(ValueError):
        asyncio.run(ks.set_encrypted(_user(), "nope", "x", _FakeSession()))


def test_factory_returns_postgres_when_firestore_disabled(monkeypatch):
    get_keystore.cache_clear()
    from app.config import settings
    monkeypatch.setattr(settings, "keystore_firestore_enabled", False, raising=False)
    ks = get_keystore()
    assert isinstance(ks, PostgresKeyStore)
    get_keystore.cache_clear()


def test_dual_keystore_dual_writes_and_reads_primary():
    # fake backends to verify dual-write + primary-read without real Firestore
    class _Mem:
        def __init__(self): self.data = {}
        def get_encrypted(self, user, provider): return self.data.get(provider)
        async def set_encrypted(self, user, provider, enc, session): self.data[provider] = enc
        async def clear(self, user, provider, session): self.data.pop(provider, None)

    pg, fs = _Mem(), _Mem()
    dual = DualKeyStore(pg, fs, primary="postgres")
    asyncio.run(dual.set_encrypted(_user(), "anthropic", "ENC", None))
    assert pg.data["anthropic"] == "ENC" and fs.data["anthropic"] == "ENC"  # dual-write
    # primary-read; secondary fallback for migration
    pg.data.pop("anthropic")
    assert dual.get_encrypted(_user(), "anthropic") == "ENC"  # falls back to fs
