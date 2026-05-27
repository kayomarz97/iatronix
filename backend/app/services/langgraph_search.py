"""Parallel search graph using LangGraph for concurrent data fetch, vector search, and semantic cache."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

logger = logging.getLogger(__name__)


class SearchState(TypedDict):
    # Inputs
    query: str           # rewritten query — used for vector search
    original_query: str  # original user query — used for semantic cache
    query_type: str
    normalized_model: str
    use_api_fetch: bool
    use_vector: bool
    routing: Any
    user_llm_key: Optional[str]
    user_llm_provider: Optional[str]
    user_voyage_key: Optional[str]
    user_email: Optional[str]
    user_ncbi_key: Optional[str]
    api_fetch_timeout: float
    pubmed_expansion_terms: Optional[dict]
    force_refresh: bool  # If True, bypass all cache layers

    # Outputs — each written by a separate parallel node
    fetched_data: Any
    vector_results: list
    sem_result: Any


async def fetch_node(state: SearchState) -> dict:
    """Fetch external API data (ChEMBL, PubMed, DrugBank, etc.)."""
    routing = state.get("routing")
    if not state["use_api_fetch"] or not routing or not routing.fetch_enabled:
        return {"fetched_data": None}

    from app.services.data_fetcher import FetchedData, fetch_data_for_query

    try:
        result = await asyncio.wait_for(
            fetch_data_for_query(
                state["query_type"],
                routing.entities,
                condition_context=routing.condition_context,
                user_email=state.get("user_email"),
                ncbi_api_key=state.get("user_ncbi_key"),
                pubmed_expansion_terms=state.get("pubmed_expansion_terms"),
            ),
            timeout=state["api_fetch_timeout"],
        )
        return {"fetched_data": result}
    except asyncio.TimeoutError:
        logger.warning("search_graph: API fetch timed out — returning empty data for evidence floor retry")
        # Always False on timeout: the evidence floor in _expand_retrieval_if_needed will retry
        # with progressive broadening before giving up. Bypassing that with a True value here
        # would skip expansion entirely and fall through to generate mode.
        return {"fetched_data": FetchedData(query_type=state["query_type"], fallback_to_llm=False)}
    except Exception as exc:
        logger.warning("search_graph: API fetch error: %s", exc)
        return {"fetched_data": None}


async def vector_node(state: SearchState) -> dict:
    """Run pgvector similarity search."""
    if not state["use_vector"]:
        return {"vector_results": []}

    from app.services.vector_search import search as vector_search

    try:
        results = await vector_search(
            state["query"],
            user_key=state.get("user_llm_key"),
            user_provider=state.get("user_llm_provider"),
            voyage_api_key=state.get("user_voyage_key"),
        )
        return {"vector_results": results or []}
    except Exception as exc:
        logger.warning("search_graph: vector search error: %s", exc)
        return {"vector_results": []}


async def semantic_cache_node(state: SearchState) -> dict:
    """Check the semantic cache for a prior similar query (uses original, not rewritten, query).

    Skipped entirely if force_refresh=True.
    """
    from app.services.semantic_cache import semantic_cache_get

    # Skip cache if force_refresh is set
    if state.get("force_refresh", False):
        return {"sem_result": None}

    try:
        result = await semantic_cache_get(
            state["original_query"],
            state["query_type"],
            state["normalized_model"],
            provider=state.get("user_llm_provider"),
            api_key=state.get("user_llm_key"),
            voyage_api_key=state.get("user_voyage_key"),
        )
        return {"sem_result": result}
    except Exception as exc:
        logger.warning("search_graph: semantic cache error: %s", exc)
        return {"sem_result": None}


def _build_graph() -> Any:
    g = StateGraph(SearchState)
    g.add_node("fetch", fetch_node)
    g.add_node("vector", vector_node)
    g.add_node("semantic_cache", semantic_cache_node)

    # Fan-out: START → all three nodes run in parallel
    g.add_edge(START, "fetch")
    g.add_edge(START, "vector")
    g.add_edge(START, "semantic_cache")

    # Fan-in: all three converge on END
    g.add_edge("fetch", END)
    g.add_edge("vector", END)
    g.add_edge("semantic_cache", END)

    return g.compile()


_search_graph = _build_graph()


async def run_search_graph(
    query: str,
    original_query: str,
    query_type: str,
    routing: Any,
    normalized_model: str,
    api_fetch_timeout: float = 31.0,
    use_api_fetch: bool = True,
    use_vector: bool = True,
    user_llm_key: str | None = None,
    user_llm_provider: str | None = None,
    user_voyage_key: str | None = None,
    user_email: str | None = None,
    user_ncbi_key: str | None = None,
    pubmed_expansion_terms: dict | None = None,
    force_refresh: bool = False,
) -> tuple[Any, list, Any]:
    """Run parallel search (fetch + vector + semantic cache) via LangGraph.

    query is the rewritten query used for vector search.
    original_query is used for semantic cache lookup.
    Returns (fetched_data, vector_results, sem_result).
    """
    initial: SearchState = {
        "query": query,
        "original_query": original_query,
        "query_type": query_type,
        "normalized_model": normalized_model,
        "use_api_fetch": use_api_fetch,
        "use_vector": use_vector,
        "routing": routing,
        "user_llm_key": user_llm_key,
        "user_llm_provider": user_llm_provider,
        "user_voyage_key": user_voyage_key,
        "user_email": user_email,
        "user_ncbi_key": user_ncbi_key,
        "api_fetch_timeout": api_fetch_timeout,
        "pubmed_expansion_terms": pubmed_expansion_terms,
        "force_refresh": force_refresh,
        "fetched_data": None,
        "vector_results": [],
        "sem_result": None,
    }

    final = await _search_graph.ainvoke(initial)
    return final.get("fetched_data"), final.get("vector_results", []), final.get("sem_result")
