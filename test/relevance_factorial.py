"""
Relevance precision — 2^3 factorial test of the 3 levers.

Levers (independent flags):
  F = relevance floor (drop entity-absent articles, keep >= min_keep)
  S = synonym-aware matching (paracetamol <-> acetaminophen ...)
  Q = query-sense framing (add adverse-sense PubMed terms for causation queries)

Niche queries across all types (two loosely-related things → few on-topic hits → off-topic
keyword matches surface, the paracetamol/fever pattern). For each query we do ONE base fetch +
(for causation queries) one sense fetch, then for each of the 8 combos compute the "surfaced"
top-K set (rank + floor + synonyms). A Haiku judge (Claude Code subscription) rates each unique
surfaced article once per query; verdicts are reused across combos.

Outputs: results/relevance_judge_input.json (per-query union titles + per-combo surfaced titles),
         results/relevance_combos.json (per-combo surfaced sets, for aggregation).
"""
import asyncio, json, sys, itertools
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import app.services.data_fetcher as df                 # noqa: E402
from app.services.ranking import rank_article_list     # noqa: E402
from app.services.query_sense import sense_terms        # noqa: E402

RES = Path(__file__).resolve().parent / "results"
RES.mkdir(exist_ok=True)
K = 8            # surfaced top-K (approx what reaches the prompt)
MIN_KEEP = 3

# (label, query_type, fetch_entities, relevance_entities(anchor), query_text)
QUERIES = [
    ("evidence: paracetamol→fever",     "evidence",   ["paracetamol", "fever"],          ["paracetamol"],          "does paracetamol cause fever"),
    ("evidence: metformin→tinnitus",    "evidence",   ["metformin", "tinnitus"],         ["metformin"],            "does metformin cause tinnitus"),
    ("evidence: omeprazole→hypoNa",     "evidence",   ["omeprazole", "hyponatremia"],    ["omeprazole"],           "does omeprazole cause hyponatremia"),
    ("evidence: amiodarone→hairloss",   "evidence",   ["amiodarone", "hair loss"],       ["amiodarone"],           "does amiodarone cause hair loss"),
    ("disease: night sweats in AS",     "disease",    ["ankylosing spondylitis"],        ["ankylosing spondylitis"],"night sweats in ankylosing spondylitis"),
    ("procedure: thoracentesis+dialysis","procedure", ["thoracentesis"],                 ["thoracentesis"],        "thoracentesis in a patient on dialysis"),
    ("comparative: ibuprofen vs naproxen","comparative",["ibuprofen", "naproxen"],       ["ibuprofen", "naproxen"],"ibuprofen vs naproxen for tension headache"),
    ("complex: allopurinol+epilepsy",   "complex",    ["allopurinol", "epilepsy"],       ["allopurinol"],          "allopurinol in a patient with epilepsy"),
]


def _collect(fetched) -> list[dict]:
    out = []
    def add(o):
        if o is None: return
        for attr in ("guideline_abstracts","systematic_review_abstracts","clinical_trial_abstracts","practice_guideline_abstracts"):
            for a in getattr(o, attr, None) or []:
                if isinstance(a, dict) and (a.get("title") or "").strip():
                    out.append({"title": a["title"].strip(), "pmid": str(a.get("pmid") or ""),
                                "abstract": a.get("abstract") or "", "year": a.get("year") or 0})
    for name in ("drug_data","disease_data","condition_data","procedure_data","evidence_data","comparative_evidence"):
        add(getattr(fetched, name, None))
    for c in getattr(fetched, "comorbidity_data", None) or []: add(c)
    for d in getattr(fetched, "comparative_drug_data", None) or []: add(d)
    return out


def _dedup(pool):
    seen, out = set(), []
    for a in pool:
        key = a["pmid"] or a["title"].lower()
        if key and key not in seen:
            seen.add(key); out.append(a)
    return out


def _surfaced(pool, rel_entities, query, *, floor, syn):
    ranked = rank_article_list(pool, rel_entities, query, use_synonyms=syn, apply_floor=floor, min_keep=MIN_KEEP)
    return [a["title"] for a in ranked[:K]]


async def main():
    judge_input, combos_out = [], []
    COMBOS = list(itertools.product([0, 1], repeat=3))  # (F, S, Q)
    for label, qtype, fetch_ents, rel_ents, query in QUERIES:
        print(f"\n=== {label}", flush=True)
        base = await df.fetch_data_for_query(qtype, fetch_ents, pubmed_expansion_terms=None)
        base_pool = _dedup(_collect(base))
        st = sense_terms(query)
        if st:
            sense_extra = await df.fetch_evidence_data(query, extra_pubmed_terms=st)
            sense_pool = _dedup(base_pool + _collect_ev(sense_extra))
        else:
            sense_pool = base_pool
        print(f"  base pool={len(base_pool)}  sense pool={len(sense_pool)}  sense_terms={bool(st)}", flush=True)

        per_combo = {}
        union_titles = set()
        for (F, S, Q) in COMBOS:
            pool = sense_pool if Q else base_pool
            surf = _surfaced(pool, rel_ents, query, floor=bool(F), syn=bool(S))
            per_combo[f"F{F}S{S}Q{Q}"] = surf
            union_titles.update(surf)
        combos_out.append({"label": label, "query": query, "per_combo": per_combo})
        judge_input.append({"label": label, "query": query, "titles": sorted(union_titles)})

    (RES / "relevance_combos.json").write_text(json.dumps(combos_out, indent=2))
    (RES / "relevance_judge_input.json").write_text(json.dumps(judge_input, indent=2))
    print("\nWROTE relevance_combos.json / relevance_judge_input.json  (combos:", len(COMBOS), ")")


def _collect_ev(ev):
    out = []
    for attr in ("guideline_abstracts","systematic_review_abstracts","clinical_trial_abstracts"):
        for a in getattr(ev, attr, None) or []:
            if isinstance(a, dict) and (a.get("title") or "").strip():
                out.append({"title": a["title"].strip(), "pmid": str(a.get("pmid") or ""),
                            "abstract": a.get("abstract") or "", "year": a.get("year") or 0})
    return out


if __name__ == "__main__":
    asyncio.run(main())
