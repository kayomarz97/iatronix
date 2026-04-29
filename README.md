# Iatronix

Evidence-based medical reference for clinical professionals. Search real-time data from FDA, PubMed, NICE, and your own documents — formatted with AI, graded by evidence.

**Live:** [med.kayomarz.com](https://med.kayomarz.com)

---

## What it does

You type a clinical question. Iatronix fetches live data from 8+ authoritative sources in parallel, scores it for evidence quality, then uses your LLM key to format the result into structured sections with Level of Evidence (LOE I–III) and Class of Recommendation (COR I–IIb) on every claim.

No static knowledge base. Responses are grounded in data retrieved at query time whenever retrieval succeeds. If external fetch times out, the system can fall back to an explicit low-confidence model-generated response.

---

## How a search works — the 7-stage pipeline

```
Query
  │
  ├─ 1. Query rewriting
  │     Typos fixed, abbreviations expanded, terminology standardized
  │     (HTN → hypertension, MI → myocardial infarction)
  │
  ├─ 2. Classification
  │     Regex scoring → drug / disease / procedure / evidence / comparative
  │     Ambiguous queries → lightweight Claude Haiku call to resolve type
  │
  ├─ 3. Semantic cache lookup
  │     Query embedded → cosine similarity against past answers (threshold: 0.92)
  │     Hit + fresh → return immediately
  │     Hit + stale → bypass cache and run fresh pipeline (medical-safety first)
  │     Miss → continue pipeline
  │
  ├─ 4. Parallel data fetch (zero LLM tokens here)
  │     Drug:    OpenFDA labels, DailyMed, RxNorm, adverse events
  │     Disease: PubMed guidelines + recent RCTs, PMC full-text, StatPearls,
  │              Unpaywall PDFs, MedlinePlus summaries, NICE guidelines
  │     Each source: 20s timeout, fails silently
  │
  ├─ 5. Evidence quality assessment
  │     Fetched data scored before any LLM call
  │     Below minimum threshold → DegradedResponse (no generation)
  │     "Not enough data" is always safer than a confident hallucination
  │
  ├─ 6. Adaptive LLM formatting
  │     LLM is prompted to use fetched evidence first; if fetch timed out, fallback generation is allowed with warnings
  │     Prompt: fill schema fields, cite sources by index, no invented data
  │     Model routing: Haiku for drug/procedure, Sonnet for disease (higher depth)
  │     Token budget scales per query type (2048–8192 tokens)
  │
  └─ 7. Validation + cache store
        LOE/COR assigned structurally by source type, not inferred from text
        Citations verified against fetched data
        Sparse responses → second-pass LLM call with wider evidence budget
        Result stored in semantic cache
```

---

## How hallucinations are prevented

Five mechanisms prevent the LLM from inventing clinical facts:

**1. Evidence grounding**
The LLM is instructed to ground claims in retrieved evidence and cite source indices. If retrieval times out, fallback generation is allowed but clearly flagged for manual verification.

**2. Fail-closed design**
If retrieved evidence is insufficient, the pipeline stops and returns a `DegradedResponse` explaining what was found. Generation does not proceed.

**3. Citation validation**
Section claims cite source indices. The validator checks those indices exist in the fetched data. Claims without valid citations cannot pass.

**4. LOE/COR structural assignment**
Evidence levels are assigned by source type at the code level, not inferred by the model. A case report cannot be upgraded to LOE I regardless of how the LLM phrases the claim.

**5. Query-focused retrieval**
PubMed is searched with standardized MeSH-matched terms, not freeform prose. Date-sorted results prioritize recent guidelines over older studies.

---

## Tech stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 14 (App Router), TypeScript, Tailwind CSS |
| Backend | FastAPI (Python), async throughout |
| Database | PostgreSQL + pgvector (semantic cache, user data, PDF chunks) |
| Cache | Redis (24h exact-match cache) + pgvector (7-day semantic cache freshness window) |
| LLM | BYOK — user's own Anthropic / OpenAI / OpenRouter key |
| Embeddings | Voyage AI (Anthropic users), OpenAI text-embedding-3-small, Google |
| Auth | Firebase Auth |
| Storage | Cloudflare R2 (PDF uploads) |
| Infra | Docker Compose, Nginx, Cloudflare proxy |

---

## BYOK — Bring Your Own Key

Iatronix does not hold server-side LLM keys. Every generation call uses the user's own key, encrypted at rest with Fernet. Supported providers: Anthropic (Claude), OpenAI (GPT), OpenRouter.

This means:
- No cost passed through to users at the platform level
- No LLM data sent to Iatronix servers
- Users can switch providers anytime from Settings

---

## Data sources

| Source | What it provides |
|---|---|
| FDA OpenFDA | Drug labels, adverse events, recalls |
| PubMed / NCBI | Guidelines, RCTs, systematic reviews |
| PMC Open Access | Full-text articles, StatPearls monographs |
| Unpaywall | Free legal PDFs for open-access articles |
| RxNorm | Drug names, synonyms, interaction data |
| DailyMed | FDA-approved prescribing information |
| MedlinePlus | Patient-facing drug and disease summaries |
| NICE | UK clinical practice guidelines |

---

## Semantic caching

Cache hits return in ~200ms. The pipeline uses two cache layers:

- **Redis** — 24h exact-match cache on normalized query strings
- **pgvector semantic cache** — cosine similarity >= 0.92 against all past queries. Entries older than 7 days are treated as stale and skipped; the pipeline runs fresh retrieval/generation instead of returning stale medical content.

The `last_verified_at` timestamp from the DB row is used for staleness checks — not a field from the JSON payload, which would always be `None` after deserialization.

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

---

## Lessons learnt

### Quantity vs. quality is a harder trade-off than it looks

More PubMed results sounds better. In practice, 20 weakly-relevant abstracts produce worse output than 5 high-quality ones. A noisy evidence set causes the model to hedge, bury the clinical point, or invent a consensus that isn't in the sources. Evidence quality scoring before LLM formatting is what makes the fail-closed behavior work.

### Medical research is behind paywalls

Most impactful RCTs and meta-analyses are in paywalled journals. PubMed gives titles and abstracts. Unpaywall helps for open-access articles, but institutional guidelines (NICE, ACC/AHA, ESC) are not consistently machine-readable. A query about a rare condition or a recent trial may return a DegradedResponse — not because the answer doesn't exist, but because it exists behind a paywall and can't be fetched.

### LLMs are good editors, not good researchers

Give the model structured evidence and a schema to fill, and it produces clean, graded, citable output. Ask it to "find information about X" without grounded sources and it confabulates confidently. The fail-closed gate exists because in early testing the model would fill evidence gaps with plausible-sounding but unsourced content when retrieval came back sparse.

### Cache design has a correctness problem, not just a performance one

Semantic caching at 0.92 cosine similarity means "scabies management" and "scabies treatment guidelines" can map to the same cached response — usually correct. But old cache can miss guideline updates. Current behavior skips stale semantic hits and runs a fresh pipeline; the harder unsolved problem is detecting meaningful guideline deltas automatically.

---

## Running locally

```bash
# 1. Clone
git clone https://github.com/kayomarz97/med-ai-project
cd med-ai-project

# 2. Copy env template and fill in values
cp .env.example .env

# 3. Start all services
docker compose up -d --build

# Frontend: http://localhost:3100
# Backend:  http://localhost:8000
# API docs: http://localhost:8000/docs
```

Required `.env` values:
- `DATABASE_URL` — PostgreSQL connection string
- `REDIS_URL` — Redis connection string
- `ENCRYPTION_KEY` — Fernet key (generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)
- Firebase config (`NEXT_PUBLIC_FIREBASE_*`) — for auth
- Optional: `PUBMED_API_KEY` (NCBI), `OPENFDA_API_KEY`

User-provided at runtime (not in `.env`):
- Anthropic / OpenAI / OpenRouter API key (saved encrypted per user in DB)
- Voyage AI key (for Anthropic users who want PDF vector search)

---

## Disclaimer

For clinical decision support and educational purposes only. Always verify information with primary sources. Not a substitute for professional medical judgment.
