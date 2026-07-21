# Plan — "wrong drug answer" for a differential-diagnosis query + Haiku confusion

**Path:** `/root/projects/med-ai-project/.claude/plans/2026-07-21-ddx-misanchor-and-analyzer-truncation.md`
**Date:** 2026-07-21  **Branch:** dev first, then user promotes to main.

## Trigger
User searched (real logged query): **"abdominal mass with Mets to spleen differential diagnosis"**
and got an answer about a random drug for pancreatic cancer. Asked: how did it happen, how did it
bypass the safety nets, and why was "Haiku not working".

## What the investigation FOUND (all evidence-backed, on dev)

1. **Analyzer JSON truncation — VERIFIED, deterministic 3/3 (root cause).**
   `_analyze_and_expand_query` (rag_pipeline.py:2556) calls the Haiku analyzer with `max_tokens=512`.
   For this query the JSON overruns ~char 1620 (line ~27) and truncates mid-string → `JSON parse
   failed (Unterminated string ...) — falling back` on every attempt. The rich path (entities,
   pubmed_terms, condition_context, search_variants, related_topics) is LOST; the crude fallback
   classifier runs, returns `query_type="general"` → normalized to `complex` → comorbidity backstop
   forces `complex`. Retrieval then runs on a degraded, mis-anchored analysis.

2. **How it bypassed the nets (old build).** The nets check *provenance* (grounding/evidence floor),
   *sufficiency* (cross-strategy fallback = unique-PMID count), and *scope* (non-medical guard =
   ZERO medical terms). NONE checks *topicality / aboutness*. A real, well-cited pancreatic-cancer
   drug trial is grounded, sufficient, and medical → every net passes it. The mis-anchor (mass →
   "malignancy" → pancreatic literature) is invisible to all of them.

3. **Current dev build no longer emits the wrong answer** — it returns a SAFE `no_evidence` card
   (`grounding_gate: only 0 grounded claim(s) (type=complex) — returning no_evidence card`). The
   ~12:31 rebuild enabled the relevance floor + tightened grounding, which now strip the off-topic
   pancreatic articles → 0 grounded → honest card. Safer, but the user gets NOTHING instead of a real
   differential, because the analyzer truncation still breaks retrieval upstream.

4. **"Haiku not working" — key/model/routing are all FINE.** Key decrypts, is valid against the
   Anthropic API; `claude-haiku-4-5-20251001` is in the live catalog and in providers.yaml;
   `get_provider` routes it to anthropic; analysis calls returned `200 OK`. BUT generation ran on
   Cerebras (cerebras cache logs + BLUF-fail), and `GET /api/v1/providers` returned `401` — the model
   picker likely failed to load, so the Haiku selection was not sent as `model_explicit`, and
   generation defaulted to Cerebras. Needs one confirm (request payload / frontend providers 401).

## Proposed fixes (dev-first, flag/config where risky)

- **F1 (root, high value): stop the analyzer truncation.** Raise the analysis `max_tokens` (512 →
  ~1280) AND make the parse tiered/salvageable (reuse `query_classifier._parse_classification`
  recovery) so a truncated JSON degrades gracefully instead of nuking the whole rich analysis.
  Verify the 3/3 repro turns green.
- **F2 (topicality net): "aboutness" gate.** Before synthesis, require retrieved evidence entities to
  intersect the query SUBJECT entities; for differential/finding queries anchor on the finding
  (abdominal mass / splenic mets), not a hallucinated malignancy. Flag-gated, dev-first.
- **F3 (ddx shape): recognize differential-diagnosis / symptom queries** as their own shape so they
  aren't forced to `complex` and driven off a single mis-picked entity.
- **F4 (Haiku): fix the `/api/v1/providers` 401** so the picker loads and an explicit engine choice
  reaches generation (verify `model_explicit` end-to-end).

## DECISION (2026-07-21, user)
Build ALL FOUR (F1–F4), then A/B test the contribution of EACH (incremental / factorial, Haiku-judged,
reusing test/dev_vs_main_experiment.py + relevance_factorial.py patterns) to see which actually help.
Each fix stays flag-gated so it can be toggled independently for a clean A/B. Dev-first; prod OFF until approved.

## Verify
- Re-run `/tmp/repro.py` analyzer test → expect parsed rich analysis (not None) 3/3.
- Re-run the live query on dev → expect a grounded differential answer (or an honest card), never an
  off-topic drug answer.
- `verifier` agent + offline citation suite (37/37) before any promote. Prod stays OFF until approved.
