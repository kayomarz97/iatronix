# Plan — RAGnosis-driven retrieval fixes (reference-first + intent + contradiction)

**Path:** `/root/projects/med-ai-project/.claude/plans/2026-07-21-ragnosis-retrieval-fixes.md`
**Date:** 2026-07-21 · dev-first · all flag-gated default OFF · **NO container rebuild until user asks**
(test via docker-cp inject + fresh python, never the served endpoint).

## Evidence (50-question RAGnosis batch on dev)
- Faithfulness 50/50, hallucinations 0, abstention 40/40 — SAFETY is perfect (validates grounding/F2/evidence-floor).
- Correctness 10/50 — ALL misses are retrieval, not reasoning. Buckets: 18 intent-mismatch, 17 thin, 5 entity-mismatch.
- ROOT of thin/intent: the answer often lives in a StatPearls chapter that isn't reaching the answer:
  `_fetch_book_monographs('hereditary hemochromatosis')` → "Laboratory Evaluation of Hereditary Hemochromatosis";
  `('pneumothorax')` → "Acute Pneumothorax Evaluation and Treatment". But `fetch_disease_data('haemochromatosis')`
  returned book_monographs=0 — spelling (haemo→hemo) + throttle fail-fast + not surfaced.
- Confound (honest): the q50 entities came from a Claude analyzer stand-in with an answer-leak guard that stripped
  stem-named conditions to symptoms → understates real coverage. Rerun must fix this + include reference content.

## B — Reference-first for disease/drug (highest value)  flag REFERENCE_FIRST_ENABLED
1. StatPearls robustness (`data_fetcher._fetch_book_monographs` / `fetch_disease_data`):
   - Spelling normalization for the book search: British→American medical spelling (haemo→hemo, oe→e, -isation→-ization, paediatric→pediatric, tumour→tumor) as an extra query variant.
   - Don't let a single NCBI throttle zero it when it's the primary grounding: one bounded retry on the precise `[title]` variant (still capped, still non-blocking of the main gather).
2. Drug: ensure `fetch_drug_data` FDA/DailyMed label + RxNorm summary are populated + surfaced.
3. Surface + prioritize: reference chapters/labels rank BEFORE PubMed abstracts in the data block for disease/drug/fact-recall intents (they encode "first-line X" directly). Reuses existing TEXTBOOK section.

## A — Intent-framing lever  flag INTENT_FRAMING_ENABLED
`intent_framing.intent_terms(intent, entities)` maps the analyzer's existing 10 intents → PubMed qualifiers/subheadings,
appended to `pubmed_expansion_terms` in `process_query` (same plumbing as F3 `differential_terms` / `query_sense`):
- diagnosis → `[diagnosis]` sh + "diagnostic criteria/cytogenetics"; drug_dosing → "administration and dosage[sh]/dose";
  treatment → `[therapy]` sh; guideline → guideline[pt] (already); side_effect/contraindication → query_sense covers.
Fixes the residual intent-mismatch not covered by a textbook chapter.

## C — Contradiction surfacing  flag CONTRADICTION_SURFACING_ENABLED
`prompt_engine`: add a rule — when retrieved sources give CONFLICTING recommendations/values, state the disagreement
explicitly and cite BOTH sides, rather than silently picking one. (Prompt-level; complements "never contradict data".)

## D — Test fix + rerun (dev, offline inject, no rebuild)
- Fix entity confound: keep the stem-named condition when present (don't over-strip to symptoms).
- Include reference content (book_monographs + drug label + FDA) in the evidence pack collector.
- Rerun retrieval on the 50 with B+A on; re-judge with parallel agents (Claude Code usage, no BYOK). Report deltas.
- Save `test/ragnosis_*` harness + `test/results/RAGNOSIS_FINDINGS.md` as a standing regression.

## Verify
Offline unit tests per lever; citation 37/37 + classifier 16/16 must stay green; rerun 50-batch shows correctness up
and thin/intent buckets down, faithfulness still 50/50 (no new hallucinations).
