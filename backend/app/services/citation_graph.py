"""Citation-chasing as a bounded cyclic LangGraph sub-graph (Phase 6).

The brief asks the Phase-5 citation-chasing to be modelled as a bounded cyclic
sub-graph. This expresses it with LangGraph (same idioms as the working
``langgraph_search.py``): a single ``chase`` node looped by a conditional edge
that terminates on depth cap / empty frontier / budget exhaustion — with a small
``recursion_limit`` backstop (LangGraph's default is 1000, INTEGRATION_NOTES §B).

The termination predicate (``should_chase``) and the fetchers (``icite_fetcher``)
are the same tested primitives the asyncio engine uses, so behaviour matches.

NOTE: LangGraph isn't importable in the unit-test env; this module is
py_compile-checked here and exercised at the Phase-10 dev rebuild. The pure
decision logic it relies on is unit-tested in ``deep_search``.
"""

from __future__ import annotations

import asyncio
import logging
import operator
import time
from typing import Annotated, Any

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from app.services.deep_search import ChaseConfig, ChasedArticle, should_chase
from app.services.deep_search_sources import icite_fetcher

logger = logging.getLogger(__name__)


class ChaseState(TypedDict):
    frontier: list            # ChasedArticle to expand next depth
    articles: Annotated[list, operator.add]  # accumulator (reducer-safe)
    seen: set
    depth: int
    deadline: float
    max_depth: int
    per_branch_timeout: float


async def chase_node(state: ChaseState) -> dict:
    """Fetch citations for the whole current frontier in parallel; emit the fresh set."""
    if time.monotonic() >= state["deadline"]:
        return {"frontier": [], "depth": state["depth"]}

    async def _one(seed: ChasedArticle) -> list:
        try:
            return await asyncio.wait_for(icite_fetcher(seed), timeout=state["per_branch_timeout"])
        except Exception:
            return []

    results = await asyncio.gather(*(_one(s) for s in state["frontier"]), return_exceptions=True)

    seen = state["seen"]
    fresh: list[ChasedArticle] = []
    next_depth = state["depth"] + 1
    for r in results:
        if not isinstance(r, list):
            continue
        for a in r:
            k = a.key()
            if k and k not in seen:
                seen.add(k)
                a.depth = next_depth
                fresh.append(a)
    return {"articles": fresh, "frontier": fresh, "depth": next_depth, "seen": seen}


def route_after_chase(state: ChaseState) -> str:
    """Conditional edge: loop back to chase, or terminate."""
    time_up = time.monotonic() >= state["deadline"]
    if should_chase(state["depth"], len(state["frontier"]), time_up, state["max_depth"]):
        return "chase"
    return END


def _build_graph() -> Any:
    g = StateGraph(ChaseState)
    g.add_node("chase", chase_node)
    g.add_edge(START, "chase")
    g.add_conditional_edges("chase", route_after_chase, {"chase": "chase", END: END})
    return g.compile()


_citation_graph = _build_graph()


async def run_citation_graph(
    seeds: list[ChasedArticle],
    config: ChaseConfig | None = None,
) -> list[ChasedArticle]:
    """Run the bounded cyclic citation chaser; return all grounded articles found."""
    cfg = config or ChaseConfig.from_registry()
    if not seeds:
        return []
    initial: ChaseState = {
        "frontier": list(seeds),
        "articles": [],
        "seen": {s.key() for s in seeds if s.key()},
        "depth": 0,
        "deadline": time.monotonic() + cfg.total_budget_seconds,
        "max_depth": cfg.max_depth,
        "per_branch_timeout": cfg.per_branch_timeout_seconds,
    }
    # recursion_limit backstop: never spin past the depth cap even if logic regresses.
    final = await _citation_graph.ainvoke(initial, {"recursion_limit": cfg.max_depth + 5})
    return final.get("articles", [])
