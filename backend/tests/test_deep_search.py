"""Deep-search engine tests (Phase 5) — bounds, dedup, budget, terminal state.

Uses a fake in-memory fetcher so the bounded-parallel orchestration is verified
without live API calls.
"""

import asyncio

from app.services.deep_search import (
    ChaseConfig,
    ChasedArticle,
    DeepSearchResult,
    deep_search,
)


def _seed(name="root"):
    return ChasedArticle(title=name, source="S", doi=name, url="u")


async def _tree_fetcher(seed):
    # each node yields 2 children with deterministic unique keys -> an infinite tree
    return [
        ChasedArticle(title=f"{seed.doi}-a", source="S", doi=f"{seed.doi}-a", url="u"),
        ChasedArticle(title=f"{seed.doi}-b", source="S", doi=f"{seed.doi}-b", url="u"),
    ]


def test_depth_is_bounded():
    cfg = ChaseConfig(max_depth=3, branch_parallelism=8, total_budget_seconds=30)
    res = asyncio.run(deep_search([_seed()], _tree_fetcher, config=cfg))
    assert res.max_depth_reached == 3            # never exceeds max_depth
    # depth1:2 + depth2:4 + depth3:8 = 14 (depth4 is pruned before fetching)
    assert len(res.articles) == 14
    assert res.found_evidence is True


def test_dedup_across_branches():
    async def same_child_fetcher(seed):
        return [ChasedArticle(title="shared", source="S", doi="SHARED", url="u")]

    cfg = ChaseConfig(max_depth=5, total_budget_seconds=30)
    res = asyncio.run(deep_search([_seed("x"), _seed("y")], same_child_fetcher, config=cfg))
    # "SHARED" discovered once despite two seeds + recursion
    assert sum(1 for a in res.articles if a.doi == "SHARED") == 1


def test_budget_timeout_is_respected():
    async def slow_fetcher(seed):
        await asyncio.sleep(1.0)
        return [ChasedArticle(title="late", source="S", doi="late", url="u")]

    cfg = ChaseConfig(max_depth=5, total_budget_seconds=0.2, per_branch_timeout_seconds=20)
    res = asyncio.run(deep_search([_seed()], slow_fetcher, config=cfg))
    assert res.timed_out is True
    assert len(res.articles) == 0                # nothing assembled past the budget


def test_no_evidence_terminal_when_nothing_url_bearing():
    async def urlless_fetcher(seed):
        return [ChasedArticle(title="no-url", source="S", doi="x", url=None)]

    cfg = ChaseConfig(max_depth=1, total_budget_seconds=30)
    res = asyncio.run(deep_search([_seed()], urlless_fetcher, config=cfg))
    # found articles but none citable -> honest "no evidence found"
    assert res.found_evidence is False


def test_empty_seeds_returns_empty():
    res = asyncio.run(deep_search([], _tree_fetcher, config=ChaseConfig()))
    assert res.articles == []
    assert res.found_evidence is False


def test_branch_failure_does_not_abort():
    calls = {"n": 0}

    async def flaky_fetcher(seed):
        calls["n"] += 1
        if seed.doi == "root":
            raise RuntimeError("boom")
        return [ChasedArticle(title="ok", source="S", doi="ok", url="u")]

    # root fails -> no children -> graceful empty (not a crash)
    res = asyncio.run(deep_search([_seed()], flaky_fetcher, config=ChaseConfig(max_depth=3)))
    assert isinstance(res, DeepSearchResult)
    assert res.articles == []


def test_config_from_registry_matches_yaml():
    cfg = ChaseConfig.from_registry()
    assert cfg.max_depth == 5
    assert cfg.total_budget_seconds == 120.0
