# Iatronix — Agent Integration & Architecture Guide

> Use this document when adding new AI agents, integrating external tools, or improving the existing pipeline.

---

## 1. What Iatronix Does

Iatronix is a **BYOK (Bring Your Own Key) medical AI reference platform**. Users authenticate, supply their own LLM API key (Anthropic, OpenAI, or OpenRouter), and ask clinical questions. The system:

1. Classifies the query type (drug / disease / comparative / procedure / evidence / general)
2. Fetches live data from 10+ free medical APIs in parallel
3. Ranks retrieved articles by evidence quality (study type, recency, relevance, fulltext availability)
4. Routes to the appropriate LLM prompt and model tier
5. Computes structured confidence levels (low/moderate/high/strong) based on guideline + RCT counts
6. Returns a **typed, evidence-graded JSON response** with confidence metadata

No server-side API keys are used for LLMs — all inference cost is borne by the user.

---

## 2. High-Level Architecture

```
Browser (Next.js 15)
  │  POST /api/query  (X-API-Key: JWT)
  ▼
Next.js Proxy  →  FastAPI Backend (port 8000)
                        │
            ┌───────────┼───────────────┐
            ▼           ▼               ▼
       Middleware    RAG Pipeline    Auth / CRUD
       (JWT, rate    (main logic)   (users, docs,
        limit)                       history)
            │
  ┌─────────┴──────────────────────────────┐
  │          RAG Pipeline steps            │
  │  1. Query Classification               │
  │  2. Redis Cache Check                  │
  │  3. Circuit Breaker Check              │
  │  4. Source Routing + LLM Intent        │
  │  5. Parallel API Fetch (10+ sources)   │
  │  6. Evidence Ranking by Quality        │
  │  7. Confidence Engine (guideline/RCT)  │
  │  8. Optional Vector Search (pgvector)  │
  │  9. LLM Call (DSPy or format-mode)     │
  │  10. Post-processing (validate, repair)│
  │  11. Cache Write + Async DB Log        │
  └────────────────────────────────────────┘
            │
  PostgreSQL (pgvector) + Redis
```

---

## 3. Key Files & Entry Points

| File | Role |
|------|------|
| `backend/app/services/rag_pipeline.py` | **Main orchestrator** — `process_query()` is the entry point for all queries |
| `backend/app/services/data_fetcher.py` | Fetches from 10+ medical APIs in parallel; includes new NCBI Books + ClinicalTrials.gov sources |
| `backend/app/services/ranking.py` | Ranks articles by multi-factor evidence score (study type, relevance, recency, fulltext, citations) — NEW |
| `backend/app/services/url_builder.py` | Deterministic source-aware URL enrichment (7-step priority) — PMID lookup, NCT ID lookup, DOI, source pattern matching with non-PubMed source guards |
| `backend/app/services/prompt_engine.py` | Builds prompts for each query type (format-mode and generate-mode) |
| `backend/app/services/llm_factory.py` | Instantiates LLM clients (Claude, OpenAI, OpenRouter) from the user's BYOK key |
| `backend/app/services/dspy_modules.py` | DSPy adaptive pipeline — analysis + generation signatures |
| `backend/app/services/dspy_signatures.py` | DSPy I/O type definitions |
| `backend/app/schemas/query.py` | All Pydantic response schemas (`DrugResponse`, `DiseaseResponse`, etc.) |
| `backend/app/api/v1/query.py` | HTTP route that calls `process_query()` |
| `backend/app/config.py` | Single source of truth for all settings and feature flags |

---

## 4. Query Lifecycle (Step-by-Step)

