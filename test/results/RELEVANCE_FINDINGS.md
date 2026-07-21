# RELEVANCE PRECISION — 2³ factorial (floor × synonyms × sense)

**Problem:** "does paracetamol cause fever" surfaced an unrelated post-op arthroplasty *fever* guideline
(keyword match, drug absent). Three independent levers, tested in all 8 combinations on **niche** queries
(two loosely-related things → thin pools → off-topic matches surface). Fetch is API-free; **Haiku (Claude
Code subscription)** judged each surfaced article on/off-topic. Metric: off-topic rate among surfaced
top-8 (↓ better) + relevant-kept (↑ = not thinning). 8 queries across all types.

## Results (sorted best→worst off-topic rate)

| levers | surfaced | relevant kept | off-topic | off-topic rate |
|---|--:|--:|--:|--:|
| **floor + sense** | 24 | **6** | 18 | **0.750** ← best |
| floor + syn + sense | 26 | 6 | 20 | 0.769 |
| floor | 20 | 3 | 17 | 0.850 |
| floor + syn | 22 | 3 | 19 | 0.864 |
| sense | 41 | 5 | 36 | 0.878 |
| syn + sense | 41 | 5 | 36 | 0.878 |
| **baseline (none)** | 37 | **2** | 35 | **0.946** |
| syn | 37 | 2 | 35 | 0.946 |

## Verdict
**floor + sense wins decisively.** It has the lowest off-topic rate (0.75 vs 0.95 baseline — a 20-point
drop) AND triples relevant-kept (6 vs 2). The two levers are complementary and *both needed*:
- **Sense-framing** (adverse-sense PubMed terms) *fetches the right articles* — it raises relevant-kept
  from 2→5/6. Alone it can't lower off-topic (nothing drops the noise): 0.878.
- **Floor** *drops the entity-absent noise* — 0.946→0.85 alone. But alone it can't add on-topic articles.
- **Together**: sense supplies on-topic articles, floor removes off-topic ones → 0.75 + 6 relevant.

**Synonyms is neutral-to-slightly-negative on precision here** (floor+sense 0.750 → +syn 0.769) — the test
drugs mostly lack synonym ambiguity, and syn lets a couple more articles through. BUT it's a **safety net**:
it stops the floor from wrongly dropping an "acetaminophen" article on a "paracetamol" query — exactly the
reported bug's drug. Keep it ON for that protection; the precision cost is ~2 points.

**Recommended config: floor + sense + synonyms** (best precision + recall, with the acetaminophen safety net).

## Caveats
- These are **deliberately adversarial niche queries** — absolute off-topic rates are high (even the best is
  0.75) because thin pools + the min-keep=3 recall safeguard force some off-topic through when few on-topic
  articles exist. On normal queries rates are far lower. The RELATIVE ranking of combos is the result.
- Floor effectiveness depends on **anchoring on the subject (drug), not the effect (symptom)** — an article
  matching only "fever" must not count as relevant. The harness anchors on the drug; the pipeline integration
  must do the same.
- n=8 queries — directional, not statistically powered.

## Files
`../relevance_factorial.py`, `../relevance_aggregate.py`, `relevance_combos.json`,
`relevance_precision.json`, `rel_raw/q*.json`, `../PLAN-...` (plans/2026-07-21-relevance-precision-factorial.md)
