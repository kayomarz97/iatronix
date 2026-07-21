# Differential-diagnosis mis-anchor — fix + deterministic A/B findings (2026-07-21)

**Query that broke:** `abdominal mass with Mets to spleen differential diagnosis`
**Symptom:** answer about a random pancreatic-cancer drug. **Root cause:** retrieval returned almost
nothing on-topic (see baseline), so synthesis had only off-topic scraps to work with; the grounding/
evidence/scope nets check provenance, sufficiency and medical-ness but NOT *aboutness*, so an off-topic
but real, well-cited article passes them all.

## Fixes (all flag-gated, dev-first, prod OFF)
- **F1** `ANALYSIS_TRUNCATION_FIX_ENABLED` — analysis call budget 512→1280 + salvage a truncated JSON so
  the crude-fallback classifier stops firing on rich queries. (Root cause of the mis-analysis.)
- **F3** `DIFFERENTIAL_DX_ENABLED` — `differential_dx.differential_terms()` adds etiology/differential-sense
  PubMed terms anchored on the FINDING (recall).
- **F2** `TOPICALITY_GATE_ENABLED` — `ranking.apply_topicality_gate()` keeps only subject-mentioning
  articles, NEVER re-admits off-topic to hit a count (precision). Empty → honest no_evidence card.
- **F4** (`/api/v1/providers` added to auth-exempt list) — unrelated Haiku-picker bug; not A/B'd.

## Deterministic retrieval A/B (NO LLM, NO judge, NO API tokens — NCBI only)
Four arms; F2 applied as a post-fetch filter to the same fetched sets (clean isolation).

| arm | articles | on-finding % | off-topic noise % |
|---|--:|--:|--:|
| A baseline | 13 | 23 | 8 |
| B F3 only | 22 | 45 | 5 |
| C F2 only | 3 | 100 | 0 |
| **D F3+F2 (shipped dev config)** | **11** | **91** | **0** |

**Reading:** F3 is *recall* (nearly doubles the pool, +22pp on-finding). F2 is *precision* (100% on-finding,
0 noise) but low recall alone. **F3+F2 together** = 11 genuinely relevant articles, 91% on-finding, 0 noise —
the best of both. Baseline titles were junk (Pancreatic Injuries, acupuncture-for-constipation, POCUS-for-HIV);
D's surviving titles are a real differential: splenic metastases from prostate, nasopharyngeal, rectal, ovarian,
sigmoid, breast, lung, colorectal, and carcinoid primaries.

**Caveats (honest):** (1) baseline arm compares no-expansion vs F3-terms, not analyzer-terms±F3, because the
analyzer baseline needs a token-billed call. (2) PubMed/CT.gov results vary run-to-run (baseline was 10 then 13);
the RELATIVE deltas are the signal. (3) The answer *shape* (is it a well-structured ranked differential?) is not
measured here — that needs an LLM judge (tokens); eyeball on dev. (4) 91% not 100% in D: one methodology paper
("Do we CARE about the quality of case reports?") stem-matched — acceptable residual.

Raw: `ab_final_result.json`. Reproduce: `test/ab_ddx_retrieval.py` (offline).

## Broad ON/OFF sweep across query shapes (`test/ab_sweep.py`, offline)
Ran fixes OFF (baseline) vs ON (+F3 if ddx, then F2 gate) across simple → layered → differential queries
to confirm F2 does not OVER-filter normal queries. Danger signal = the gate blanking a query that had evidence.

| query shape | ddx | off | on | on-subject after gate | note |
|---|:-:|--:|--:|--:|---|
| simple drug MoA | – | 1 | 1 | (thin) | gate STEPPED ASIDE (nothing on-subject → unchanged) |
| simple dosing | – | 8 | 5 | 100% | |
| simple disease | – | 14 | 9 | 100% | |
| comparative | – | 11 | 9 | 100% | |
| causation/side-effect | – | 8 | 8 | 100% | anchors on drug, not symptom |
| layered comorbidity | – | 15 | 5 | 100% | |
| ddx simple (splenomegaly) | ✓ | 15 | 6 | 100% | |
| ddx layered (orig) | ✓ | 26 | 11 | 100% | |
| ddx anemia | ✓ | 10 | 5 | 100% | |

**Result: 0 queries blanked.** Every query keeps a healthy on-subject set (retention 62–100%), and the gate
reaches 100% on-subject everywhere.

**Refinement the sweep earned (F2 step-aside):** first sweep blanked "empagliflozin mechanism of action"
(1→0) because the lone article didn't repeat the drug token. `apply_topicality_gate` now DROPS the
off-subject remainder only when ≥1 article is on-subject; a total blank returns the set UNTOUCHED and defers
to the evidence-floor/grounding-gate — so F2 never manufactures a spurious no_evidence card. Re-sweep: 0 blanks.

## F3 answer-shape half (prompt A/B, `test/ab_f3_prompt.py`, offline)
Built the second half of F3: `prompt_engine._maybe_differential_guidance()` appends DIFFERENTIAL-DIAGNOSIS
MODE to the BLUF prompt (both general + complex builders) so ddx answers become a RANKED differential
(candidate diagnoses / discriminating features / red-flags / recommended workup) instead of the drug-centric
complex framing. Prompt-level A/B across 14 queries: **injected on 7/7 ddx queries, 0 leaks into
7 normal queries, absent with flag OFF; complex-builder path OK.**

## F3 answer-QUALITY A/B (parallel agent, Claude Code usage — NO BYOK, NO app LLM)
A parallel agent acted as stand-in generator+judge on real retrieved evidence (evidence_pack.json) for 2 ddx
queries, generating OFF vs ON answers and scoring a 6-item differential rubric. **Aggregate OFF 2.92 → ON 4.42
(+1.5, ~51%).** Gains: ranked structure +2.5, red-flags +2.5, treatment-tunnel avoidance +2.0, discriminating
features +2.0, workup +1.0. **BUT grounding regressed −1.0** — the "use these section titles" pressure induced
empty-section padding on thin evidence (splenic-mets query had only 2 sources), a latent hallucination risk in
the Can't-Miss section. **Fix applied (guidance hardening):** `_DIFFERENTIAL_DX_GUIDANCE` now says use sections
ONLY where evidence supports them (omit, don't pad) and REQUIRES an explicit "insufficient evidence for a full
differential" over a fabricated skeleton. Re-verified: prompt A/B still 7/7 inject / 0 leak, citation 37/37.
Caveats: n=2 queries, single entity generated+judged, model = Claude not production gpt-oss-120b — indicative,
not a production metric. A full metric needs many queries + blind independent judging.
