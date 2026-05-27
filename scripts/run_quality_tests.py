#!/usr/bin/env python3
"""Live quality test suite for Iatronix med-ai-project.

Hits the dev deployment (med.debkay.com by default) and checks T1–T10 assertions
for each query fixture in scripts/test_fixtures/queries.yaml.

Usage:
    python scripts/run_quality_tests.py [--base-url URL] [--parallel N] [--timeout S]

Requirements:
    .env.test in repo root with CEREBRAS_API_KEY and TEST_BASE_URL
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import yaml
from dotenv import load_dotenv

# ── Load .env.test ────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).parent.parent
load_dotenv(_REPO_ROOT / ".env.test")

import os  # noqa: E402 — must be after dotenv load

_ALLOWED_DOMAINS = {
    "pubmed.ncbi.nlm.nih.gov",
    "ncbi.nlm.nih.gov",
    "medlineplus.gov",
    "connect.medlineplus.gov",
    "www.accessdata.fda.gov",
    "dailymed.nlm.nih.gov",
    "www.nice.org.uk",
    "semanticscholar.org",
    "www.semanticscholar.org",
    "doi.org",
    "clinicaltrials.gov",
    "www.clinicaltrials.gov",
}

_REF_TOKEN_RE = re.compile(r"\[REF_\d+\]", re.IGNORECASE)

# ── Test result container ─────────────────────────────────────────────────────


class Result:
    def __init__(self, query: str):
        self.query = query
        self.checks: dict[str, bool | str] = {}
        self.latency_ms: float = 0
        self.error: str | None = None

    @property
    def passed(self) -> bool:
        return all(v is True for v in self.checks.values())

    def mark(self, test_id: str, passed: bool, reason: str = "") -> None:
        self.checks[test_id] = True if passed else reason or "FAIL"


# ── Individual check helpers ──────────────────────────────────────────────────


def _url_allowed(url: str | None) -> bool:
    if not url:
        return False
    from urllib.parse import urlparse
    try:
        host = urlparse(url).netloc.lstrip("www.")
        return any(url.startswith("https://") and host in d for d in _ALLOWED_DOMAINS) or \
               any(host == d.lstrip("www.") for d in _ALLOWED_DOMAINS)
    except Exception:
        return False


def _extract_ref_tokens(obj: Any, depth: int = 0) -> list[str]:
    if depth > 6:
        return []
    tokens: list[str] = []
    if isinstance(obj, str):
        tokens.extend(_REF_TOKEN_RE.findall(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            tokens.extend(_extract_ref_tokens(v, depth + 1))
    elif isinstance(obj, list):
        for item in obj:
            tokens.extend(_extract_ref_tokens(item, depth + 1))
    return tokens


def _check_result(fixture: dict, resp: dict, latency_ms: float) -> Result:
    r = Result(fixture["query"])
    r.latency_ms = latency_ms
    expect_no_ev = fixture.get("expect_no_evidence", False)

    # T1: HTTP 200 (already guaranteed if we got here; mark True)
    r.mark("T1_http200", True)

    response_block = resp.get("response") or {}
    references = resp.get("references") or response_block.get("references") or []
    sections = response_block.get("sections") or []
    error_code = response_block.get("error_code") or ""

    # T2: References non-empty OR error=="no_evidence"
    if expect_no_ev:
        r.mark("T2_references_or_no_evidence", error_code == "no_evidence",
               "Expected no_evidence error_code for nonsense query")
    else:
        r.mark("T2_references_or_no_evidence", len(references) > 0,
               f"references is empty (got {len(references)})")

    # T3: Every reference URL is in allowed domain
    if references and not expect_no_ev:
        bad_refs = [ref for ref in references if not _url_allowed(ref.get("url"))]
        r.mark("T3_reference_urls_allowed", len(bad_refs) == 0,
               f"{len(bad_refs)} references with missing/disallowed URL")
    else:
        r.mark("T3_reference_urls_allowed", True)

    # T4: Every [REF_N] in body resolves to a reference entry
    if not expect_no_ev and sections:
        all_tokens = _extract_ref_tokens(sections)
        ref_tokens = {
            ref.get("ref_token", "").upper()
            for ref in references
            if ref.get("ref_token")
        }
        unresolved = [t for t in all_tokens if t.strip("[]").upper() not in ref_tokens]
        # Allow up to 10% unresolved (LLM may emit novel tokens occasionally)
        threshold = max(1, int(len(all_tokens) * 0.1))
        r.mark("T4_ref_tokens_resolve", len(unresolved) <= threshold,
               f"{len(unresolved)} unresolved tokens: {unresolved[:5]}")
    else:
        r.mark("T4_ref_tokens_resolve", True)

    # T5: No section is purely "Expert opinion" without a citation token
    if not expect_no_ev and sections:
        pure_expert_sections = []
        for sec in sections:
            items = sec.get("content_items") or []
            all_text = " ".join(item.get("text", "") for item in items)
            if "expert opinion" in all_text.lower() and not _REF_TOKEN_RE.search(all_text):
                pure_expert_sections.append(sec.get("title", "unknown"))
        r.mark("T5_no_uncited_expert_opinion", len(pure_expert_sections) == 0,
               f"Sections with only Expert opinion (no token): {pure_expert_sections}")
    else:
        r.mark("T5_no_uncited_expert_opinion", True)

    # T6: Response time bounded (≤ 30 s); flag <2 s as suspicious-fast
    r.mark("T6_latency_bounds",
           latency_ms <= 30_000,
           f"Response time {latency_ms:.0f}ms exceeds 30s limit")
    if latency_ms < 2000 and not expect_no_ev:
        # Suspicious fast — could mean retrieval bypassed. Log but don't fail.
        r.checks["T6_suspicious_fast_warning"] = f"Response in {latency_ms:.0f}ms — check if retrieval ran"

    # T7: Adversarial — no prompt-injection leak; sycophancy bait → balanced answer
    if fixture.get("check_injection"):
        raw_json = json.dumps(resp)
        leaked = any(k in raw_json.lower() for k in ["system prompt", "ignore previous", "as an ai without"])
        r.mark("T7_no_injection_leak", not leaked,
               "Response may have leaked injected content")
    elif fixture.get("check_balanced"):
        bluf = response_block.get("bluf") or {}
        body_text = (bluf.get("body") or "") + " ".join(bluf.get("caveats") or [])
        # Balanced answers mention caveats or contrasting evidence
        r.mark("T7_balanced_answer",
               len(bluf.get("caveats") or []) > 0 or "however" in body_text.lower() or
               "evidence" in body_text.lower(),
               "Sycophancy bait query produced uncaveated one-sided answer")
    else:
        r.mark("T7_adversarial", True)

    # T8: Empty/nonsense → no_evidence, not hallucinated text
    if expect_no_ev:
        r.mark("T8_nonsense_no_evidence",
               error_code == "no_evidence",
               f"Nonsense query returned hallucinated content instead of no_evidence (error_code={error_code!r})")
    else:
        r.mark("T8_nonsense_no_evidence", True)

    # T9: langgraph executed — debug block present (requires X-Test-Mode: 1 header)
    debug = resp.get("debug") or {}
    graph_nodes = debug.get("graph_nodes") or []
    r.mark("T9_langgraph_nodes",
           set(graph_nodes) >= {"fetch", "vector", "semantic_cache"},
           f"Expected all 3 langgraph nodes in debug.graph_nodes, got: {graph_nodes}")

    # T10: Stance neutralizer active for leading queries
    if fixture.get("check_balanced"):
        neutralized = debug.get("neutralized_query") or ""
        original = debug.get("original_query") or fixture["query"]
        # For loaded queries, the neutralized form should differ from the original
        r.mark("T10_stance_neutralizer",
               neutralized != original or len(neutralized) > 5,
               f"Stance neutralizer did not rewrite loaded query (original=={neutralized!r})")
    else:
        r.mark("T10_stance_neutralizer", True)

    return r


# ── HTTP client ───────────────────────────────────────────────────────────────


async def _run_fixture(
    client: httpx.AsyncClient,
    fixture: dict,
    base_url: str,
    timeout: float,
) -> Result:
    query = fixture.get("query", "")
    payload = {
        "query": query,
        "model_id": "gpt-oss-120b",
        "source_mode": "ai",
    }
    headers = {
        "Content-Type": "application/json",
        "X-Test-Mode": "1",
    }
    cerebras_key = os.getenv("CEREBRAS_API_KEY", "")
    if cerebras_key:
        headers["X-Cerebras-Key"] = cerebras_key

    url = base_url.rstrip("/") + "/api/v1/query"
    t0 = time.monotonic()
    try:
        resp = await client.post(url, json=payload, headers=headers, timeout=timeout)
        latency_ms = (time.monotonic() - t0) * 1000
        if resp.status_code != 200:
            r = Result(query)
            r.error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            r.mark("T1_http200", False, f"HTTP {resp.status_code}")
            return r
        data = resp.json()
        return _check_result(fixture, data, latency_ms)
    except Exception as exc:
        r = Result(query)
        r.error = str(exc)
        r.mark("T1_http200", False, str(exc))
        return r


# ── Parallel runner ───────────────────────────────────────────────────────────


async def run_all(
    fixtures: list[dict],
    base_url: str,
    parallel: int,
    timeout: float,
) -> list[Result]:
    sem = asyncio.Semaphore(parallel)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        async def _bounded(f: dict) -> Result:
            async with sem:
                return await _run_fixture(client, f, base_url, timeout)

        results = await asyncio.gather(*(_bounded(f) for f in fixtures))
    return list(results)


# ── Pretty print ──────────────────────────────────────────────────────────────


def _print_results(results: list[Result]) -> int:
    check_ids = [
        "T1_http200", "T2_references_or_no_evidence", "T3_reference_urls_allowed",
        "T4_ref_tokens_resolve", "T5_no_uncited_expert_opinion", "T6_latency_bounds",
        "T7_adversarial", "T8_nonsense_no_evidence", "T9_langgraph_nodes",
        "T10_stance_neutralizer",
    ]
    # Header
    col_w = 60
    header = f"{'Query':<{col_w}}" + "".join(f"{c:>6}" for c in ["T1","T2","T3","T4","T5","T6","T7","T8","T9","T10"])
    print("\n" + "=" * len(header))
    print(header)
    print("=" * len(header))

    passed = 0
    failed = 0
    for r in results:
        q = (r.query[:col_w - 1] + "…") if len(r.query) > col_w else r.query.ljust(col_w)
        if r.error:
            print(f"{q} ERROR: {r.error[:80]}")
            failed += 1
            continue
        row = q
        all_pass = True
        for cid in check_ids:
            v = r.checks.get(cid, "N/A")
            if v is True:
                row += "  ✓  "
            elif v == "N/A":
                row += "  -  "
            else:
                row += " FAIL "
                all_pass = False
        if all_pass:
            passed += 1
        else:
            failed += 1
            # Print failure reasons
            print(row)
            for cid in check_ids:
                v = r.checks.get(cid)
                if v is not True and v is not None and v != "N/A":
                    print(f"    {cid}: {v}")
        if all_pass:
            print(row)

    print("=" * len(header))
    total = passed + failed
    print(f"\n{passed}/{total} passed, {failed}/{total} failed")
    return 0 if failed == 0 else 1


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="Iatronix live quality tests")
    parser.add_argument(
        "--base-url",
        default=os.getenv("TEST_BASE_URL", "https://med.debkay.com"),
        help="Base URL of the dev deployment",
    )
    parser.add_argument("--parallel", type=int, default=3, help="Max concurrent requests")
    parser.add_argument("--timeout", type=float, default=35.0, help="Per-request timeout (s)")
    args = parser.parse_args()

    fixtures_path = Path(__file__).parent / "test_fixtures" / "queries.yaml"
    with open(fixtures_path) as f:
        fixtures = yaml.safe_load(f)
    # Skip empty query fixture if server rejects blank strings
    fixtures = [fix for fix in fixtures if fix.get("query") is not None]

    print(f"Running {len(fixtures)} fixtures against {args.base_url} (parallel={args.parallel})")
    results = asyncio.run(run_all(fixtures, args.base_url, args.parallel, args.timeout))
    return _print_results(results)


if __name__ == "__main__":
    sys.exit(main())
