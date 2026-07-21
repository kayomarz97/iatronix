"""Aggregate the relevance factorial: per-combo off-topic rate + relevant-kept, across queries.

Haiku verdicts live in results/rel_raw/q{i}.json  ->  {"verdicts": {"<title>": true/false}}.
For each of the 8 combos (F=floor, S=synonyms, Q=sense), sum over queries the surfaced articles
judged relevant vs off-topic. Winner = lowest off-topic rate that keeps relevant-kept high (no thinning).
"""
import json
from pathlib import Path

RES = Path(__file__).resolve().parent / "results"
RAW = RES / "rel_raw"


def norm(s): return " ".join((s or "").lower().split())


def main():
    combos = json.loads((RES / "relevance_combos.json").read_text())
    inp = json.loads((RES / "relevance_judge_input.json").read_text())
    # verdicts per query index
    vmap_by_q = {}
    for i in range(1, len(inp) + 1):
        f = RAW / f"q{i}.json"
        vmap_by_q[i] = {norm(k): v for k, v in (json.loads(f.read_text()).get("verdicts") or {}).items()} if f.exists() else {}

    labels = [f"F{F}S{S}Q{Q}" for F in (0, 1) for S in (0, 1) for Q in (0, 1)]
    agg = {lab: {"surfaced": 0, "relevant": 0, "offtopic": 0, "unknown": 0} for lab in labels}

    for i, row in enumerate(combos, 1):
        vmap = vmap_by_q.get(i, {})
        for lab, titles in row["per_combo"].items():
            a = agg[lab]
            for t in titles:
                a["surfaced"] += 1
                v = vmap.get(norm(t))
                if v is True: a["relevant"] += 1
                elif v is False: a["offtopic"] += 1
                else: a["unknown"] += 1

    rows = []
    for lab in labels:
        a = agg[lab]
        judged = a["relevant"] + a["offtopic"]
        rows.append({
            "combo": lab,
            "floor": lab[1] == "1", "syn": lab[3] == "1", "sense": lab[5] == "1",
            "surfaced": a["surfaced"], "relevant": a["relevant"], "offtopic": a["offtopic"],
            "offtopic_rate": round(a["offtopic"] / judged, 3) if judged else None,
        })
    (RES / "relevance_precision.json").write_text(json.dumps(rows, indent=2))

    def human(lab):
        F, S, Q = lab[1] == "1", lab[3] == "1", lab[5] == "1"
        parts = [n for n, on in (("floor", F), ("syn", S), ("sense", Q)) if on]
        return "+".join(parts) if parts else "baseline (none)"

    print("| combo | levers | surfaced | relevant kept | off-topic | off-topic rate |")
    print("|---|---|--:|--:|--:|--:|")
    for r in sorted(rows, key=lambda x: (x["offtopic_rate"] is None, x["offtopic_rate"], -x["relevant"])):
        print(f"| {r['combo']} | {human(r['combo'])} | {r['surfaced']} | {r['relevant']} | {r['offtopic']} | {r['offtopic_rate']} |")
    base = next(r for r in rows if r["combo"] == "F0S0Q0")
    print(f"\nBaseline (no levers): off-topic rate {base['offtopic_rate']}, relevant kept {base['relevant']}")


if __name__ == "__main__":
    main()
