"""F3 prompt-shape A/B — deterministic, NO LLM, NO API tokens.

Builds the REAL Phase-1 BLUF prompts with DIFFERENTIAL_DX_ENABLED ON vs OFF across many query shapes
and verifies the differential-diagnosis framing is injected for ddx queries ONLY, never leaks into
normal queries, and never appears with the flag OFF. (Answer *quality* — does the model follow it —
needs an LLM judge = tokens; this proves the wiring, deterministically and for free.)
"""
from app.config import settings
from app.services.prompt_engine import build_bluf_only_messages, build_complex_bluf_messages

MARKER = "DIFFERENTIAL-DIAGNOSIS MODE"

# (query, query_type, expected_ddx)
CASES = [
    ("empagliflozin mechanism of action", "drug", False),
    ("metformin dose in chronic kidney disease", "evidence", False),
    ("chronic kidney disease staging", "disease", False),
    ("warfarin vs apixaban in atrial fibrillation", "comparative", False),
    ("does metformin cause lactic acidosis", "evidence", False),
    ("drug of choice for CKD with T2DM and heart failure", "complex", False),
    ("management of community acquired pneumonia", "disease", False),
    # --- differential / diagnostic-reasoning queries (should inject) ---
    ("abdominal mass with Mets to spleen differential diagnosis", "complex", True),
    ("causes of splenomegaly", "disease", True),
    ("differential diagnosis of microcytic anemia", "disease", True),
    ("what could cause bilateral hilar lymphadenopathy", "disease", True),
    ("workup of a solitary pulmonary nodule", "disease", True),
    ("ddx of chronic diarrhea", "complex", True),
    ("which malignancy could a pancreatic head mass with jaundice be", "complex", True),
]


def bluf_dyn(query, qtype, flag):
    prev = settings.differential_dx_enabled
    settings.differential_dx_enabled = flag
    try:
        _, dyn, _, _ = build_bluf_only_messages(query, qtype, raw_query=query)
    finally:
        settings.differential_dx_enabled = prev
    return dyn


def main():
    print(f"{'query':<52}{'ddx?':>6}{'OFF':>6}{'ON':>5}{'delta_chars':>13}  verdict")
    ok = True
    inject_count = 0
    for query, qtype, expected in CASES:
        off = bluf_dyn(query, qtype, False)
        on = bluf_dyn(query, qtype, True)
        off_has = MARKER in off
        on_has = MARKER in on
        # correctness: OFF must never have it; ON must have it iff expected ddx
        good = (not off_has) and (on_has == expected)
        ok = ok and good
        inject_count += int(on_has)
        delta = len(on) - len(off)
        verdict = "OK" if good else "!! FAIL"
        print(f"{query[:50]:<52}{str(expected):>6}{str(off_has):>6}{str(on_has):>5}{delta:>13}  {verdict}")

    # complex BLUF builder path (ddx routed to complex with a drug slot)
    settings.differential_dx_enabled = True
    _, cdyn, _, _ = build_complex_bluf_messages(
        "which malignancy could a pancreatic head mass with jaundice be",
        drug="", primary_disease="abdominal mass", comorbidity_list=[])
    settings.differential_dx_enabled = False
    _, cdyn_off, _, _ = build_complex_bluf_messages(
        "which malignancy could a pancreatic head mass with jaundice be",
        drug="", primary_disease="abdominal mass", comorbidity_list=[])
    complex_ok = (MARKER in cdyn) and (MARKER not in cdyn_off)
    print(f"\ncomplex-BLUF builder: injected_ON={MARKER in cdyn}  leaked_OFF={MARKER in cdyn_off}  "
          f"-> {'OK' if complex_ok else '!! FAIL'}")

    print(f"\nInjected on {inject_count}/{sum(e for _,_,e in CASES)} expected ddx cases; "
          f"0 leaks into {sum(1 for _,_,e in CASES if not e)} normal cases.")
    print("RESULT:", "PASS" if (ok and complex_ok) else "FAIL")


main()
