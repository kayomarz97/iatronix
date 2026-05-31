"""Tests for the provider registry (config/providers.yaml + loader).

These pin the Phase 3 contract: enabled set, model lookups, role resolution,
secret-free public view, and fail-fast validation.
"""

import textwrap

import pytest

from app.services.provider_registry import (
    ProviderRegistry,
    ProviderRegistryError,
    load_registry,
)


# --- the real shipped registry ------------------------------------------------

def test_real_registry_loads_and_enabled_set():
    reg = load_registry()  # default path -> backend/config/providers.yaml
    assert reg.default_provider == "cerebras"
    assert set(reg.enabled_providers().keys()) == {"cerebras", "anthropic"}
    # all six are wired (one-flag-away), even if disabled
    assert set(reg.allowed_providers()) == {
        "cerebras", "anthropic", "gemini", "xai", "openai", "openrouter"
    }
    for off in ("gemini", "xai", "openai", "openrouter"):
        assert reg.is_enabled(off) is False


def test_model_lookups_and_per_model_caching():
    reg = load_registry()
    assert reg.provider_for_model("gpt-oss-120b") == "cerebras"
    assert reg.provider_for_model("claude-haiku-4-5-20251001") == "anthropic"
    # per-MODEL caching: gpt-oss caches, the Cerebras llama does not
    assert reg.supports_caching("gpt-oss-120b") is True
    assert reg.supports_caching("llama-3.3-70b") is False
    # verified pricing made it into the registry (not the stale config.py/registry numbers)
    assert reg.pricing("claude-haiku-4-5-20251001")["input"] == 1.00
    assert reg.pricing("claude-haiku-4-5-20251001")["output"] == 5.00
    assert reg.min_cache_tokens("claude-haiku-4-5-20251001") == 4096


def test_role_resolution():
    reg = load_registry()
    assert reg.default_model("anthropic") == "claude-haiku-4-5-20251001"
    assert reg.default_model("cerebras") == "gpt-oss-120b"
    assert reg.default_model_for_role("anthropic", "sonnet_fallback") == "claude-sonnet-4-6"
    assert reg.default_model_for_role("anthropic", "vision") == "claude-sonnet-4-6"
    assert reg.default_model_for_role("cerebras", "classify") == "gpt-oss-120b"
    assert reg.default_model_for_role("anthropic", "nonexistent") is None


def test_key_columns_and_cache_classes():
    reg = load_registry()
    assert reg.key_column("anthropic") == "anthropic_api_key"
    assert reg.key_column("openrouter") == "openrouter_key"
    assert reg.cache_class("anthropic") == "inline"
    assert reg.cache_class("cerebras") == "auto_prefix"
    assert reg.cache_class("gemini") == "stateful"
    assert reg.cache_class("openrouter") == "conditional"


def test_public_view_is_enabled_only_and_secret_free():
    reg = load_registry()
    pub = reg.public_view()
    assert set(pub["providers"].keys()) == {"cerebras", "anthropic"}
    assert pub["default_provider"] == "cerebras"
    # no secret-ish fields leak to the frontend payload
    blob = repr(pub)
    for leak in ("key_column", "validation", "probe_model", "api_version", "base_url"):
        assert leak not in blob
    # models carry display + pricing for the picker
    cere = pub["providers"]["cerebras"]
    assert cere["default_model"] == "gpt-oss-120b"
    assert any(m["id"] == "gpt-oss-120b" for m in cere["models"])


def test_deep_search_bounds_present():
    reg = load_registry()
    ds = reg.deep_search
    assert ds["max_depth"] == 5
    assert ds["total_budget_seconds"] == 120


# --- validation / fail-fast ---------------------------------------------------

def _write(tmp_path, body: str):
    p = tmp_path / "providers.yaml"
    p.write_text(textwrap.dedent(body))
    return p


def test_validation_rejects_disabled_default_provider(tmp_path):
    p = _write(tmp_path, """
        version: 1
        default_provider: cerebras
        providers:
          cerebras:
            display: Cerebras
            enabled: false
            client_kind: openai_compatible
            key_column: cerebras_api_key
            cache_class: auto_prefix
            default_model: gpt-oss-120b
            models:
              - {id: gpt-oss-120b}
    """)
    with pytest.raises(ProviderRegistryError):
        load_registry(p)


def test_validation_rejects_default_model_not_in_models(tmp_path):
    p = _write(tmp_path, """
        version: 1
        default_provider: cerebras
        providers:
          cerebras:
            display: Cerebras
            enabled: true
            client_kind: openai_compatible
            key_column: cerebras_api_key
            cache_class: auto_prefix
            default_model: missing-model
            models:
              - {id: gpt-oss-120b}
    """)
    with pytest.raises(ProviderRegistryError):
        load_registry(p)


def test_validation_rejects_duplicate_model_ids(tmp_path):
    p = _write(tmp_path, """
        version: 1
        default_provider: cerebras
        providers:
          cerebras:
            display: Cerebras
            enabled: true
            client_kind: openai_compatible
            key_column: cerebras_api_key
            cache_class: auto_prefix
            default_model: dup
            models: [{id: dup}]
          openai:
            display: OpenAI
            enabled: false
            client_kind: openai_compatible
            key_column: openai_api_key
            cache_class: auto_prefix
            default_model: dup
            models: [{id: dup}]
    """)
    with pytest.raises(ProviderRegistryError):
        load_registry(p)


def test_validation_rejects_bad_cache_class(tmp_path):
    p = _write(tmp_path, """
        version: 1
        default_provider: cerebras
        providers:
          cerebras:
            display: Cerebras
            enabled: true
            client_kind: openai_compatible
            key_column: cerebras_api_key
            cache_class: telepathy
            default_model: gpt-oss-120b
            models: [{id: gpt-oss-120b}]
    """)
    with pytest.raises(ProviderRegistryError):
        load_registry(p)
