"""FINAL deterministic retrieval A/B — NO LLM, NO judge, NO API tokens. Network = NCBI only.

Four arms isolate each lever's contribution for the query that broke:
  A  baseline            (no F3, no F2)
  B  F3 only             (+ differential/etiology terms in the fetch)
  C  F2 only             (baseline fetch, then topicality gate)
  D  F3 + F2             (differential fetch, then topicality gate)   <- the shipped dev config
F2 is a post-fetch filter, so C/D apply the gate to the SAME fetched sets as A/B (clean isolation).
"""
import asyncio
import json
import time
from pathlib import Path

import app.services.data_fetcher as df
from app.services.differential_dx import differential_terms
from app.services.ranking import apply_topicality_gate

QUERY = "abdominal mass with Mets to spleen differential diagnosis"
QTYPE = "complex"
ENTITIES = ["abdominal mass", "splenic metastasis"]   # ddx -> subject anchor = all finding entities

FINDING_KW = ["splenic", "spleen", "metasta", "abdominal mass", "peritone"]
CANCER_KW = ["pancrea", "carcinoma", "adenocarcinoma", "lymphoma", "sarcoma", "melanoma", "hepatocellular"]
TREAT_KW = ["chemotherap", "treatment", "therapy", "trial", "efficacy", "survival", "regimen",
            "adjuvant", "neoadjuvant", "inhibitor", "dose", "randomi", "acupuncture"]


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
    add(getattr(fetched, "disease_data", None))
    add(getattr(fetched, "condition_data", None))
    add(getattr(fetched, "evidence_data", None))
    for c in getattr(fetched, "comorbidity_data", None) or []:
        add(c)
    return out


def flat_articles(fetched):
    seen, out = set(), []
    for b in _buckets(fetched):
        for a in b:
            t = (a.get("title") or "").strip()
            key = str(a.get("pmid") or "") or t.lower()
            if t and key not in seen:
                seen.add(key)
                out.append(a)
    return out


def has_any(t, kws):
    tl = t.lower()
    return any(k in tl for k in kws)


def score(articles):
    titles = [(a.get("title") or "") for a in articles]
    n = len(titles) or 1
    on_finding = sum(has_any(t, FINDING_KW) for t in titles)
    noise = sum(has_any(t, CANCER_KW) and has_any(t, TREAT_KW) and not has_any(t, FINDING_KW)
                for t in titles)
    return {
        "articles": len(titles),
        "on_finding_pct": round(100 * on_finding / n),
        "off_topic_noise_pct": round(100 * noise / n),
    }


def gate(articles):
    return apply_topicality_gate(articles, ENTITIES)


async def main():
    f3_terms = {"review": differential_terms(QUERY)}
    t0 = time.perf_counter()
    fetched_A = await df.fetch_data_for_query(QTYPE, ENTITIES, pubmed_expansion_terms=None)
    fetched_B = await df.fetch_data_for_query(QTYPE, ENTITIES, pubmed_expansion_terms=f3_terms)
    dt = round(time.perf_counter() - t0, 1)

    A = flat_articles(fetched_A)
    B = flat_articles(fetched_B)
    arms = {
        "A baseline":  score(A),
        "B F3 only":   score(B),
        "C F2 only":   score(gate(A)),
        "D F3+F2":     score(gate(B)),
    }
    print(f"\nfetch wall-clock: {dt}s   F3 terms: {f3_terms['review']}\n")
    print(f"{'arm':<14}{'articles':>9}{'on_finding%':>13}{'off_topic_noise%':>18}")
    for name, m in arms.items():
        print(f"{name:<14}{m['articles']:>9}{m['on_finding_pct']:>13}{m['off_topic_noise_pct']:>18}")

    print("\nD (F3+F2) surviving titles — what the model would actually synthesize from:")
    for a in gate(B):
        print("   -", (a.get("title") or "")[:110])

    out = {"query": QUERY, "arms": arms,
           "D_titles": [a.get("title") for a in gate(B)]}
    Path("/app/ab_final_result.json").write_text(json.dumps(out, indent=2))
    print("\nsaved -> ab_final_result.json")


asyncio.run(main())
