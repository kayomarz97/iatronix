"""
Phase B aggregation — compute retrieval PRECISION for TYPED vs FETCH-ALL.

Each Haiku judge (spawned via the Claude Code subscription, model="haiku") writes a
verdict file to test/results/phase_b_raw/<label>.json of the form:
    {"verdicts": {"<exact title>": true/false, ...}}   (true = relevant to the query)

This script joins those verdicts back to phase_b_input.json and computes, per query:
    precision = (# retrieved titles judged relevant) / (# retrieved titles)
for the TYPED title set and the FETCH-ALL title set separately.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RES = HERE / "results"
RAW = RES / "phase_b_raw"


def norm(s: str) -> str:
    return " ".join((s or "").lower().split())


def precision(titles, verdict_map):
    titles = [t for t in titles if t]
    if not titles:
        return None, 0, 0
    rel = sum(1 for t in titles if verdict_map.get(norm(t)) is True)
    return round(rel / len(titles), 3), rel, len(titles)


def main():
    inp = json.loads((RES / "phase_b_input.json").read_text())
    rows = []
    for i, item in enumerate(inp, start=1):
        label = item["label"]
        vf = RAW / f"q{i}.json"
        if not vf.exists():
            rows.append({"label": label, "status": "no_verdict"})
            continue
        raw = json.loads(vf.read_text())
        vmap = {norm(k): v for k, v in (raw.get("verdicts") or {}).items()}
        tp, tr, tn = precision(item["typed_titles"], vmap)
        ap, ar, an = precision(item["fetch_all_titles"], vmap)
        rows.append({"label": label,
                     "typed_precision": tp, "typed_relevant": tr, "typed_n": tn,
                     "fetch_all_precision": ap, "fetch_all_relevant": ar, "fetch_all_n": an})
    (RES / "phase_b_precision.json").write_text(json.dumps(rows, indent=2))

    print("| Query | typed prec (rel/n) | fetch-all prec (rel/n) |")
    print("|---|--:|--:|")
    for r in rows:
        if r.get("status") == "no_verdict":
            print(f"| {r['label']} | — | — |")
            continue
        print(f"| {r['label']} | {r['typed_precision']} ({r['typed_relevant']}/{r['typed_n']}) "
              f"| {r['fetch_all_precision']} ({r['fetch_all_relevant']}/{r['fetch_all_n']}) |")
    # aggregate (weighted by n)
    tot_tr = sum(r.get("typed_relevant", 0) for r in rows if "typed_n" in r)
    tot_tn = sum(r.get("typed_n", 0) for r in rows if "typed_n" in r)
    tot_ar = sum(r.get("fetch_all_relevant", 0) for r in rows if "fetch_all_n" in r)
    tot_an = sum(r.get("fetch_all_n", 0) for r in rows if "fetch_all_n" in r)
    if tot_tn and tot_an:
        print(f"\nOVERALL micro-precision: TYPED={tot_tr/tot_tn:.3f} ({tot_tr}/{tot_tn}) "
              f"| FETCH-ALL={tot_ar/tot_an:.3f} ({tot_ar}/{tot_an})")


if __name__ == "__main__":
    main()
