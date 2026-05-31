"""Tests for the registry-backed config endpoints (Phase 3.5).

Guarded by importorskip(fastapi) so they run in the container/CI (fastapi
present) and skip in a bare local env. The route handlers are plain async
functions over the registry, so we call them directly via asyncio.run.
"""

import asyncio

import pytest

pytest.importorskip("fastapi")


def test_providers_endpoint_enabled_only_and_secret_free():
    from app.api.v1.providers import list_providers

    out = asyncio.run(list_providers())
    assert out["default_provider"] == "cerebras"
    assert set(out["providers"]) == {"cerebras", "anthropic"}
    blob = repr(out)
    for leak in ("key_column", "validation", "probe_model", "base_url", "api_version"):
        assert leak not in blob
    cere = out["providers"]["cerebras"]
    assert cere["default_model"] == "gpt-oss-120b"
    assert any(m["id"] == "gpt-oss-120b" for m in cere["models"])


def test_config_llm_is_registry_backed():
    from app.api.v1.config_routes import llm_config

    out = asyncio.run(llm_config())
    assert out["default_provider"] == "cerebras"
    assert set(out["providers"]) == {"cerebras", "anthropic"}
    # verified pricing flows from the registry (not stale config.py numbers)
    assert out["providers"]["anthropic"]["model_id"] == "claude-haiku-4-5-20251001"
    assert out["providers"]["anthropic"]["output"] == 5.00


def test_models_endpoint_only_enabled_providers():
    from app.api.v1.models import list_models

    out = asyncio.run(list_models())
    provs = {m["provider"] for m in out["models"]}
    assert provs == {"cerebras", "anthropic"}
    ids = {m["id"] for m in out["models"]}
    assert "gpt-oss-120b" in ids and "claude-haiku-4-5-20251001" in ids
    # a disabled-provider model must never leak here
    assert "grok-4.3" not in ids
