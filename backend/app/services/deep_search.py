"""Deep-grounded citation chasing (Phase 5).

When first-pass retrieval is thin, fan out parallel branches that follow an
article's citations (forward = cited-by, backward = references) and chase
open-access fulltext, **bounded** by depth + a wall-clock budget — all
registry-configurable (config/providers.yaml ``deep_search``).

Replaces the old "instant degrade" terminal: instead of returning a quick
ungrounded answer, we chase grounded evidence within the budget, then either
assemble from what we found or return the honest "no evidence" terminal.

The engine is provider-of-citations-agnostic: it takes a ``fetcher`` callable so
it is unit-testable without live API calls. Real fetchers live in
``deep_search_sources.py`` (NCBI iCite / Semantic Scholar / Unpaywall).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChaseConfig:
    max_depth: int = 5
    branch_parallelism: int = 6
    total_budget_seconds: float = 120.0
    per_branch_timeout_seconds: float = 20.0

    @classmethod
    def from_registry(cls) -> "ChaseConfig":
        try:
            from app.services.provider_registry import get_registry

            ds = get_registry().deep_search or {}
        except Exception:
            ds = {}
        return cls(
            max_depth=int(ds.get("max_depth", 5)),
            branch_parallelism=int(ds.get("branch_parallelism", 6)),
            total_budget_seconds=float(ds.get("total_budget_seconds", 120.0)),
            per_branch_timeout_seconds=float(ds.get("per_branch_timeout_seconds", 20.0)),
        )


def should_chase(depth: int, frontier_count: int, time_up: bool, max_depth: int) -> bool:
    """Pure termination predicate for the bounded citation cycle.

    Shared by the asyncio engine and the LangGraph sub-graph (citation_graph.py)
    so both bound depth/budget identically. Continue iff there is still a frontier
    to chase, we are under the depth cap, and the budget is not exhausted.
    """
    if time_up:
        return False
    if depth >= max_depth:
        return False
    return frontier_count > 0


@dataclass
class ChasedArticle:
    title: str
    source: str
    pmid: Optional[str] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    depth: int = 0

    def key(self) -> Optional[str]:
        return self.doi or (f"PMID:{self.pmid}" if self.pmid else None) or (self.title.lower().strip() or None)


# A fetcher takes a seed article and returns newly-discovered citing/cited articles.
Fetcher = Callable[[ChasedArticle], Awaitable[list[ChasedArticle]]]

# Progress callback: (stage_message, count_found_so_far)
ProgressCb = Callable[[str, int], None]


@dataclass
class DeepSearchResult:
    articles: list[ChasedArticle] = field(default_factory=list)
    branches_explored: int = 0
    max_depth_reached: int = 0
    timed_out: bool = False

    @property
    def found_evidence(self) -> bool:
        # Honest terminal: only "found" if at least one URL-bearing (citable) article surfaced.
        return any(a.url for a in self.articles)


async def deep_search(
    seeds: list[ChasedArticle],
    fetcher: Fetcher,
    *,
    config: Optional[ChaseConfig] = None,
    on_progress: Optional[ProgressCb] = None,
) -> DeepSearchResult:
    """Fan out one bounded cyclic branch per seed; chase citations in parallel.

    Guarantees: depth never exceeds ``max_depth``; total wall-clock never exceeds
    ``total_budget_seconds`` (cooperative deadline checks); concurrency capped by
    ``branch_parallelism``; results de-duplicated by DOI/PMID/title.
    """
    cfg = config or ChaseConfig.from_registry()
    deadline = time.monotonic() + cfg.total_budget_seconds
    seen: set[str] = set()
    result = DeepSearchResult()
    sem = asyncio.Semaphore(max(1, cfg.branch_parallelism))

    # seed dedup
    for s in seeds:
        k = s.key()
        if k:
            seen.add(k)

    def _emit(msg: str) -> None:
        if on_progress:
            try:
                on_progress(msg, len(result.articles))
            except Exception:
                pass

    async def chase(seed: ChasedArticle, depth: int) -> None:
        if depth > cfg.max_depth:
            return
        if time.monotonic() >= deadline:
            result.timed_out = True
            return
        result.branches_explored += 1
        result.max_depth_reached = max(result.max_depth_reached, depth)
        async with sem:
            if time.monotonic() >= deadline:
                result.timed_out = True
                return
            try:
                remaining = deadline - time.monotonic()
                timeout = min(cfg.per_branch_timeout_seconds, max(0.1, remaining))
                found = await asyncio.wait_for(fetcher(seed), timeout=timeout)
            except asyncio.TimeoutError:
                result.timed_out = True
                return
            except Exception as exc:  # a single branch failing must not abort the search
                logger.debug("deep_search branch failed at depth %d: %s", depth, exc)
                return

        fresh: list[ChasedArticle] = []
        for a in found or []:
            k = a.key()
            if not k or k in seen:
                continue
            seen.add(k)
            a.depth = depth
            result.articles.append(a)
            fresh.append(a)

        if fresh:
            _emit(f"Following citations from {seed.source or 'source'} — {len(result.articles)} grounded so far")
            # recurse one level deeper, in parallel (bounded cyclic sub-branch)
            await asyncio.gather(*(chase(a, depth + 1) for a in fresh), return_exceptions=True)

    _emit("Standard sources thin — chasing citations for primary evidence")
    await asyncio.gather(*(chase(s, 1) for s in seeds), return_exceptions=True)
    return result
