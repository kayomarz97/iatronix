# Iatronix

Evidence-based medical reference for clinical professionals. Ask a clinical question; Iatronix retrieves
live data from 10+ authoritative medical sources in parallel, ranks it by evidence quality, then uses
**your own LLM key** to format the result into structured, citable sections — with a Level of Evidence
(LOE I–III) and Class of Recommendation (COR I–III) attached to every claim.

**Live:** [med.kayomarz.com](https://med.kayomarz.com)

> **No static knowledge base, and never the model's training data.** Every rendered answer is grounded in
> data retrieved at query time. If retrieval can't find citable evidence, Iatronix returns an honest
> "not enough evidence" card instead of a confident guess.

---

## What it does

You type a clinical question. Iatronix:

1. Rewrites and classifies the query (drug / disease / comparative / procedure / evidence / complex).
2. Neutralizes loaded phrasing so the evidence search isn't biased toward the conclusion you hinted at.
3. Fetches live data from 10+ free medical APIs **in parallel** (zero LLM tokens spent here).
4. Ranks every retrieved article by evidence quality (study type, recency, relevance, full-text, citations).
5. Enforces an **evidence floor** — if nothing citable is found, it broadens the search before giving up.
6. Uses **your encrypted LLM key** to write a short BLUF summary, then generates each section in parallel.
7. Runs a **grounding gate** over the result — any claim that can't be tied to a real source is demoted or
   dropped, and if too little remains grounded, the answer becomes an honest "no evidence" card.
8. Attaches a real, article-level citation link to every surviving claim.

The LLM is used as an **editor of retrieved evidence**, never as the source of the facts.

---

## What's functional today

A snapshot of what actually works on the live site right now.

| Capability | Status | Notes |
|---|---|---|
| Evidence-grounded clinical search | ✅ Live | 6 query types, per-claim LOE/COR grading |
| Bring-Your-Own-Key (BYOK) | ✅ Live | Cerebras (default) + Anthropic Claude enabled; keys Fernet-encrypted at rest |
| Provider-agnostic model layer | ✅ Live | One config file (`providers.yaml`) drives backend routing **and** the frontend key/model picker |
| Progressive streaming results | ✅ Live | BLUF summary appears first, then each section streams in as its agent finishes (SSE) |
| Resumable streaming | ✅ Live *(flag)* | A search survives a mobile tab-switch / screen-off and reconnects where it left off |
| Grounding gate + evidence floor | ✅ Live | Guarantees answers come from retrieved evidence, never training data |
| Stance neutralization (anti-sycophancy) | ✅ Live *(flag)* | Balanced evidence even when the question is phrased to push a conclusion |
| Multi-variation retrieval | ✅ Live *(flag)* | Searches several phrasings of the question to de-bias the evidence base |
| Per-section re-fetch | ✅ Live *(flag)* | A still-empty section triggers a targeted re-fetch + re-write of just that section |
| Deep citation-chasing | ✅ Live *(flag)* | When retrieval is thin, follows references forward/backward (iCite) to find grounding |
| Article registry (real citation links) | ✅ Live | Every citation resolves to an article-level URL — never a homepage fallback |
| Semantic + exact-match caching | ✅ Live | Redis exact-match (always on) + pgvector cosine-similarity cache (configurable) |
| Waves — spirometry analysis | ✅ Live | Upload a spirometry image → Claude vision → ATS/ERS interpretation |
| Waves — ECG | 🟡 Coming soon | Placeholder in the UI |
| Firebase authentication | ✅ Live | Client SDK + server-side Admin SDK |
| PDF upload + vector store | 🟡 Partial | Upload + embedding works; RAG retrieval not yet wired into the main query path |

*(flag)* = controlled by a feature flag in `.env`, so it can be turned on/off per environment without a code change.

---

## How a search works — the pipeline

```
Query
  │
  ├─ 1. Query rewriting & analysis (DSPy)
  │     Typos fixed, abbreviations expanded (HTN → hypertension, MI → myocardial infarction)
  │     Extracts entities, clinical intent (10 intents), and patient context
  │     (age / renal / hepatic / weight / pregnancy / concurrent drugs)
  │
  ├─ 2. Stance neutralization  [STANCE_NEUTRALIZER_ENABLED]
  │     "why is X NOT rational?" → neutral "X: clinical rationale and evidence base"
  │     The neutral form is what gets searched, so retrieval isn't one-sided
  │
  ├─ 3. Classification → drug / disease / comparative / procedure / evidence / complex
  │     User hint > DSPy analysis > LLM classifier > safe "complex" fallback
  │
  ├─ 4. Cache lookup
  │     Redis exact-match (24h) on the normalized query  → instant return on hit
  │     pgvector semantic cache (cosine similarity)      → near-duplicate questions
  │
  ├─ 5. Parallel data fetch (no LLM tokens spent here)
  │     asyncio.gather across 10+ medical APIs; each source times out and fails silently
  │     Complex queries cascade PubMed across comorbidity combinations to guarantee evidence
  │     Multi-variation retrieval [MULTI_VARIATION_SEARCH_ENABLED] fetches several phrasings
  │
  ├─ 6. Evidence ranking
  │     Every article scored: study type, relevance, recency, full-text, citation count
  │     Penalties for animal-only / off-population studies
  │     Highest-evidence articles survive the abstract budget
  │
  ├─ 7. Evidence floor + deep search
  │     has_minimum_evidence()? If not, up to 5 progressive broadening strategies run
  │     Still thin? Deep citation-chasing [DEEP_SEARCH_ENABLED] follows iCite references
  │     All strategies exhausted → honest "no evidence" card (no generation)
  │
  ├─ 8. LLM formatting — your key, two phases  [PARALLEL_SECTIONS_ENABLED]
  │     Phase 1: BLUF agent → headline + section titles + flowcharts/tables (streams immediately)
  │     Phase 2: one agent per section, in parallel → each section streams in as it finishes
  │     Every article is tokenized as [REF_N]; the model cites tokens, not free-text titles
  │
  ├─ 9. Grounding gate + post-processing  [GROUNDING_FLOOR_ENABLED]
  │     [REF_N] tokens resolved to real titles/PMIDs/URLs
  │     Claims with no real source are demoted (low-confidence) or dropped
  │     Too few grounded claims remain → answer becomes the honest "no evidence" card
  │     Per-section re-fetch [SECTION_REFETCH_ENABLED] fills any section still empty
  │
  └─ 10. Validation + cache store
        LOE/COR assigned structurally by source type — not inferred from the model's wording
        Article registry builds the final reference list (every link is article-level)
        Only grounded answers are cached
```

---

## How answers stay grounded (hallucination prevention)

Iatronix layers several independent mechanisms so the model can't invent clinical facts:

1. **Evidence floor** — before any answer is written, at least one citable source (PMID, NCT ID, DOI, NICE or
   FDA label URL) must exist. If not, up to five progressive broadening searches run; if those fail too, the
   pipeline stops and returns a `no_evidence` card. Generation never proceeds on empty evidence.

2. **Grounding gate** — after the model writes the answer, every claim is checked against the retrieved
   evidence. Ungrounded claims are **demoted** to low-confidence (shown with a badge) or dropped. If too few
   grounded claims remain, the whole answer is replaced with the honest "no evidence" card. This is the
   guarantee that a rendered answer is *retrieved evidence*, never training data.

3. **`[REF_N]` citation tokens** — each fetched article gets a deterministic token in the data block. The
   model emits `[REF_3]` instead of typing a title it might hallucinate; a post-processor maps tokens back to
   real titles/PMIDs/URLs. This is LLM-agnostic — it works the same across Cerebras, Claude, GPT, Gemini, etc.

4. **Article registry** — a single post-fetch source of truth with the hard guarantee that **every entry has
   a validated article-level URL**. References that can't be resolved to a real article are excluded entirely —
   there are no homepage fallbacks anywhere in the system. Ungrounded inline claims show an amber *Unverified*
   badge instead of a fake link.

5. **Structural LOE/COR** — evidence levels are assigned by source type in code, not inferred from the model's
   phrasing. A case report cannot be upgraded to LOE I no matter how confidently the model writes.

6. **Stance neutralization** — loaded query phrasing ("why is X *not* rational?") is rewritten to a neutral
   clinical question for retrieval, and anti-sycophancy rules are injected into every prompt, so the answer
   reflects the evidence rather than the framing.

7. **Strict citation validation** — for `complex` and `procedure` queries, any claim whose source isn't in the
   fetched data block is dropped, preventing the model from smuggling in training-knowledge recommendations.

---

## Providers & BYOK (Bring Your Own Key)

Iatronix holds **no server-side LLM keys**. Every generation call uses the user's own key, encrypted at rest
with Fernet and stored per-provider. Keys are never logged or returned to the client.

The entire provider layer is driven by a single file — `backend/config/providers.yaml` — which feeds both
backend routing and the frontend's key-entry cards and model picker (served via `GET /api/v1/providers`).

| Provider | Status | Default model | Notes |
|---|---|---|---|
| **Cerebras** | ✅ Enabled (default) | `gpt-oss-120b` | OpenAI-compatible, ~3,000 tok/s, ~$0.35/$0.75 per 1M tokens |
| **Anthropic (Claude)** | ✅ Enabled | `claude-haiku-4-5` | Haiku + Sonnet 4.6; powers Waves vision |
| Google (Gemini) | ⚪ Wired, not enabled | `gemini-3.5-flash` | Flip `enabled: true` in `providers.yaml` to activate |
| xAI (Grok) | ⚪ Wired, not enabled | `grok-4.3` | — |
| OpenAI | ⚪ Wired, not enabled | `gpt-4o-mini` | — |
| OpenRouter | ⚪ Wired, not enabled | `google/gemma-4-31b-it` | Includes OAuth PKCE connect + 3-model fallback chain |

Adding or enabling a provider is normally a **one-file change** to `providers.yaml`. Switching the default
Cerebras model is a one-line change to `CEREBRAS_DEFAULT_MODEL` in `.env`.

**What BYOK means for you:**
- No LLM cost is passed through at the platform level — you pay your provider directly.
- No prompt or response data is sent to an Iatronix-owned model.
- You can switch providers anytime from Settings.

---

## Tech stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS v4, Lucide icons |
| Backend | FastAPI, Python 3.12, async SQLAlchemy, Gunicorn (multi-worker) |
| AI orchestration | DSPy (adaptive analysis), LangGraph (parallel search graphs), LangChain (LLM clients) |
| Database | PostgreSQL 16 + pgvector (semantic cache, user data, PDF chunks) |
| Cache | Redis 7 (exact-match) + pgvector (semantic) |
| LLM | BYOK — Cerebras (default) / Anthropic, with Google, xAI, OpenAI, OpenRouter wired |
| Auth | Firebase Auth (client SDK + server-side Admin SDK) |
| Storage | Cloudflare R2 (PDF uploads) |
| Infra | Docker Compose, Nginx, Cloudflare proxy |

---

## Data sources

All free, public medical APIs. Each is fetched concurrently and fails silently so one slow source never
blocks the answer.

| Source | What it provides |
|---|---|
| FDA OpenFDA | Drug labels (marketed drugs only) and adverse-event data |
| DailyMed | Full FDA-approved prescribing information |
| RxNorm | Drug names, synonyms, class, interaction data |
| ChEMBL | Drug mechanism and pharmacology |
| PubMed / NCBI | Guideline abstracts, RCTs, systematic reviews |
| PMC Open Access | Full-text articles |
| NCBI Bookshelf | StatPearls monographs, GeneReviews, textbook chapters |
| ClinicalTrials.gov | Completed trial summaries with outcomes |
| Semantic Scholar | Paper metadata and citation counts |
| MedlinePlus | Patient-facing drug and disease summaries |
| NICE | UK clinical practice guidelines |

> **Tip:** Set a free `PUBMED_API_KEY` (from an NCBI account). A single query can fire ~15 NCBI calls;
> without a key the 3 req/s limit is the main cause of intermittent "no evidence" cards. A key raises it to
> 10 req/s.

---

## Evidence grading

| Grade | Meaning |
|---|---|
| LOE I | Randomized controlled trial |
| LOE II | Prospective cohort / guideline consensus |
| LOE III | Case reports / expert opinion |
| COR I | Strong benefit — should be done |
| COR IIa | Moderate benefit — reasonable |
| COR IIb | Weak benefit — may consider |
| COR III | No benefit or harmful |

A structured **confidence level** (low / moderate / high / strong) is also computed per answer from the count
of guidelines, RCTs, and systematic reviews retrieved.

---

## Caching

Cache hits return in ~200ms. Two layers:

- **Redis exact-match** (always on) — keyed by `v{prompt_version}:{model}:{query_type}:{md5(normalized query)}`.
- **pgvector semantic cache** — cosine similarity against past queries (threshold configurable, ~0.88–0.92).
  Near-duplicate questions ("scabies management" vs "scabies treatment guidelines") can reuse a result.

Only grounded answers are ever cached, and the cache key includes a `prompt_version` so a prompt change
invalidates stale entries automatically.

---

## Waves

A separate tab for waveform analysis, backed by its own service.

- **Spirometry** — upload a spirometry image; Claude (Sonnet) vision reads it, then deterministic ATS/ERS
  logic produces the interpretation. Uses your stored Anthropic key.
- **ECG** — placeholder, coming soon.

---

## Feature flags

Behavior is toggled in `.env` without code changes. The main ones:

| Flag | Effect when enabled |
|---|---|
| `PARALLEL_SECTIONS_ENABLED` | Two-phase BLUF + parallel per-section generation with progressive streaming |
| `RESUMABLE_STREAM_ENABLED` | Durable streaming jobs that survive a client disconnect (mobile tab-switch / screen-off) |
| `MULTI_VARIATION_SEARCH_ENABLED` | Fetch using several phrasings of the question (anti-sycophancy) |
| `SECTION_REFETCH_ENABLED` | Targeted re-fetch + re-write for any section still empty after retries |
| `DEEP_SEARCH_ENABLED` | Bounded citation-chasing (iCite forward/backward) when retrieval is thin |
| `STANCE_NEUTRALIZER_ENABLED` | Rewrite loaded queries to neutral clinical questions for retrieval |
| `GROUNDING_FLOOR_ENABLED` | Replace ungrounded answers with the honest "no evidence" card |
| `MODEL_ROUTING_ENABLED` | Auto-select model tier by query type |
| `SEMANTIC_CACHE_ENABLED` | Reuse results for near-duplicate (not just identical) queries |

---

## Running locally

```bash
# 1. Clone
git clone https://github.com/kayomarz97/iatronix
cd iatronix

# 2. Copy the env template and fill in the CHANGE_ME values
cp .env.example .env

# 3. Generate an ENCRYPTION_KEY (Fernet) and paste it into .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 4. Start all services
docker compose up -d --build

# 5. Run database migrations
docker compose exec iatronix-backend alembic upgrade head

# 6. Health check
curl http://localhost:8200/api/v1/health
# {"status":"healthy","db":"connected","redis":"connected"}

# Frontend: http://localhost:3200
# Backend:  http://localhost:8200
# API docs: http://localhost:8200/docs
```

**Required `.env` values** (placeholders are in `.env.example`; never commit real secrets):
- `DATABASE_URL`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` — PostgreSQL connection
- `REDIS_URL` — Redis connection
- `ENCRYPTION_KEY` — Fernet key for encrypting BYOK keys (generated above)
- Firebase config — Admin credentials file mounted into the backend, plus `NEXT_PUBLIC_FIREBASE_*` for the client

**Optional but recommended:**
- `PUBMED_API_KEY` — free from NCBI; raises the NCBI rate limit from 3 to 10 req/s
- `CEREBRAS_DEFAULT_MODEL` — change the default Cerebras model (default `gpt-oss-120b`)
- `OPENROUTER_CALLBACK_BASE` — only if enabling OpenRouter OAuth

**Provided at runtime, not in `.env`** (saved encrypted per user in the database):
- Your Cerebras / Anthropic / other provider API key

---

## Lessons learnt

### Quantity vs. quality is a harder trade-off than it looks
More PubMed results sounds better. In practice, 20 weakly-relevant abstracts produce worse output than 5
high-quality ones — a noisy evidence set makes the model hedge, bury the clinical point, or invent a consensus
that isn't in the sources. Ranking evidence *before* the LLM sees it is what makes fail-closed behavior work.

### A silent retrieval bug looks exactly like a fast, confident answer
For weeks, disease queries returned suspiciously quick "expert opinion" answers. The cause wasn't the model —
a type error (`unhashable type: 'dict'`) was crashing the disease fetch on every call, so retrieval silently
returned empty and the model filled the gap from training knowledge, which then got cached and replayed
instantly. The fix was one-line; the lesson is that **"fast and confident" is a red flag in a RAG system**,
which is exactly why the grounding gate now exists.

### LLMs are good editors, not good researchers
Give the model structured evidence and a schema to fill and it produces clean, graded, citable output. Ask it
to "find information about X" with no grounded sources and it confabulates confidently. Every mechanism in the
grounding section above exists because, in early testing, the model would fill evidence gaps with
plausible-sounding but unsourced content whenever retrieval came back sparse.

### Medical research is behind paywalls
Most impactful RCTs and institutional guidelines (NICE, ACC/AHA, ESC) aren't consistently machine-readable.
A query about a rare condition can return a "no evidence" card — not because the answer doesn't exist, but
because it exists behind a paywall and can't be fetched. Returning that honestly beats inventing an answer.

### Caching has a correctness problem, not just a performance one
Semantic caching at high similarity means two phrasings of the same question can share a cached answer —
usually correct, but old cache can miss guideline updates. The current design treats stale semantic hits as a
miss and re-runs the pipeline; detecting meaningful guideline deltas automatically is the harder open problem.

---

## Disclaimer

For clinical decision support and educational purposes only. Always verify information with primary sources.
Not a substitute for professional medical judgment.