### 4.1 Classification
`rag_pipeline.py` determines `query_type` via (in priority order):
1. User-supplied hint in the request (`query_type` field) — confidence 0.99
2. LLM analysis+expansion result (`_analyze_and_expand_query()` call via DSPy) — confidence 0.95
3. LLM classifier fallback (`classify_query_llm()` call when #2 fails) — confidence variable
4. Fallback: `_no_llm_fallback()` returns `"complex"` type (catch-all) when no LLM key available — confidence 0.4

**LLM call routing** — for non-Anthropic providers, `_dspy_classify_model` uses the user's own model for classification:
- **OpenRouter** → uses user's OpenRouter model
- **Cerebras** → uses user's Cerebras model (e.g. `gpt-oss-120b`)
- **OpenAI** → uses user's OpenAI model
- **Gemini** → uses user's Gemini model
- **Anthropic** → uses `settings.model_classify` (Claude Haiku, optimized for classification cost)

**Model configuration** — All Anthropic model IDs (Haiku, Sonnet, Classify, Generate) are fully env-var configurable via `.env`:
- `MODEL_HAIKU`, `MODEL_SONNET` — primary generation models
- `MODEL_CLASSIFY`, `MODEL_GENERATE` — override defaults without code changes
- Error handling: If a model is not found on Anthropic (e.g., due to API plan or ID typo), the pipeline returns a friendly 400 error with instructions to update the model name via env vars. No cryptic 404 stack traces.

**Types (6 total, no "general"):**
- `drug` — single pharmaceutical agent, no clinical condition context; info-only questions (mechanism, dosing, side effects)
- `disease` — single disease/condition/syndrome, no drug/treatment context; overview, diagnosis, prognosis questions
- `comparative` — exactly two named entities being explicitly compared; outputs comparison table
- `procedure` — pure step-by-step technique only (no timing, management, or clinical context); "how to perform" questions only
- `evidence` — drug-in-condition (drug + disease context), timing/management decisions, postoperative protocols, safety/efficacy of intervention
- `complex` — everything else (multiple entities, comorbidities, vague queries, broad clinical questions, general medical questions); fetch all sources; catch-all default

**"general" type removed** — all queries now route to one of the 6 valid types. The LLM classifier is instructed never to return "general"; any value from cache or malformed output is normalized to "complex" by the safety net (line 2150–2157).

### 4.2 Cache Check
Redis key format: `v{prompt_version}:{model_id}:{query_type}:{md5(normalized_query)}`
- Hit → return immediately, skip all downstream work
- Miss → continue

### 4.3 Query Analysis & Patient Context Extraction
`_analyze_and_expand_query()` (via DSPy) performs multi-step analysis:

**Step 1 — Source Routing & LLM Intent:**
`source_router.py` extracts drug/disease entities, determines clinical intent, and selects the model tier:
- **Intent classification:** 10 clinical intents (treatment, diagnosis, drug_dosing, drug_safety, drug_comparison, guideline, side_effect, contraindication, prognosis, general) — enables intent-aware routing and search refinement
- **Entity extraction:** Drug/disease terms for guideline/trial filtering
- **Model selection:** Drug queries → Haiku (fast, cheap); Disease/comparative/procedure → Sonnet (powerful, slow)
- **Condition context:** Extracted for "drug in condition" queries (e.g., "metformin in CKD")

**Step 2 — Patient Context Extraction (May 2026):**
For complex and drug-in-condition queries, `_analyze_and_expand_query()` extracts structured clinical modifiers from the user's natural-language query:
- **age:** Numerical age or population descriptor (e.g., "72-year-old", "pediatric", "elderly")
- **renal:** Any creatinine clearance, GFR, dialysis status, ESRD, or CKD stage mention
- **hepatic:** Child-Pugh classification, cirrhosis grade, or liver failure level
- **weight:** Body weight in kg or BMI if mentioned
- **pregnancy:** Pregnancy status, lactation, or trimester
- **concurrent_drugs:** All named medications OTHER than the primary drug (e.g., "on amiodarone and fluconazole" in "rivaroxaban for AFib on amiodarone and fluconazole")
- **other_factors:** Immunocompromised status, transplant history, ICU setting, or other population modifiers

These are stored in `FetchedData.patient_context` dict (empty `{}` for simple queries) and passed to the section builders.

**How it works:**
1. User query: _"rivaroxaban 5mg in AFib, 72-year-old, CrCl 35, on amiodarone and fluconazole"_
2. `_analyze_and_expand_query()` extracts: `patient_context = {"age": "72-year-old", "renal": "CrCl 35", "concurrent_drugs": ["amiodarone", "fluconazole"]}`
3. These are formatted into the section-generation prompt as: _"Specified Patient Context: Patient age: 72-year-old. Renal function: CrCl 35. Concurrent medications: amiodarone, fluconazole."_
4. The prompt also includes clinical-relevance instructions: _"Include additional sections for any of the following that are CLINICALLY RELEVANT for rivaroxaban: Renal Dose Adjustment (if renally cleared) · Hepatic Dose Adjustment (if hepatically metabolised)..."_

**Two-layer approach:**
- **Layer 1 (explicit):** If patient context IS provided, sections are personalised with specific values (e.g., "Renal Dose Adjustment — CrCl 35: dose X")
- **Layer 2 (implicit):** Even WITHOUT patient context, the LLM uses its pharmacology knowledge to determine which sections are clinically relevant. A renally-cleared drug always warrants a renal dose section; a teratogenic drug always warrants pregnancy/lactation safety section. The LLM determines relevance, NOT hardcoded rules.

**Why this scales:** Any new drug in the query automatically gets appropriate sections based on the LLM's pharmacology knowledge without code changes. No per-drug rule hardcoding needed.

### 4.4 Parallel Data Fetch
`data_fetcher.py` fires all API calls concurrently with `asyncio.gather`. Each source is independent and fails silently. Results are merged into a `FetchedData` dataclass.

**Sources (10+):**

| Source | What It Provides |
|--------|-----------------|
| OpenFDA | Drug labels (marketed drugs only—filtered by product_type), adverse events (May 2026: added marketing status filter to exclude discontinued drugs) |
| PubMed/NCBI | Guideline abstracts, PMC full text, clinical trials |
| RxNorm | Drug names, interactions, drug class |
| DailyMed | Full FDA drug labels |
| MedlinePlus | Patient-friendly summaries |
| Semantic Scholar | Research paper metadata |
| StatPearls/NCBI Bookshelf | Medical monographs |
| NCBI Books | Broader medical handbooks (GeneReviews, Harrison's) — NEW |
| ClinicalTrials.gov | Completed trial summaries with outcomes — NEW |
| NICE | UK/EU clinical guidelines |
| ChEMBL | Drug mechanism, drug class, pharmacology |

### 4.5 Evidence Ranking & Confidence Engine
`ranking.py` scores and re-ranks all retrieved articles **before** LLM synthesis to ensure the strongest evidence survives the abstract budget:

**Scoring factors:**
- Study type (guideline: 10, systematic review: 8, RCT: 7, cohort: 5, case report: 1, etc.)
- Relevance (entity matches in title +3, abstract +2, capped at 6)
- Recency (≤5y: 2.0, 6-15y: 1.0, 16-25y: 0.5, >25y: 0.0) — preserves landmark trials (HOPE 2000, ALLHAT 2002, etc.)
- Fulltext availability (1.0 if PMCID present, 0.0 otherwise)
- Citation count (1.0 if ≥100 citations, 0.0 otherwise)
- Penalties (-3.0 for animal-only, -2.0 for off-population)

**Implementation:** `rank_article_list()` in `rag_pipeline.py` calls `_rank_fetched_abstracts()` after fetch, before `_cap_abstracts()` budget limits. Each article gets `_rank_score` and `_rank_breakdown` metadata for observability.

### 4.6 Confidence Engine
Replaces binary insufficient/sufficient with structured confidence levels based on evidence quality:

| Level | Condition | Usage |
|-------|-----------|-------|
| **strong** | ≥1 guideline + ≥3 total strong studies | Actionable recommendations |
| **high** | ≥1 strong study + ≥3 total studies | Good evidence base |
| **moderate** | Other combinations | Emerging/mixed evidence |
| **low** | ≤2 weak studies or 0 studies | Insufficient data |

**Fields in audit log:** `evidence_confidence` (level), `evidence_count` (total articles), `top_study_types` (breakdown).

### 4.7 LLM Call
Three modes depending on feature flags:

- **Parallel agent mode** (`PARALLEL_SECTIONS_ENABLED=true`): Two-phase pipeline:
  - Phase 1 — `build_bluf_only_messages()` → fast call (1024 tokens) → returns BLUF + section titles → emits `bluf` SSE event
  - Phase 2 — `asyncio.gather()` of N `build_section_messages()` calls (1200 tokens each) → emits `section_complete` per section
- **Single-call mode** (`PARALLEL_SECTIONS_ENABLED=false`): One large call with `build_adaptive_messages()`, tokens streamed live via `token_callback`
- **Generate mode**: Fallback when no API data retrieved; LLM uses training knowledge

Token budgets (single-call path):
- Drug: 2048 tokens (Haiku)
- Disease: 6144 tokens (Sonnet)
- Generate fallback: 4096 tokens
- Parallel BLUF: 1024 tokens / section: 1200 tokens

### 4.8 Post-Processing & URL Enrichment (May 2026 Update)
1. JSON repair (LLM output is often malformed)
2. **Complete Reference List** (May 2026):
   - `_normalize_consensus_sources()`: Converts all "Expert Consensus"/"Clinical Consensus" variants to canonical "Expert opinion"
   - `_build_complete_references()`: Merges LLM-cited refs (section context preserved) with ALL fetched articles (PubMed, NICE recommendations, FDA/DailyMed labels) — deduped by PMID/title
   - `_inject_fetched_refs()` removed as bottleneck — now includes ALL abstracts with direct article-level URLs (not capped at 8)
   - URL assignment: Direct PMID→PubMed URL, NCT ID→ClinicalTrials.gov, NICE rec→nice.org.uk, FDA label→dailymed/fda.gov (no homepage fallbacks)
3. Citation validation (`citation_validator.py`):
   - **Strict mode** (query_type=`complex` or `procedure`): Claims with sources not matching `[SOURCE: ...]` labels from fetched data are dropped (marked `__drop__=True`)
   - **Approved sources:** Whitelist of 30+ sources (PubMed, NICE, FDA, ACOG, etc.); unverified sources logged as warnings but allowed for non-strict types
   - **NA literal replacement:** LLM-output "NA"/"N/A" values in source field replaced with actual data source or "Medical literature" fallback
4. **Universal Source URL Flow** (`url_builder.py`):
   - **Step 0 (LLM output):** If the data block contained a `URL: https://...` label (from DailyMed, NICE, FDA, ClinicalTrials, or PubMed abstracts), the LLM copies it verbatim into the reference `url` field. This is the authoritative source for the URL.
   - **Step 1 (validation):** `url_builder.py` validates the LLM-provided URL exists and is safe (HTTPS, domain whitelist enforcement)
   - **Step 2 (construction for missing URLs):** For references without a URL from the LLM, use deterministic source-aware construction (7-step priority) — PMID lookup (guard: skip for non-PubMed sources), PMID/DOI inline, NCT ID lookup, source-name pattern matching
   - **Domain whitelist:** Includes `pubmed.ncbi.nlm.nih.gov`, `clinicaltrials.gov`, `doi.org`, `dailymed.nlm.nih.gov`, `www.accessdata.fda.gov`, `www.nice.org.uk`, and 20+ others
   - **Backward compatibility:** For any new source added in the future, if the fetch function stores a `label_url` in the result and the format helper includes `URL: {url}` in the data block text, the LLM will copy it verbatim without any url_builder code changes (existing domain whitelist permitting)
4. Drug name normalization (fuzzy match + metaphone)
5. Safety checking
6. Rich hyperlinking (PMID/DOI → source-specific URLs via `enrich_references()`)

### 4.8a Comparative Query Evidence Injection (May 2026)

For `query_type="comparative"` (two named entities being compared), the data block now includes **head-to-head evidence** that was previously fetched but unused:

**Evidence included per entity:**
- **Per-drug evidence:** Guideline abstracts, clinical trial abstracts, and systematic review abstracts specific to each drug
- **Head-to-head evidence:** Clinical trials comparing the two drugs directly, systematic reviews of both drugs side-by-side, and comparative guidelines

**Data block structure for comparative queries:**
```
=== DRUG 1 DATA ===
[Drug A profile: indication, mechanism, dosing, side effects, etc.]

=== DRUG 1 EVIDENCE ===
[Guideline abstracts about Drug A]
[Clinical trial abstracts about Drug A]
[Systematic review abstracts about Drug A]

=== DRUG 2 DATA ===
[Drug B profile...]

=== DRUG 2 EVIDENCE ===
[Guideline abstracts about Drug B]
[Clinical trial abstracts about Drug B]
[Systematic review abstracts about Drug B]

=== HEAD-TO-HEAD CLINICAL TRIALS ===
[Trials directly comparing Drug A vs Drug B]

=== HEAD-TO-HEAD SYSTEMATIC REVIEWS ===
[Reviews synthesizing evidence on Drug A vs Drug B]

=== COMPARATIVE GUIDELINES ===
[Guidelines discussing both drugs side-by-side]
```

**Section guidance expansion (for comparative drug queries):**
The `_SECTION_GUIDANCE["comparative_drug"]` now includes mandatory sections:
- Summary (what is being compared, key clinical question)
- Drug A Full Profile (Mechanism of Action, Indications, Dosing, Contraindications, Side Effects, Drug Interactions, Pharmacokinetics, Monitoring Parameters, Special Populations)
- Drug B Full Profile (same 8 sub-sections)
- Head-to-Head Comparison (MUST include a structured table: Drug A vs Drug B columns; rows must cover mechanism, dosing, efficacy, safety, contraindications, drug interactions, pharmacokinetics, guideline standing)
- Drug Interactions Between Agents (severity: major/moderate/minor; mechanism; clinical consequences; management)
- Clinical Evidence (key RCTs and systematic reviews with trial names, sample sizes, primary endpoints, results)
- Clinical Preference & Guideline Positioning

**Why this works:**
Previously, comparative queries returned only 4 thin sections. Now the LLM has access to full clinical evidence for each drug and head-to-head comparisons, enabling comprehensive structured comparisons with evidence citations throughout.

---

### 4.9 Response Shape

Every response carries per-claim evidence grades:
```json
{
  "value": "First-line for T2DM",
  "loe": "I",
  "cor": "I",
  "source": "ADA Standards of Care 2024",
  "confidence": "high"
}
```

Top-level response:
```json
{
  "query_type": "drug",
  "model_used": "claude-haiku-4-5-20251001",
  "response": { ... },
  "cached": false,
  "latency_ms": 2800,
  "safety_warnings": [],
  "disclaimer": "..."
}
```

---

## 5. Feature Flags (config.py)

These gates control which pipeline steps are active. Toggle in `.env` without code changes.

| Flag | Dev Default | Prod Default | Effect When Enabled |
|------|------------|-------------|---------------------|
| `API_FETCH_ENABLED` | `true` | `true` | Live medical API retrieval |
| `DSPY_ENABLED` | `true` | `true` | DSPy adaptive two-pass pipeline |
| `ADAPTIVE_SECOND_PASS_ENABLED` | `true` | `true` | Retry with relaxed constraints on sparse output |
| `MODEL_ROUTING_ENABLED` | `true` | `true` | Auto-select Haiku vs Sonnet based on query type |
| `PARALLEL_SECTIONS_ENABLED` | `true` | `false` | Phase-1 BLUF + parallel per-section LLM agents; progressive SSE display |
| `VECTOR_SEARCH_ENABLED` | `false` | `false` | pgvector similarity search from uploaded PDFs |
| `SEMANTIC_CACHE_ENABLED` | `false` | `false` | Cache similar (not just identical) queries |
| `FAIL_CLOSED_EVIDENCE_ONLY` | `true` | `true` | Reject responses without evidence citations |

---

## 6. Adding a New AI Agent

The pipeline is designed to accept additional agents at specific integration points. Below are the primary hooks.

### 6.1 Add a New Query Type

Note: The 6-type taxonomy (drug, disease, comparative, procedure, evidence, complex) is stable and complete. To modify classification behavior:

1. **Update the LLM classifier prompt** in `query_classifier.py`: `LLM_CLASSIFY_PROMPT` — add semantic rules for the new classification rule
2. **Update `_analyze_and_expand_query()` prompt** in `rag_pipeline.py` (Rule 8): add clarification on when the new rule applies
3. **Add/modify fetch logic** in `data_fetcher.py` if a query type now maps to different sources
4. **Add/modify prompt builder** in `prompt_engine.py` if response format changes per type
5. **Update `_SECTION_GUIDANCE`** dict in `prompt_engine.py` if section structure differs

For truly novel query types (unlikely), follow: Add schema → update LLM prompt → add fetch function → add prompt builder → add frontend renderer

### 6.2 Add a New Data Source

Add a new async function to `data_fetcher.py`:
```python
async def fetch_my_source(query: str, entities: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(MY_API_URL, params={"q": query})
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return {}  # Silent failure — never block the pipeline
```

Then add it to the `asyncio.gather()` call in `data_fetcher.py`'s main fetch function, and add a field to `FetchedData`. Make sure to populate the `data_sources` field in your result object so sources are rolled up into `FetchedData.data_sources`.

#### Universal Source URL Flow for New Sources (May 2026)

When adding a new data source, the URL propagation is **automatic** if you follow this pattern:

1. **In your fetch function**, store the human-readable page URL in the result object. For example:
   ```python
   result.label_url = f"https://my-api.com/articles/{article_id}"
   ```
   or add it to each item in a list:
   ```python
   item["url"] = f"https://my-api.com/drug/{drug_id}"
   ```

2. **In the format helper** (`_format_drug_block()`, `_format_abstracts()`, or a new format function), include the URL in the text output:
   ```python
   if url:
       lines.append(f"URL: {url}")
   ```

3. **In the LLM prompt** (reference schema), the LLM is instructed to copy the URL verbatim into the reference `url` field if present.

4. **In `url_builder.py`**, the URL is validated against the domain whitelist (add your domain if needed).

**No additional url_builder code changes required** — the LLM handles the URL propagation. This keeps the URL-construction logic centralized in the fetch and format functions, where the actual data lives.

#### May 2026 Update: Data Source Rollup
- **Added:** Automatic aggregation of all sub-result `data_sources` into top-level `FetchedData.data_sources` at end of `fetch_data_for_query()`
- **Purpose:** Enables accurate `fetch_sources` reporting to frontend for `DataSourceBadges` component
- **Implementation:** Loop through all `FetchedData` sub-results and `comparative_drug_data`, collect unique source strings, assign to `fetched.data_sources`

### 6.3 Add a New LLM Provider

**Step 1 — Register in the model registry (required):**
Edit `backend/app/services/model_registry.py` and add one entry to `_REGISTRY`:
```python
"your-model-id": {"provider": "yourprovider", "display": "Your Model Name", "input": 0.50, "output": 1.00},
```
This automatically propagates pricing, display names, and frontend labels everywhere.

**Step 2 — Add to the BYOK key column map (if adding a new provider type):**
- Add `your_provider_api_key` column to `backend/app/models/user.py`
- Add migration in `backend/app/main.py` lifespan startup (ALTER TABLE IF NOT EXISTS)
- Add to `_PROVIDER_COLUMN_MAP` in `backend/app/api/v1/auth_routes.py`
- Add to `_provider_col_map` in `backend/app/services/rag_pipeline.py` LLM key resolution

**Step 3 — Add to `llm_factory.py`:** add a new branch to the provider switch. The factory returns an object with a `.complete(prompt, max_tokens)` interface. Follow the existing Anthropic/OpenAI pattern.

**No frontend changes needed** — the engine toggle reads provider list from `GET /api/v1/config/llm`, which is built from `model_registry.py`. The new provider appears automatically.

### 6.5 OpenRouter OAuth + ChatService (added 2026-04)

**ChatService** (`backend/app/services/chat_service.py`) wraps OpenRouter calls with a **3-model fallback chain** for users who connect via OAuth PKCE:

Chain: `gemma_primary` → `gemma_fallback` → `meta_fallback` (Meta Llama 3.3 free — independent of Google infra)

```python
from app.services.chat_service import chat_with_fallback

result, is_fallback, used_model = await chat_with_fallback(
    messages=langchain_messages,
    user_key=decrypted_openrouter_key,
    max_tokens=4096,
    model_id="google/gemma-4-31b-it",  # optional — defaults to settings.openrouter_gemma_primary
)
```

**Key rule:** `chat_with_fallback` is only used when `use_chat_service=True` in `process_query()`. This flag is set when `user.openrouter_key` is set AND `user.encrypted_llm_key` is NOT set (OAuth path, not manual BYOK path). Manual BYOK OpenRouter users continue using `create_llm()` directly.

**Rate limit conservation:** When `use_chat_service=True`, the parallel sections pipeline is skipped regardless of `PARALLEL_SECTIONS_ENABLED`. OpenRouter free-tier models cap at ~20 req/day per model; parallel mode would burn 6–8 calls/query (3–4 queries/day). Single-call mode = 1 call/query (~20 queries/day).

**Adding a new fallback trigger:** Edit `_FALLBACK_STATUS_CODES` or `_is_fallback_trigger()` in `chat_service.py`.

**Adding a 4th model to the chain:** Add `openrouter_<name>_fallback` to `config.py` and append it to the `chain` list in `chat_with_fallback()`.

### 6.4 Add a Specialist Sub-Agent (Multi-Agent Pattern)

The pipeline now supports **parallel section agents** (live, enabled by `PARALLEL_SECTIONS_ENABLED`). The pattern:

```
process_query()
  │
  ├─ Phase 1: BLUF agent → returns headline + section titles
  │    └─ Emits: bluf SSE event (frontend renders ResultHero immediately)
  │
  └─ Phase 2: asyncio.gather — one agent per section title
       ├─ Each agent: build_section_messages() → LLM call → section dict
       └─ Results merged → AdaptiveResponse → done SSE event
```

**To add a new section type:**
1. Add the section title to `_SECTION_GUIDANCE[query_type]` in `prompt_engine.py`
2. The BLUF phase will automatically include it in `section_titles`
3. Phase 2 generates it in parallel alongside all other sections

**Frontend rendering for new sections (Comparative queries — May 2026):**
- For `query_type="comparative"`, the frontend `ComparativeLayout` component automatically groups sections into three zones based on title heuristics:
  - **Profile Zone:** Sections whose titles DON'T contain "comparison", "interaction", "preference", "evidence", "summary" — rendered as 2-column grid (desktop) or stacked (mobile)
  - **Comparison Zone:** Sections with "comparison" or "interaction" in the title, plus any tables — rendered with prominent table display
  - **Guidance Zone:** Sections with "evidence", "preference", or "positioning" in the title
- No frontend code changes needed when adding new sections; the heuristics automatically categorize new titles. To fine-tune layout for a new section type, update the title-matching regex in `AdaptiveResultRenderer.tsx` `ComparativeLayout` component.

**To add a post-generation specialist agent** (e.g., drug interaction enricher):
```python
# In rag_pipeline.py, after _run_parallel_pipeline() returns:
specialist_result = await my_specialist_agent(parsed, fetched_data)
parsed["sections"].append(specialist_result)
```

**Sequential agent handoff (alternative):**
```
process_query()
  ├─ [existing] parallel section pipeline
  └─ [new] post_processor.run(adaptive_response, fetched_data)
       └─ Returns enrichment merged into final response
```

### 6.5 Cascade Tiering for Rare Queries (Complex Multi-Condition Pattern)

The **complex query type** (drug/procedure in primary disease WITH comorbidities) implements a **cascade fetching pattern** to guarantee non-empty evidence even for rare combinations.

**Pattern Overview:**
```
_cascade_pubmed_for_complex(drug, primary_disease, comorbidities)
  │
  ├─ Tier 1: drug + primary_disease + ALL comorbidities  → "guideline"  (if ≥3 hits)
  ├─ Tier 2: drug + primary_disease + first comorbidity  → "rct"        (if ≥3 hits)
  ├─ Tier 3: drug + primary_disease                      → "review"     (if ≥3 hits)
  ├─ Tier 4: drug + first comorbidity                    → "case_report" (if ≥1 hit)
  ├─ Tier 5: drug alone                                  → "case_report" (if ≥1 hit)
  └─ Tier 6: (fallback) RxNorm drug class data           → "drug_class"
```

The tier is propagated to the section agents via `evidence_tier` field, which:
- Caps section `confidence` floor (case_report → low, rct → high)
- Prefixes section text with "Evidence is limited — based on case reports" when needed
- Ensures the UI displays confidence caveats appropriately

**When to use:** Apply this pattern when building queries where evidence is sparse for specific combinations. The guarantee is: if ANY data exists on the drug, it will be found and cited — never "no evidence" or hallucinated claims.

### 6.6 Add a DSPy Module

Add a new signature in `dspy_signatures.py`:
```python
class DrugInteractionAnalysis(dspy.Signature):
    """Identify and grade drug-drug interactions."""
    drug_a: str = dspy.InputField()
    drug_b: str = dspy.InputField()
    interaction_data: str = dspy.InputField()
    interactions: list[dict] = dspy.OutputField()
    severity: str = dspy.OutputField()  # "major" | "moderate" | "minor"
```

Then wire it into `dspy_modules.py` as a chain step.

---

## 7. Complex Query Type (Multi-Condition with Comorbidities)

**Added:** April 2026

The `complex` query type handles questions like: _"rivaroxaban dosing in severe AFib for a patient currently on fluconazole presenting with subacute hepatic impairment."_

**Distinguishing features:**
- Detects via regex in `query_classifier.py` (`_COMPLEX_RE`): looks for "with [comorbidity]", "alongside", "on [drug]", organ impairments, pregnancy, age modifiers
- Routes through `build_complex_bluf_messages()` and `build_complex_section_messages()` (forced section titles for baseline rule + per-comorbidity conflicts)
- Fetches via `_cascade_pubmed_for_complex()` — guarantees at least case-report-level evidence
- Validates citations strictly (`validate_citations(..., query_type="complex")`) — all claims must cite [SOURCE: ...] labels from the data block
- Emits evidence tier (guideline / rct / review / case_report / drug_class) to the frontend for confidence labeling

**Files modified:**
- `query_classifier.py`: add `_COMPLEX_RE` pattern, update LLM prompt
- `dspy_signatures.py`: add `comorbidity_list` output field
- `source_router.py`: add complex entity extraction
- `data_fetcher.py`: add `_cascade_pubmed_for_complex()`, `_fetch_comorbidities()`, cascade fields on `FetchedData`
- `prompt_engine.py`: add `build_complex_bluf_messages()`, `build_complex_section_messages()`
- `rag_pipeline.py`: route complex queries through new builders
- `citation_validator.py`: strict-mode enforcement for complex

---

## 7a. Strict Citation Validation Extended to Procedure Queries (May 2026)

**Rationale:** Procedure queries (e.g., "surgical treatment of Dupuytren's contracture") were allowing LLM to cite drugs/treatments from training knowledge even though no FDA data was fetched, leading to hallucinated drug recommendations.

**Change:**
- Modified `citation_validator.py` line 87: `strict = query_type in ("complex", "procedure")` (was only `"complex"`)
- Now drops any claim whose source doesn't match a `[SOURCE: ...]` label from the actual fetched data block for procedure queries
- Prevents LLM from inventing drug/treatment claims during procedure responses

---

## 7b. Citation Hardening — Robust Token Grounding (May 2026 v3)

**Rationale:** Three regressions observed after May v2 citation hardening: (1) **References empty.** Hardening over-corrected: `_is_grounded_ref` was too strict (exact normalized-title match required), rejecting paraphrased titles as hallucinations → claims dropped → only "Expert opinion" shown with no linked sources. (2) **Provider toggle stuck.** Frontend cached stale provider; backend used "first key wins" instead of honoring `engine_pref` → users switched to Anthropic but got Cerebras. (3) **Mid-stream shrinkage.** When `done` event arrives, aggressive post-processing (due to issue #1) drops claims the user already saw stream → visible content shrinkage on screen.

**Implementation** (`rag_pipeline.py`, `prompt_engine.py`, `url_builder.py`, `auth_routes.py`, `settings/page.tsx`, `QueryProvider.tsx`):

**Backend — References:**
1. **Unresolved token sentinel** — `_resolve_ref_tokens` now marks unparseable tokens with `__UNRESOLVED_TOKEN__` (not empty string). Triggers per-claim backfill instead of silent drop; distinguishable in audit logs.
2. **Tiered LLM-ref validation** — `_is_grounded_ref()` uses evidence-based tiers (not all-or-nothing): (a) PMID/NCT/DOI exact match → grounded; (b) title token overlap ≥0.5 against fetched articles → grounded (enables paraphrased titles); (c) source authority match (PubMed, NICE, FDA, etc.) with fetched articles present → grounded by association; (d) otherwise → not grounded (but claim may still be backfilled). Accepts Tier 1–3 evidence; no longer rejects tier-4 paraphrases.
3. **Gated quarantine (demote not drop)** — `_quarantine_sourceless_items()` now: (a) only runs if `fetched_data` is non-null (if no live API data, skip quarantine entirely to preserve training-knowledge content); (b) instead of **deleting** ungrounded claims, **demotes** them: sets `source="Expert opinion"`, `confidence="low"`. Users see the claim with a low-confidence badge (never a missing chunk).
4. **Broadened backfill** — `_backfill_expert_opinion_global` now fires on: (a) empty sources, (b) `__UNRESOLVED_TOKEN__`, (c) low-confidence demoted items. Per-claim backfill via `_best_article_for_claim()` lands each claim on the best-matching fetched article.
5. **URL safety net** — `url_builder.py` Step 5.5 deterministically rebuilds hallucinated URLs from structured `pmid`/`nct_id`/`doi` fields before returning None. Guarantees: every reference has a clickable link if any ID survives.
6. **Prompt token re-emission** — `build_section_messages()` and `build_complex_section_messages()` now re-emit valid `[REF_1]...[REF_{max_n}]` tokens in `dynamic_system` prompt (not just data block), with explicit instruction: *"NEVER write 'Expert opinion' as a token — reserve for low-confidence backfill."* Compensates for non-Anthropic models that lose context across long generations.

**Backend — Provider (engine_pref):**
7. **Authoritative engine_pref resolution** — `rag_pipeline.py` now: (a) reads `user.preferences["engine_pref"]` first; (b) if that provider has a key, use it; (c) else fall back to priority order (cerebras → anthropic → openai). "First key wins" logic removed.
8. **API returns active_provider** — `POST /auth/settings` now returns `{active_provider, ...}` so frontend has canonical source of truth.

**Frontend — Provider (engine_pref):**
9. **Single source of truth** — `settings/page.tsx`: (a) initialize `activeProvider` from `fetchBYOKKeys()` response; (b) all save handlers re-sync from API response (not localStorage assumptions); (c) `handleNewEnginePref` awaits `POST /auth/settings` and syncs from response.
10. **Fresh provider on submit** — `QueryProvider.tsx` calls `getLLMConfig()` at submit time (not stale closure) to get fresh provider + model_id from backend.

**Frontend — Mid-stream shrinkage:**
11. **Never shrink on done** — `QueryProvider.tsx` `done` handler now: (a) diffs streamed vs. post-processed sections by character count; (b) if post-processed is shorter, keeps streamed content and merges post-processed references only; (c) guarantees UI never shrinks vs. what user already saw.

**Feature flag:** `CITATION_REF_TOKENS_ENABLED`. Set to `false` to revert to pre-token pipeline instantly.

**Verification steps:**
- Drug query ("metformin T2DM") → every reference has non-null URL
- Multi-claim section → ≥2 distinct articles cited (inspect response JSON)
- Paraphrased title → claim retained with correct backing article (title_overlap scoring)
- Cerebras output → same or better coverage than v2 (unresolved tokens backfilled)
- Rare-disease query with 0 PubMed hits → low-confidence "Expert opinion" shown (never a missing chunk)
- Toggle provider mid-session → subsequent query uses selected provider (not cached stale value)
- Stream claim text → complete claim visible when `done` arrives (no visible shrinkage)
- Backend logs → `unresolved_token_count` counter → <5% of claims

---

## 8. Improvement Areas & Known Gaps

| Area | Status | Notes |
|------|--------|-------|
| Parallel section agents | **Live** (`PARALLEL_SECTIONS_ENABLED=true` on dev) | Phase-1 BLUF + Phase-2 parallel sections; progressive SSE display |
| Drug interactions in comparative | **Live** | Auto-injected when comparing ≥2 drugs |
| Progressive SSE streaming | **Live** | `bluf` + `section_complete` events; frontend renders progressively |
| Vector search (pgvector) | Disabled (`VECTOR_SEARCH_ENABLED=false`) | Infrastructure exists; embeddings stored; needs activation and tuning |
| Semantic cache | Disabled (`SEMANTIC_CACHE_ENABLED=false`) | Would cache similar (not just identical) queries using cosine similarity |
| PDF document pipeline | Partial | Upload works, vectors stored, but RAG retrieval not integrated into main query path |
| Local LLM | Not implemented | Config stubs exist; needs llama.cpp or Ollama integration |
| Multi-turn conversations | Not implemented | Each query is stateless; no session context carried between queries |

---

## 8. Database Schema (Quick Reference)

| Table | Purpose |
|-------|---------|
| `users` | Auth, bcrypt password, JWT key ID, encrypted BYOK LLM keys |
| `documents` | Uploaded PDFs — metadata + status |
| `document_chunks` | PDF chunks with pgvector embeddings (384-dim) |
| `query_logs` | Audit trail — every query, model used, latency, status |
| `search_history` | Per-user query history shown in the sidebar |
| `refresh_tokens` | JWT refresh tokens |

Migrations are in `backend/migrations/versions/` (Alembic).

---

## 9. Auth & Security Model

- Registration → bcrypt password → generates a UUID JWT `api_key` stored in `users`
- Login → verify password → return JWT signed with `ENCRYPTION_KEY`
- Every request carries `X-API-Key: <JWT>` validated by `ApiKeyAuthMiddleware`
- User's LLM key is stored as `Fernet(ENCRYPTION_KEY).encrypt(user_llm_key)` in `users.encrypted_llm_key`
- Middleware decrypts it and attaches it to `request.state` — never logged or returned

---

## 10. Local Development

```bash
# 1. Copy and fill env
cp .env.example .env
# Set ENCRYPTION_KEY to a new Fernet key:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 2. Start all services
docker compose up -d --build

# 3. Run migrations
docker compose exec iatronix-backend alembic upgrade head

# 4. Health check
curl http://localhost:8200/api/v1/health
# {"status":"healthy","db":"connected","redis":"connected"}

# 5. Frontend
open http://localhost:3200
```

**Backend tests:**
```bash
docker compose exec iatronix-backend pytest backend/tests/ -v
```

---

## 11. Rate Limits at a Glance

| Layer | Limit | Scope |
|-------|-------|-------|
| IP pre-auth | 30 req/min | Per IP |
| Per API key | 10 req/min | Per authenticated key |
| Free tier key | 20 req/min | Configurable |
| Premium tier key | 60 req/min | Configurable |
| LLM timeout | 90 seconds | Per call |
| Payload | 64 KB | Per request body |

---

## 12. Deployment Stack

```
Cloudflare (CDN, SSL, DDoS)
  └─ VPS Nginx (med.debkay.com)
       ├─ :80/:443  → localhost:3200 (Next.js)
       └─ /api/     → localhost:8200 (FastAPI)

Docker Compose:
  iatronix-frontend   (Next.js 15, port 3200)
  iatronix-backend    (FastAPI + Gunicorn 6 workers, port 8200)
  iatronix-db         (PostgreSQL 16 + pgvector)
  iatronix-redis      (Redis 7)
```
