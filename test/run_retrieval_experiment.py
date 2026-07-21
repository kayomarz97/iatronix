"""
Phase A — Retrieval metrics: TYPED router vs FETCH-ALL (union of every strategy).

Deterministic, no LLM, no API cost. Exercises the REAL fetchers in
backend/app/services/data_fetcher.py with pubmed_expansion_terms=None so no
classifier / LLM is involved. Network = NCBI E-utilities only.

Outputs:
  test/results/phase_a_metrics.json   (machine-readable, feeds Phase B)
  test/results/phase_a_table.md       (human-readable summary)
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

# --- make the backend package importable --------------------------------------
ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

import app.services.data_fetcher as df  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"
RESULTS.mkdir(exist_ok=True)

ALL_TYPES = ["drug", "disease", "evidence", "procedure", "comparative", "complex"]

# (query_type, entities, label). entities are the SAME input handed to TYPED and
# to every strategy in FETCH-ALL — a faithful "run everything on this input" test.
QUERIES = [
    ("drug",        ["empagliflozin"],                                  "drug: empagliflozin MoA"),
    ("disease",     ["chronic kidney disease"],                         "disease: CKD staging"),
    ("disease",     ["chronic fatigue", "night sweats"],                "symptom-only: fatigue+night sweats"),
    ("evidence",    ["SGLT2 inhibitors", "heart failure"],              "evidence: SGLT2i in HF"),
    ("procedure",   ["central venous catheter insertion"],              "procedure: CVC insertion"),
    ("comparative", ["warfarin", "apixaban"],                           "comparative: warfarin vs apixaban"),
    ("complex",     ["", "chronic kidney disease", "type 2 diabetes"],  "complex: DOC for CKD+T2DM+HF"),
    ("complex",     ["metformin", "chronic kidney disease"],            "complex: metformin in CKD+HF"),
    ("evidence",    ["amiodarone", "atrial fibrillation"],              "drug-in-disease: amiodarone in AF"),
    ("disease",     ["capital of France"],                              "non-medical: capital of France"),
]

# --- NCBI esearch call counter (wrap the primitive all searches funnel through) -
_ESEARCH_COUNT = {"n": 0}
_orig_esearch = df._pubmed_esearch


async def _counting_esearch(*args, **kwargs):
    _ESEARCH_COUNT["n"] += 1
    return await _orig_esearch(*args, **kwargs)


df._pubmed_esearch = _counting_esearch


def collect_buckets(fetched):
    """Return the list of per-source abstract BUCKETS (each a list of dicts).

    The real pipeline caps every bucket independently at ~3000 chars, so cap-waste
    must be measured per-bucket, not on a merged pool. Full 'abstract' text is kept
    because _cap_abstracts() budgets on len(a['abstract'])."""
    buckets = []

    def add(obj):
        if obj is None:
            return
        for attr in ("guideline_abstracts", "systematic_review_abstracts",
                     "clinical_trial_abstracts", "practice_guideline_abstracts"):
            raw = getattr(obj, attr, None) or []
            clean = [{"pmid": str(a.get("pmid") or ""),
                      "title": (a.get("title") or "").strip(),
                      "abstract": a.get("abstract") or "",
                      "year": a.get("year") or 0}
                     for a in raw if isinstance(a, dict)]
            if clean:
                buckets.append(clean)

    add(getattr(fetched, "drug_data", None))
    add(getattr(fetched, "disease_data", None))
    add(getattr(fetched, "condition_data", None))
    add(getattr(fetched, "procedure_data", None))
    add(getattr(fetched, "evidence_data", None))
    add(getattr(fetched, "comparative_evidence", None))
    for c in getattr(fetched, "comorbidity_data", None) or []:
        add(c)
    for d in getattr(fetched, "comparative_drug_data", None) or []:
        add(d)
    return buckets


def collect_abstracts(fetched) -> list[dict]:
    """Flat list of every abstract dict (for total/unique/relevance)."""
    return [a for b in collect_buckets(fetched) for a in b]


def metrics_for(buckets, latency_s: float, esearch_calls: int, tier="unknown", fallback=None) -> dict:
    flat = [a for b in buckets for a in b]
    total = len(flat)
    pmids = [a["pmid"] for a in flat if a["pmid"]]
    unique = len(set(pmids))
    # cap-waste: sum over buckets of (fetched - survives the real 3000-char cap).
    # This mirrors how the pipeline actually trims each bucket before the prompt.
    cap_kept = sum(len(df._cap_abstracts(b, 3000)) for b in buckets)
    kept = cap_kept
    any_ev = bool(unique)
    return {
        "latency_s": round(latency_s, 2),
        "esearch_calls": esearch_calls,
        "total_abstracts": total,
        "unique_pmids": unique,
        "duplication_ratio": round(total / unique, 2) if unique else 0.0,
        "cap_kept": kept,
        "cap_waste": max(total - kept, 0),
        "empty_fetch": not any_ev,
        "evidence_tier": tier,
        "fallback_to_llm": fallback,
    }


async def run_typed(qtype, entities):
    _ESEARCH_COUNT["n"] = 0
    t0 = time.perf_counter()
    fetched = await df.fetch_data_for_query(qtype, entities, pubmed_expansion_terms=None)
    dt = time.perf_counter() - t0
    buckets = collect_buckets(fetched)
    m = metrics_for(buckets, dt, _ESEARCH_COUNT["n"],
                    tier=getattr(fetched, "evidence_tier", "unknown"),
                    fallback=getattr(fetched, "fallback_to_llm", None))
    return m, [a for b in buckets for a in b]


async def run_fetch_all(entities):
    _ESEARCH_COUNT["n"] = 0
    t0 = time.perf_counter()
    # steelman: run every strategy concurrently (best-case latency for FETCH-ALL)
    results = await asyncio.gather(
        *[df.fetch_data_for_query(t, entities, pubmed_expansion_terms=None) for t in ALL_TYPES],
        return_exceptions=True,
    )
    dt = time.perf_counter() - t0
    buckets, tier = [], "unknown"
    for r in results:
        if isinstance(r, Exception):
            continue
        buckets.extend(collect_buckets(r))
        if getattr(r, "evidence_tier", "unknown") not in ("unknown", None):
            tier = r.evidence_tier
    m = metrics_for(buckets, dt, _ESEARCH_COUNT["n"], tier=tier, fallback=None)
    return m, [a for b in buckets for a in b]


async def main():
    rows = []
    b_input = []  # feeds Phase B (Haiku relevance judge)
    for qtype, entities, label in QUERIES:
        print(f"\n=== {label}  (type={qtype}, entities={entities})", flush=True)
        try:
            typed_m, typed_absts = await run_typed(qtype, entities)
        except Exception as e:
            typed_m, typed_absts = {"error": str(e)}, []
        print("  TYPED    :", typed_m, flush=True)
        try:
            all_m, all_absts = await run_fetch_all(entities)
        except Exception as e:
            all_m, all_absts = {"error": str(e)}, []
        print("  FETCH-ALL:", all_m, flush=True)

        rows.append({"label": label, "query_type": qtype, "entities": entities,
                     "typed": typed_m, "fetch_all": all_m})
        # unique titles for the relevance judge (cap 15 each to keep prompts small)
        def uniq_titles(absts):
            seen, out = set(), []
            for a in absts:
                t = a["title"]
                if t and t not in seen:
                    seen.add(t); out.append(t)
            return out[:15]
        b_input.append({"label": label, "query": label.split(":", 1)[1].strip(),
                        "typed_titles": uniq_titles(typed_absts),
                        "fetch_all_titles": uniq_titles(all_absts)})

    (RESULTS / "phase_a_metrics.json").write_text(json.dumps(rows, indent=2))
    (RESULTS / "phase_b_input.json").write_text(json.dumps(b_input, indent=2))

    # human-readable table
    lines = ["# Phase A — TYPED vs FETCH-ALL (retrieval metrics)\n",
             "| Query | Cond | lat(s) | esearch | total | uniq | dup× | capKept | capWaste | empty | tier |",
             "|---|---|--:|--:|--:|--:|--:|--:|--:|:-:|:--|"]
    for r in rows:
        for cond in ("typed", "fetch_all"):
            m = r[cond]
            if "error" in m:
                lines.append(f"| {r['label']} | {cond} | ERR: {m['error'][:40]} |||||||||")
                continue
            lines.append(
                f"| {r['label']} | {cond} | {m['latency_s']} | {m['esearch_calls']} | "
                f"{m['total_abstracts']} | {m['unique_pmids']} | {m['duplication_ratio']} | "
                f"{m['cap_kept']} | {m['cap_waste']} | {'Y' if m['empty_fetch'] else '·'} | {m['evidence_tier']} |")
    (RESULTS / "phase_a_table.md").write_text("\n".join(lines) + "\n")
    print("\nWROTE:", RESULTS / "phase_a_metrics.json", "and phase_a_table.md")


if __name__ == "__main__":
    asyncio.run(main())
