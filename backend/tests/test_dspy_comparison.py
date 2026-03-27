"""
DSPy Comparison Test
Runs 5 test queries against:
  - Port 8201: DSPY_ENABLED=false  (baseline)
  - Port 8202: DSPY_ENABLED=true   (DSPy adaptive)

Measures: tokens used, time taken, sections returned, bluf presence.
Output: comparison table as specified in spicy-chasing-summit.md

Run:
  python3 tests/test_dspy_comparison.py
"""
import time
import json
import urllib.request
import urllib.error
from typing import Any

# ── Config ────────────────────────────────────────────────────────────────────
BASE_NODSPY = "http://localhost:8201"
BASE_DSPY   = "http://localhost:8202"
API_KEY     = "iatx.iwn5urz42y58.4JOEB5N_U1ZJPqBke1UrNF1VY8yYF5e-MLPRyanAnQ8"

TEST_QUERIES = [
    # (label, query, query_type)
    ("Drug – focused dosing",       "dose of metformin in CKD stage 3",                    "drug"),
    ("Drug – mechanism",            "aspirin mechanism of action",                          "drug"),
    ("Disease – full review",       "pulmonary hypertension treatment",                     "disease"),
    ("Comparative – hybrid",        "warfarin vs apixaban in atrial fibrillation with CKD", "comparative"),
    ("Evidence – statins",          "evidence for statins in primary prevention",            None),
]

# ── Request helper ─────────────────────────────────────────────────────────────
def query(base: str, q: str, qtype: str | None) -> tuple[dict, float]:
    payload = json.dumps({"query": q, **({"query_type": qtype} if qtype else {})}).encode()
    req = urllib.request.Request(
        f"{base}/api/v1/query",
        data=payload,
        headers={"Content-Type": "application/json", "X-API-Key": API_KEY},
        method="POST",
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = json.loads(e.read())
    elapsed = time.perf_counter() - t0
    return body, elapsed


def count_sections(body: dict) -> int:
    """Count non-null top-level fields in response (sections returned)."""
    resp = body.get("response") or {}
    if isinstance(resp, dict):
        # AdaptiveResponse: sections list
        secs = resp.get("sections")
        if isinstance(secs, list):
            return len(secs)
        # Structured response: count non-null, non-meta fields
        skip = {"query_type", "model_used", "cache_hit", "response_focus", "bluf", "depth",
                "references", "citations", "safety_flags", "error"}
        return sum(1 for k, v in resp.items() if k not in skip and v is not None and v != [] and v != {})
    return 0


def get_tokens(body: dict) -> int:
    """Extract output token count from usage metadata."""
    usage = body.get("usage") or body.get("metadata") or {}
    return (
        usage.get("output_tokens")
        or usage.get("completion_tokens")
        or usage.get("total_tokens")
        or 0
    )


def has_bluf(body: dict) -> bool:
    resp = body.get("response") or {}
    if isinstance(resp, dict):
        return bool(resp.get("bluf"))
    return False


def get_query_type(body: dict) -> str:
    return body.get("query_type") or (body.get("response") or {}).get("query_type") or "?"


# ── Run comparison ─────────────────────────────────────────────────────────────
print("\n" + "="*100)
print("IATRONIX DSPy COMPARISON — DSPY_ENABLED=false vs DSPY_ENABLED=true")
print("="*100)

SEP = "-" * 100
HDR = (
    f"{'Query':<36} | {'Mode':<10} | {'Type':<12} | {'Time(s)':>7} | "
    f"{'Sections':>8} | {'Tokens':>7} | {'BLUF':>5} | {'Error':<30}"
)
print(SEP)
print(HDR)
print(SEP)

rows = []
for label, q, qtype in TEST_QUERIES:
    for mode, base in [("NO-DSPY", BASE_NODSPY), ("DSPY", BASE_DSPY)]:
        body, elapsed = query(base, q, qtype)
        error = body.get("detail") or body.get("error") or ""
        row = {
            "label": label,
            "mode": mode,
            "type": get_query_type(body),
            "time": elapsed,
            "sections": count_sections(body),
            "tokens": get_tokens(body),
            "bluf": has_bluf(body),
            "error": str(error)[:30] if error else "",
            "body": body,
        }
        rows.append(row)
        print(
            f"{label:<36} | {mode:<10} | {row['type']:<12} | {elapsed:>7.2f} | "
            f"{row['sections']:>8} | {row['tokens']:>7} | {'yes' if row['bluf'] else 'no':>5} | {row['error']:<30}"
        )

print(SEP)

# ── Summary deltas ─────────────────────────────────────────────────────────────
print("\nSUMMARY: DSPy vs Baseline")
print(SEP)
print(f"{'Query':<36} | {'Δ Time(s)':>9} | {'Δ Sections':>10} | {'Δ Tokens':>9} | {'BLUF gain':>10}")
print(SEP)

for i in range(0, len(rows), 2):
    no_dspy = rows[i]
    dspy_row = rows[i + 1]
    dt   = dspy_row["time"]     - no_dspy["time"]
    dsec = dspy_row["sections"] - no_dspy["sections"]
    dtok = dspy_row["tokens"]   - no_dspy["tokens"]
    bluf_gain = (not no_dspy["bluf"]) and dspy_row["bluf"]
    print(
        f"{no_dspy['label']:<36} | {dt:>+9.2f} | {dsec:>+10} | {dtok:>+9} | "
        f"{'yes (new)' if bluf_gain else 'no change':>10}"
    )

print(SEP)
print("\nFull raw responses saved to /tmp/dspy_comparison_results.json\n")

with open("/tmp/dspy_comparison_results.json", "w") as f:
    # strip body for readability — keep top level only
    out = [{k: v for k, v in r.items() if k != "body"} for r in rows]
    json.dump(out, f, indent=2)
