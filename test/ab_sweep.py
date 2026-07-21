"""Broad ON/OFF retrieval sweep — NO LLM, NO judge, NO API tokens. Network = NCBI only.

Checks the fixes across query shapes (simple drug/disease -> layered comorbidity -> differential).
OFF = baseline fetch. ON = (+F3 differential terms if ddx) then F2 topicality gate.
The point: confirm F2/F3 HELP differential queries WITHOUT over-filtering normal ones
(the danger signal is `gate_empties` — the gate blanks a query that had evidence).
"""
import asyncio
import json
import time
from pathlib import Path

import app.services.data_fetcher as df
from app.services.differential_dx import differential_terms, is_differential_query
from app.services.ranking import apply_topicality_gate, _subject_tokens, _article_on_subject

# (label, query_type, entities, natural-language query)
QUERIES = [
    ("simple drug MoA",      "drug",        ["empagliflozin"],                                  "empagliflozin mechanism of action"),
    ("simple dosing",        "evidence",    ["metformin", "chronic kidney disease"],            "metformin dose in chronic kidney disease"),
    ("simple disease",       "disease",     ["chronic kidney disease"],                         "chronic kidney disease staging"),
    ("comparative",          "comparative", ["warfarin", "apixaban"],                           "warfarin vs apixaban in atrial fibrillation"),
    ("causation/side-effect","evidence",    ["metformin", "lactic acidosis"],                   "does metformin cause lactic acidosis"),
    ("layered comorbidity",  "complex",     ["chronic kidney disease", "type 2 diabetes", "heart failure"], "drug of choice for CKD with T2DM and heart failure"),
    ("ddx simple",           "disease",     ["splenomegaly"],                                   "causes of splenomegaly"),
    ("ddx layered (orig)",   "complex",     ["abdominal mass", "splenic metastasis"],           "abdominal mass with Mets to spleen differential diagnosis"),
    ("ddx anemia",           "disease",     ["microcytic anemia"],                              "differential diagnosis of microcytic anemia"),
]


def subject_anchor(entities, qtype, query):
    if qtype == "comparative" or is_differential_query(query):
        return list(entities or [])
    return entities[:1] if entities else []


def _buckets(fetched):
    out = []
    def add(obj):
        if obj is None:
            return
        for attr in ("guideline_abstracts", "systematic_review_abstracts",
                     "clinical_trial_abstracts", "practice_guideline_abstracts"):
            raw = [a for a in (getattr(obj, attr, None) or []) if isinstance(a, dict)]
            if raw:
                out.append(raw)
    for attr in ("drug_data", "disease_data", "condition_data", "procedure_data",
                 "evidence_data", "comparative_evidence"):
        add(getattr(fetched, attr, None))
    for c in getattr(fetched, "comorbidity_data", None) or []:
        add(c)
    for d in getattr(fetched, "comparative_drug_data", None) or []:
        add(d)
    return out


def flat(fetched):
    seen, out = set(), []
    for b in _buckets(fetched):
        for a in b:
            t = (a.get("title") or "").strip()
            key = str(a.get("pmid") or "") or t.lower()
            if t and key not in seen:
                seen.add(key); out.append(a)
    return out


def on_subject_pct(articles, anchor):
    toks = _subject_tokens(anchor)
    if not toks or not articles:
        return None
    hit = sum(_article_on_subject(a, toks) for a in articles)
    return round(100 * hit / len(articles))


async def fetch(qtype, entities, expansion):
    try:
        return flat(await df.fetch_data_for_query(qtype, entities, pubmed_expansion_terms=expansion))
    except Exception as e:
        return {"__error__": str(e)}


async def main():
    rows = []
    for label, qtype, entities, query in QUERIES:
        ddx = is_differential_query(query)
        anchor = subject_anchor(entities, qtype, query)
        base = await fetch(qtype, entities, None)
        if isinstance(base, dict):
            rows.append({"label": label, "error": base["__error__"]}); continue
        # ON fetch: add F3 terms only when ddx fires
        f3 = differential_terms(query) if ddx else []
        on_fetch = await fetch(qtype, entities, {"review": f3}) if f3 else base
        if isinstance(on_fetch, dict):
            rows.append({"label": label, "error": on_fetch["__error__"]}); continue
        on_gated = apply_topicality_gate(on_fetch, anchor)
        n_off, n_on = len(base), len(on_gated)
        rows.append({
            "label": label, "ddx_fires": ddx, "anchor": anchor,
            "n_off": n_off, "n_on": n_on,
            "retained_pct": round(100 * n_on / n_off) if n_off else 0,
            "onsubj_off_pct": on_subject_pct(base, anchor),
            "onsubj_on_pct": on_subject_pct(on_gated, anchor),
            "GATE_EMPTIES": (n_on == 0 and n_off > 0),
        })

    print(f"\n{'query':<24}{'ddx':>5}{'off':>5}{'on':>5}{'ret%':>6}{'onsubjOFF%':>12}{'onsubjON%':>11}  flag")
    for r in rows:
        if "error" in r:
            print(f"{r['label']:<24}  ERROR: {r['error'][:50]}"); continue
        flag = "  <-- GATE EMPTIES!" if r["GATE_EMPTIES"] else ("  (thin)" if r["n_on"] and r["n_on"] < 3 else "")
        print(f"{r['label']:<24}{str(r['ddx_fires']):>5}{r['n_off']:>5}{r['n_on']:>5}{r['retained_pct']:>6}"
              f"{str(r['onsubj_off_pct']):>12}{str(r['onsubj_on_pct']):>11}{flag}")

    empties = [r['label'] for r in rows if r.get('GATE_EMPTIES')]
    print(f"\nSUMMARY: {len(empties)} query(ies) blanked by the gate: {empties or 'NONE'}")
    Path("/app/ab_sweep_result.json").write_text(json.dumps(rows, indent=2))
    print("saved -> ab_sweep_result.json")


asyncio.run(main())
