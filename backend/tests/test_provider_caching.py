"""Provider caching assembly tests (Phase 4).

Verifies the per-provider message assembly: Cerebras/auto-prefix stable concat
order (the byte-identical prefix invariant) and Anthropic cache_control gated on
the real per-model token floor (Haiku 4.5 = 4096 tokens).
"""

import pytest

pytest.importorskip("langchain_core")

from app.services.providers import get_adapter, PromptBlocks


def test_cerebras_auto_prefix_concat_order():
    a = get_adapter("cerebras")
    msgs = a.assemble_messages(
        PromptBlocks(static_system="STATIC", data_block="DATA", dynamic_system="DYN", user_text="Q")
    )
    assert len(msgs) == 2
    sys, human = msgs
    # one SystemMessage, plain string, static -> data -> dynamic (prefix invariant)
    assert isinstance(sys.content, str)
    assert sys.content == "STATIC\n\nDATA\n\nDYN"
    assert human.content == "Q"


def test_anthropic_cache_control_gated_on_model_floor():
    a = get_adapter("anthropic")
    big = "x" * 20000   # > 4096 tokens * ~4 chars/token (Haiku floor)
    msgs = a.assemble_messages(
        PromptBlocks(static_system=big, data_block=big, dynamic_system="DYN", user_text="Q"),
        model_id="claude-haiku-4-5-20251001",
    )
    sys = msgs[0]
    assert isinstance(sys.content, list)
    assert sys.content[0]["cache_control"] == {"type": "ephemeral"}   # static
    assert sys.content[1]["cache_control"] == {"type": "ephemeral"}   # data block
    assert "cache_control" not in sys.content[2]                       # dynamic uncached


def test_anthropic_below_floor_not_cache_controlled():
    a = get_adapter("anthropic")
    small = "y" * 100   # well below Haiku's 4096-token floor
    msgs = a.assemble_messages(
        PromptBlocks(static_system=small, data_block="", user_text="Q"),
        model_id="claude-haiku-4-5-20251001",
    )
    # no breakpoint wasted on a sub-floor block (Anthropic would silently ignore it)
    assert "cache_control" not in msgs[0].content[0]


def test_apply_cache_remains_noop_passthrough():
    # assemble_messages is the active path; apply_cache stays a no-op
    a = get_adapter("cerebras")
    b = PromptBlocks(static_system="s", user_text="q")
    assert a.apply_cache(b) is b
