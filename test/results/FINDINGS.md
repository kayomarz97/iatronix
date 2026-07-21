# FINDINGS — "Fetch-all" vs. Typed router

**Question:** if we always run *every* query-type search strategy and union the data ("more and
constant data"), does answer quality improve or reduce?

**Verdict (data-backed):** **Combining everything does NOT improve quality.** Retrieval *precision*
is flat-to-slightly-worse (TYPED 33.8% vs FETCH-ALL 30.6%), while cost and noise balloon: ~2.7×
latency, ~5.5× PubMed calls, ~3× duplicate abstracts, and ~4× more data thrown away by the prompt
cap. FETCH-ALL's only real wins come on queries the typed router serves *poorly* (a procedure that
returned 1 article; a mis-slotted complex query) — which argues for **better routing / a
confidence-gated fallback / broad-retrieve-then-rerank**, not for fetching everything every time.

Run date: 2026-07-21. No API cost: fetch layer uses `pubmed_expansion_terms=None` (no LLM); the
relevance judge is **Haiku via the Claude Code subscription** (Agent tool, `model="haiku"`), not the API.

---

## How it was measured
- **TYPED** = current behaviour: run the ONE matching `fetch_data_for_query()` strategy.
- **FETCH-ALL** = run all 6 strategies concurrently for the same input and union the abstracts
  (steelmanned: concurrent = best-case latency).
- Same 10 queries spanning every type + two edges (symptom-only, non-medical).
- Real fetchers in `backend/app/services/data_fetcher.py`. Network = NCBI E-utilities only (no key → 0.4s throttle).
- **Phase A** (deterministic): latency, PubMed esearch count, abstracts, unique PMIDs, duplication,
  cap-waste (per-bucket, using the real `_cap_abstracts` 3000-char budget), empty-fetch, evidence-tier.
- **Phase B** (Haiku judge): for each retrieved title, relevant vs not → precision = relevant / retrieved.

---

## Phase A — retrieval metrics (aggregate over 10 queries)

| Metric | TYPED | FETCH-ALL | Change |
|---|--:|--:|--|
| Mean latency | 3.90 s | 10.58 s | **2.7× slower** (max 8.6s → 16.7s) |
| PubMed esearch calls (total) | 65 | 358 | **5.5× more NCBI load** |
| Mean unique PMIDs / query | 3.2 | 12.5 | +9.3 (more recall) |
| Mean duplication ratio | ~1.9× | **3.08×** | more redundant refetching |
| Mean abstracts delivered to model (cap-kept) | 5.3 | 23.8 | more reaches model… |
| Total cap-waste (fetched then discarded) | 37 | **158** | **4.3× more wasted fetching** |
| Empty fetches | 2 / 10 | 1 / 10 | FETCH-ALL rescued 1 empty case |

Full per-query table: `phase_a_table.md`.

## Phase B — relevance precision (Haiku judge)

| Query | TYPED prec (rel/n) | FETCH-ALL prec (rel/n) | who wins |
|---|--:|--:|:--|
| drug: empagliflozin MoA | 0.50 (1/2) | 0.27 (3/11) | typed (fetch-all dilutes) |
| disease: CKD staging | 0.00 (0/15) | 0.00 (0/15) | tie* (judge harsh) |
| symptom-only: fatigue+night sweats | 0.58 (7/12) | 0.47 (7/15) | typed |
| evidence: SGLT2i in HF | **0.75 (6/8)** | **0.13 (2/15)** | typed (big dilution) |
| procedure: CVC insertion | 0.00 (0/1) | **0.69 (9/13)** | **fetch-all rescues thin typed fetch** |
| comparative: warfarin vs apixaban | **0.86 (6/7)** | 0.40 (6/15) | typed (big dilution) |
| complex: DOC for CKD+T2DM+HF | 0.00 (0/6) | **0.47 (7/15)** | **fetch-all rescues mis-slotted complex** |
| complex: metformin in CKD+HF | 0.10 (1/10) | 0.00 (0/15) | tie* (both weak; judge harsh) |
| drug-in-disease: amiodarone in AF | 0.50 (4/8) | 0.47 (7/15) | ~tie |
| non-medical: capital of France | 0.00 (0/5) | 0.00 (0/5) | tie (both correctly find nothing useful) |
| **OVERALL micro-precision** | **0.338 (25/74)** | **0.306 (41/134)** | **typed slightly higher** |

