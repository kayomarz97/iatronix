"""Adapter-layer conformance tests (Phase 3.2).

Routing / model-resolution / per-model caching use only the registry and need
no heavy deps. The build_client test is guarded by importorskip.
"""

import pytest

from app.services.providers import (
    get_adapter,
    resolve_provider,
    ProviderAdapter,
    PromptBlocks,
)
from app.services.providers.anthropic import AnthropicAdapter
from app.services.providers.cerebras import CerebrasAdapter


# --- routing ------------------------------------------------------------------

@pytest.mark.parametrize("model_id,expected", [
    ("gpt-oss-120b", "cerebras"),            # registry
    ("llama-3.3-70b", "cerebras"),
    ("claude-haiku-4-5-20251001", "anthropic"),
    ("claude-sonnet-4-6", "anthropic"),
    ("gpt-4o-mini", "openai"),
    ("grok-4.3", "xai"),                     # registry fixes the old mis-route to anthropic
    ("google/gemma-4-31b-it", "openrouter"),
    ("claude-3-5-sonnet-20241022", "anthropic"),  # NOT in registry -> prefix fallback
    ("o3-mini", "openai"),                   # prefix fallback
    ("gpt-oss-FUTURE", "cerebras"),          # gpt-oss must beat gpt- (load-bearing)
])
def test_resolve_provider_routing(model_id, expected):
    assert resolve_provider(model_id) == expected


def test_resolve_provider_user_override_and_aliases():
    # explicit choice wins over model-id inference
    assert resolve_provider("gpt-oss-120b", user_provider="anthropic") == "anthropic"
    # legacy aliases normalise to canonical registry ids
    assert resolve_provider("x", user_provider="google") == "gemini"
    assert resolve_provider("x", user_provider="grok") == "xai"


# --- adapter selection --------------------------------------------------------

def test_get_adapter_types():
    assert isinstance(get_adapter("anthropic"), AnthropicAdapter)
    assert isinstance(get_adapter("cerebras"), CerebrasAdapter)
    # providers without a dedicated subclass use the generic adapter
    for pid in ("gemini", "openai", "openrouter", "xai"):
        a = get_adapter(pid)
        assert isinstance(a, ProviderAdapter)
        assert not isinstance(a, (AnthropicAdapter, CerebrasAdapter))


# --- model resolution (the generalised "/" replacement) -----------------------

def test_resolve_model_ownership_rules():
    cere = get_adapter("cerebras")
    assert cere.resolve_model("gpt-oss-120b") == "gpt-oss-120b"          # mine -> keep
    assert cere.resolve_model("") == "gpt-oss-120b"                       # empty -> default
    assert cere.resolve_model("brand-new-cerebras-x") == "brand-new-cerebras-x"  # unknown -> BYOK passthrough
    assert cere.resolve_model("claude-haiku-4-5-20251001") == "gpt-oss-120b"     # other provider's -> default

    anth = get_adapter("anthropic")
    assert anth.resolve_model("claude-sonnet-4-6") == "claude-sonnet-4-6"
    assert anth.resolve_model("google/gemma-4-31b-it") == "claude-haiku-4-5-20251001"  # not mine -> default


def test_per_model_caching_via_adapter():
    cere = get_adapter("cerebras")
    assert cere.supports_caching("gpt-oss-120b") is True
    assert cere.supports_caching("llama-3.3-70b") is False
    assert cere.cache_class == "auto_prefix"
    anth = get_adapter("anthropic")
    assert anth.cache_class == "inline"


def test_cache_methods_are_noop_in_phase3():
    a = get_adapter("cerebras")
    blocks = PromptBlocks(static_system="S", data_block="D", dynamic_system="Y", user_text="U")
    assert a.prepare_cache(blocks) is None
    assert a.apply_cache(blocks) is blocks          # unchanged
    a.release_cache(None)                            # no error


# --- client construction (guarded) -------------------------------------------

def test_build_client_picks_right_client_kind():
    pytest.importorskip("langchain_openai")
    pytest.importorskip("langchain_anthropic")
    try:
        import app.config  # noqa: F401  (build_client reads settings)
    except Exception:
        pytest.skip("app.config not importable without env in this environment")

    cere = get_adapter("cerebras").build_client("gpt-oss-120b", "dummy-key", 1024)
    assert cere.__class__.__name__ == "ChatOpenAI"
    anth = get_adapter("anthropic").build_client("claude-haiku-4-5-20251001", "dummy-key", 1024)
    assert anth.__class__.__name__ == "ChatAnthropic"
