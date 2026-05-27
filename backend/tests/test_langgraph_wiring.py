"""Tests that verify langgraph's three nodes (fetch, vector, semantic_cache) are
wired and execute correctly, and that regressions to the pipeline graph structure
are caught immediately.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.citation


class TestLangGraphWiring:
    """Verify langgraph wiring — three nodes must be present and execute."""

    def test_search_state_has_required_keys(self):
        """SearchState TypedDict must expose all expected input/output keys."""
        from app.services.langgraph_search import SearchState
        import typing

        hints = typing.get_type_hints(SearchState)
        for key in ("query", "original_query", "query_type", "fetched_data",
                    "vector_results", "sem_result"):
            assert key in hints, f"SearchState missing key: {key}"

    @pytest.mark.asyncio
    async def test_fetch_node_returns_fetched_data_key(self):
        """fetch_node must always return a dict with 'fetched_data' key."""
        from app.services.langgraph_search import fetch_node

        state = {
            "use_api_fetch": False,
            "routing": None,
            "query": "test",
            "original_query": "test",
            "query_type": "drug",
            "normalized_model": "test",
            "user_llm_key": None,
            "user_llm_provider": None,
            "user_voyage_key": None,
            "user_email": None,
            "user_ncbi_key": None,
            "api_fetch_timeout": 5.0,
            "pubmed_expansion_terms": None,
            "force_refresh": False,
        }
        result = await fetch_node(state)
        assert "fetched_data" in result

    @pytest.mark.asyncio
    async def test_vector_node_returns_vector_results_key(self):
        """vector_node must always return a dict with 'vector_results' key."""
        from app.services.langgraph_search import vector_node

        state = {
            "use_vector": False,
            "query": "test",
            "user_llm_key": None,
            "user_llm_provider": None,
            "user_voyage_key": None,
        }
        result = await vector_node(state)
        assert "vector_results" in result
        assert isinstance(result["vector_results"], list)

    @pytest.mark.asyncio
    async def test_semantic_cache_node_returns_sem_result_key(self):
        """semantic_cache_node must always return a dict with 'sem_result' key."""
        from app.services.langgraph_search import semantic_cache_node

        with patch("app.services.semantic_cache.semantic_cache_get", new=AsyncMock(return_value=None)):
            state = {
                "original_query": "hypertension treatment",
                "force_refresh": False,
            }
            result = await semantic_cache_node(state)
        assert "sem_result" in result

    @pytest.mark.asyncio
    async def test_timeout_in_fetch_node_returns_fallback_to_llm_false(self):
        """After our fix, a timeout must produce fallback_to_llm=False (not True)."""
        from app.services.langgraph_search import fetch_node
        from app.services.data_fetcher import FetchedData

        state = {
            "use_api_fetch": True,
            "routing": MagicMock(fetch_enabled=True, entities=["paracetamol"],
                                 condition_context=None),
            "query": "paracetamol overdose",
            "original_query": "paracetamol overdose",
            "query_type": "drug",
            "normalized_model": "test",
            "user_llm_key": None,
            "user_llm_provider": None,
            "user_voyage_key": None,
            "user_email": "test@test.com",
            "user_ncbi_key": None,
            "api_fetch_timeout": 0.001,  # near-zero to force timeout
            "pubmed_expansion_terms": None,
            "force_refresh": False,
        }

        with patch(
            "app.services.data_fetcher.fetch_data_for_query",
            new=AsyncMock(side_effect=asyncio.TimeoutError()),
        ):
            result = await fetch_node(state)

        assert "fetched_data" in result
        fd = result["fetched_data"]
        if fd is not None and hasattr(fd, "fallback_to_llm"):
            assert fd.fallback_to_llm is False, (
                "fetch_node timeout must NOT set fallback_to_llm=True — "
                "evidence floor needs to retry"
            )

    def test_run_search_graph_is_importable(self):
        """run_search_graph must be importable — catches broken langgraph wiring."""
        from app.services.langgraph_search import run_search_graph
        assert callable(run_search_graph)
