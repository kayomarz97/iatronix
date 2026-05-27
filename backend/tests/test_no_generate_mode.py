"""Asserts that prompt_mode="generate" is unreachable in the live request path.
pytestmark = pytest.mark.citation (set below).


Two layers of defence:
  1. Static grep — the source must not contain an unconditional assignment
     `prompt_mode = "generate"` (the ternary was removed; only "format" remains).
  2. Unit test — force an empty FetchedData into _expand_retrieval_if_needed and
     assert EvidenceFloorError is raised rather than an LLM call being made.
"""
import inspect
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.evidence_floor import EvidenceFloorError

pytestmark = pytest.mark.citation


class TestNoGenerateMode:
    def test_rag_pipeline_forces_format_mode(self):
        """prompt_mode must always be 'format' — no ternary fallback to 'generate'."""
        pipeline_path = (
            Path(__file__).parent.parent / "app" / "services" / "rag_pipeline.py"
        )
        source = pipeline_path.read_text()
        # The old ternary: prompt_mode = "format" if (...) else "generate"
        assert 'else "generate"' not in source, (
            "Found ternary that can produce prompt_mode='generate' in rag_pipeline.py. "
            "Evidence floor must force prompt_mode='format' unconditionally."
        )
        # Confirm "format" assignment exists
        assert 'prompt_mode = "format"' in source

    def test_rag_pipeline_has_no_raw_generate_assignment(self):
        """The string 'prompt_mode = \"generate\"' must not appear as a plain assignment."""
        pipeline_path = (
            Path(__file__).parent.parent / "app" / "services" / "rag_pipeline.py"
        )
        source = pipeline_path.read_text()
        # Allow it only inside string literals (comments, docstrings) — not as live code
        # We check for the assignment form specifically
        matches = re.findall(r'prompt_mode\s*=\s*["\']generate["\']', source)
        assert not matches, (
            f"Found raw generate-mode assignment in rag_pipeline.py: {matches}"
        )

    def test_langgraph_timeout_does_not_set_fallback_to_llm(self):
        """fetch_node timeout must return fallback_to_llm=False so evidence floor can retry."""
        langgraph_path = (
            Path(__file__).parent.parent / "app" / "services" / "langgraph_search.py"
        )
        source = langgraph_path.read_text()
        # Look only at non-comment, non-docstring code lines for a True assignment
        code_lines = [
            line for line in source.splitlines()
            if not line.strip().startswith("#") and "fallback_to_llm=True" in line
        ]
        assert not code_lines, (
            "langgraph_search.py has live code setting fallback_to_llm=True on timeout. "
            "The evidence floor requires fallback_to_llm=False so it can retry. "
            f"Offending lines: {code_lines}"
        )

    @pytest.mark.asyncio
    async def test_empty_fetched_data_raises_evidence_floor_error_not_llm_call(self):
        """When retrieval returns nothing, EvidenceFloorError is raised — no LLM call."""
        from app.services.evidence_floor import ensure_evidence

        empty_fd = MagicMock()
        empty_fd.query_type = "disease"
        empty_fd.fallback_to_llm = False
        empty_fd.drug_data = None
        empty_fd.disease_data = None
        empty_fd.condition_data = None
        empty_fd.procedure_data = None
        empty_fd.evidence_data = None
        empty_fd.comparative_evidence = None
        empty_fd.comparative_drug_data = []
        empty_fd.comorbidity_data = []

        failing_result = MagicMock()
        failing_result.fetch_success = False
        failing_result.label_url = None

        with (
            patch(
                "app.services.evidence_floor.asyncio.wait_for",
                new=AsyncMock(return_value=failing_result),
            ),
        ):
            with pytest.raises(EvidenceFloorError):
                await ensure_evidence(empty_fd, "completely unknown nonsense query", "evidence")
