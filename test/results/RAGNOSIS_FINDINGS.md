# RAGnosis benchmark on med-ai (dev) — findings (2026-07-21)

Ran RAGnosis MRCP-style clinical MCQs + traps through the dev pipeline. Generation + judging by Claude
Code agents (NO BYOK, NO app LLM); retrieval is the REAL dev fetchers (free, NCBI/API). Claude stands in
for production gpt-oss-120b — indicative, not a production metric.

## ⭐ COVERAGE LEVER RESULT (candidate-diagnosis chapter retrieval, 2026-07-22)
The single biggest correctness gain of the whole effort. Built `candidate_chapters_enabled`: for
symptom-vignette / diagnostic queries the analyzer proposes 2-3 candidate diagnoses and EACH gets its own
StatPearls chapter fetched (the raw symptom entity has no chapter of its own). Flag-gated, default OFF, dev ON.

| 120-q run | correct | +partial | faithful | halluc | chapter coverage |
|---|--:|--:|--:|--:|--:|
| v3 concept-gate (no coverage lever) | 28% | 32% | 100% | 0 | 45/120 (38%) |
| **v4 + candidate chapters** | **48%** (57/120) | **52%** | **100%** | **0** | **61/120 (51%)** |

**Controlled attribution (isolates the lever from judge variance):**
| cohort | v3 lever OFF | v4 lever ON |
|---|--:|--:|
| 47 questions the lever FIRED on | 9/47 (19%) | **34/47 (72%)** → +25 |
| 73 questions it did NOT touch (variance control) | 25/73 | 23/73 → −2 |

The control cohort drifted only −2 (judge noise) while the treated cohort **nearly quadrupled, 19%→72%**.
So the +25 is the lever, not lenient grading. Safety unchanged: 120/120 faithful, 0 hallucinations — a wrong
candidate's chapter simply lacks the fact → the pipeline abstains. `candidate_used`=28 wins (26 correct)
directly attributed by the judges to a candidate chapter.

CAVEATS (honest): (1) candidate QUALITY depends on the analyzer LLM — Claude stand-in may out-reason
production gpt-oss-120b, so this is an upper bound on candidate quality (retrieval mechanism + concept gate
are deterministic). (2) For pure "name-the-diagnosis" questions the analyzer's candidate ≈ the answer, so
the lever partly measures the analyzer's differential reasoning — but that IS the real production flow.
(3) Coverage 51% is a floor (concurrent batch throttled NCBI harder than a live single query).

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
| + concept-level chapter gate (tighten) — MEASURED, full chapters to judge | **28%** | **32%** | 120/120 | **0** |

Wins are carried overwhelmingly by StatPearls FULL chapters (27/34 = 79%). The ceiling is retrieval +
corpus-fit, NOT the levers.

### The decisive stat (2026-07-21 re-judge, all levers on, concept gate live)
| slice | n | correct |
|---|--:|--:|
| questions WHERE a StatPearls/Books chapter was retrieved | 45 | **60%** (27/45) |
| questions with NO reference chapter (PubMed abstracts only) | 75 | **9%** (7/75) |

Correctness is almost entirely a function of **reference COVERAGE**: 60% when a chapter is fetched, 9%
when not. So the next correctness lever must raise coverage (currently 45/120 = 38%), NOT tweak prompts
or tighten matching further. Concept gate vs precision gate: full-correct held (27→28%), partials fell
(37→32%) as the stricter gate rejected loosely-matched chapters — a precision/safety trade, not a
correctness win. Its real value was killing the 3 grounded-but-wrong cases (→0) at the 8-question check.

⚠️ METHODOLOGY NOTE: the first re-judge pass read 17%/32% because the judge-split script re-trimmed
chapters to 8000 chars — silently re-introducing the truncation the whole-chapter import exists to fix
(all 45 reference chapters exceeded 8000). Re-judging with FULL captured chapters (30000) recovered
+11 points (17→28%). Any chapter truncation ANYWHERE in the measurement path undercounts reference-first.

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
