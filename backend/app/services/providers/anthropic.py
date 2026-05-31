"""Anthropic (Claude) adapter.

client_kind=anthropic -> ChatAnthropic. cache_class=inline (Phase 4 adds the
``cache_control`` block assembly + per-model token-floor gating). This subclass
already reads Anthropic's distinct cache-accounting fields correctly.
"""

from __future__ import annotations

from typing import Any

from app.services.providers.base import ProviderAdapter, CacheUsage, _response_usage


class AnthropicAdapter(ProviderAdapter):
    def read_cache_usage(self, response: Any) -> CacheUsage:
        usage = _response_usage(response)
        cache_read = int(usage.get("cache_read_input_tokens") or 0)
        cache_creation = int(usage.get("cache_creation_input_tokens") or 0)
        # Anthropic "input_tokens" already excludes cached/created tokens.
        input_tokens = int(usage.get("input_tokens") or 0)
        return CacheUsage(
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_creation,
            uncached_input_tokens=input_tokens,
        )