Efficiency: relevant articles per PubMed call — TYPED **0.385**, FETCH-ALL **0.115** → typed is
**~3.3× more efficient** at surfacing a relevant article per unit of NCBI load.

---

## Interpretation
1. **Precision is essentially flat, slightly favouring TYPED.** FETCH-ALL finds *more relevant
   articles in absolute terms* (41 vs 25) but only by fetching ~2× as many candidates — the extra
   relevant hits are bought with a proportional flood of irrelevant ones. Net quality-per-item drops.
2. **The dilution is worst exactly where the typed router already does well** — focused queries
   (evidence 0.75→0.13, comparative 0.86→0.40, drug 0.50→0.27). For these, FETCH-ALL is a clear
   downgrade: it drags high-precision retrieval down toward noise.
3. **FETCH-ALL only wins where TYPED is thin or misrouted** — the procedure query returned a single
   article (0.00 with n=1), and one complex query was mis-slotted (0.00); FETCH-ALL's breadth
   recovered relevant material. That is a *routing/recall gap in specific cases*, not a case for
   fetching everything universally.
4. **"More reaches the model" is true but lower-grade.** FETCH-ALL delivers ~4× more abstracts past
   the cap (23.8 vs 5.3), yet those extra delivered items are lower precision — so the model is fed
   more, but noisier, context, while 158 fetched abstracts are discarded by the cap anyway.
5. **Latency is the reliability risk.** Even best-case-concurrent and with the LLM-expansion layer
   OFF, FETCH-ALL averaged 10.6s (max 16.7s). In production, expansion terms + no-key throttle +
   load push this toward the **31s fetch timeout** — past which the answer gets *no* grounded data.

## Recommendation
Do **not** adopt unconditional FETCH-ALL. Capture its upside (robustness on thin/misrouted queries)
without its cost by:
- **Confidence-gated second fetch:** if the typed fetch returns < K unique abstracts (as the
  procedure and complex cases did), fire ONE additional broad/evidence strategy — not all six.
- **Broad-retrieve → rerank → top-k:** reuse the existing `rank_article_list()` so relevance, not an
  arbitrary char-cap, selects what the model sees.
- **Fix routing for the thin cases:** the procedure fetcher returning 1 article and the complex
  positional `[0]=drug` mis-slotting are the actual defects the FETCH-ALL "win" is masking.

## Caveats / limits (honest)
- **Judge is noisy.** Haiku marked CKD-staging 0/15 for *both* conditions — implausibly harsh; the
  absolute precision numbers carry error. The **relative/directional** pattern (dilution on focused
  queries, rescue on thin ones) is robust across queries and matches the mechanics.
- **LLM query-expansion disabled** (to keep it API-free). In prod both arms would fetch somewhat more;
  FETCH-ALL's latency/duplication would grow *faster* than TYPED's.
- **No PubMed API key** here → 0.4s throttle. With a key both arms speed up, but the 5.5× call-count
  gap (rate-limit/cost exposure) is unchanged.
- **Precision proxy = title relevance**, not full grounded-citation correctness. It tests the
  signal-dilution claim directly; it does not measure final answer accuracy.
- n = 10 queries. Directional, not a statistically powered benchmark.

## Files
- `phase_a_metrics.json`, `phase_a_table.md` — retrieval metrics
- `phase_b_input.json`, `phase_b_raw/q*.json`, `phase_b_precision.json` — relevance judging
- `../run_retrieval_experiment.py`, `../phase_b_aggregate.py`, `../PLAN-2026-07-21-fetch-all-vs-typed.md`
