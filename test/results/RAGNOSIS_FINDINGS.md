# RAGnosis benchmark on med-ai (dev) — findings (2026-07-21)

Ran RAGnosis MRCP-style clinical MCQs + traps through the dev pipeline. Generation + judging by Claude
Code agents (NO BYOK, NO app LLM); retrieval is the REAL dev fetchers (free, NCBI/API). Claude stands in
for production gpt-oss-120b — indicative, not a production metric.

## Headline: SAFETY IS PERFECT AT SCALE
Across every run (50 and 120 questions): **faithful = 100%, true hallucinations = 0.** med-ai abstains
("insufficient evidence") rather than guessing whenever retrieval doesn't surface the fact. This is
RAGnosis's core dimension (does the app know the edge of its knowledge?) — med-ai passes emphatically, and
every fix in this round made it *more* honest, never less.

## 120-question result (all topics, full-chapter import + all levers on)
| | correct | +partial | faithful | hallucinations |
|---|--:|--:|--:|--:|
| baseline (500-char snippet cap) | 24% | 30% | 120/120 | 0 |
| + precision gate + full chapters | **27%** | **37%** | 120/120 | 0 |
| + concept-level chapter gate (tighten) | ~27% | ~37% | 120/120 | **0** |

Wins are carried overwhelmingly by StatPearls FULL chapters (29/37). The ceiling is retrieval + corpus-fit,
NOT the levers: ~1/3 of RAGnosis is answerable from what med-ai can fetch (it answers those well); the rest
are exam minutiae absent from PubMed / any matched chapter, or pure stats calculations retrieval can't help.

## Levers built this round (all flag-gated, default OFF, dev-first)
- **INTENT_FRAMING_ENABLED** — thread the analyzer's `intent` into retrieval (diagnosis/drug_dosing/
  side_effect/contraindication only — broad intents diluted). intent-mismatch 18→7.
- **REFERENCE_FIRST_ENABLED** — (a) StatPearls British→US spelling + key-aware exponential backoff
  (PLAYBOOK "NCBI E-utilities": 3/s no-key, 10/s per-key, 429 → jittered backoff); (b) WHOLE-chapter import
  (`char_cap` 16k→60k, 1 best chapter) so the answer deep in a chapter (t(15;17) in APL Etiology) grounds;
  (c) **concept-level title gate** — a chapter must contain the entity's most DISTINCTIVE token or ≥60% of
  its meaningful tokens (generic colour/laterality/acuity words never qualify). Killed "black eschar →
  Black Piedra", "molluscum → HIV-Prevention", "myelopathy → external-ear". Grounded-but-wrong 3→0.
  StatPearls coverage 14%→42%.
- **CONTRADICTION_SURFACING_ENABLED** — when sources disagree, the answer states the disagreement and cites
  both (prompt-level; A/B 7/7 inject, 0 leak).

## Remaining flaws (honest)
1. **Thin retrieval dominant** — the answer isn't in PubMed or any matched chapter (corpus-fit ceiling).
2. **Symptom-anchored entities → symptom-named wrong chapter** (Cyclic-Vomiting for B. cereus; Separation-
   Anxiety for dependent personality). NOT a chapter-match problem — the ENTITY is the symptom. Fix = make
   diagnostic vignettes retrieve on CANDIDATE DIAGNOSES (F3 differential path / the real analyzer), not raw
   symptoms. This is the genuinely-next lever.
3. Some chapters lack the scoped fact (UK-specific cause; pediatric investigation) even when on-topic.

## Caveats
Claude ≠ production gpt-oss-120b; concurrent batch throttles NCBI harder than a live single query (so 42%
reference coverage is a floor); symptom-anchored entities came from a Claude analyzer stand-in with an
answer-leak guard. Harness + raw results in scratchpad (q120_*, q120v2_*, recheck_*).
