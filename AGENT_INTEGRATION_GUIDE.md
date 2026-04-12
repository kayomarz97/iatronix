# Iatronix — Agent Integration & Architecture Guide

> Use this document when adding new AI agents, integrating external tools, or improving the existing pipeline.

---

## 1. What Iatronix Does

Iatronix is a **BYOK (Bring Your Own Key) medical AI reference platform**. Users authenticate, supply their own LLM API key (Anthropic, OpenAI, or OpenRouter), and ask clinical questions. The system:

1. Classifies the query type (drug / disease / comparative / procedure / evidence / general)
2. Fetches live data from 8 free medical APIs in parallel
3. Routes to the appropriate LLM prompt and model tier
4. Returns a **typed, evidence-graded JSON response** that the frontend renders in a structured UI

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
  │  4. Source Routing + Entity Extraction │
  │  5. Parallel API Fetch (8 sources)     │
  │  6. Optional Vector Search (pgvector)  │
  │  7. LLM Call (DSPy or format-mode)     │
  │  8. Post-processing (validate, repair) │
  │  9. Cache Write + Async DB Log         │
  └────────────────────────────────────────┘
            │
  PostgreSQL (pgvector) + Redis
```

---

## 3. Key Files & Entry Points

| File | Role |
|------|------|
| `backend/app/services/rag_pipeline.py` | **Main orchestrator** — `process_query()` is the entry point for all queries |
| `backend/app/services/data_fetcher.py` | Fetches from all 8 medical APIs; each source is an async function |
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
`rag_pipeline.py` determines `query_type` via:
- User-supplied hint in the request (`query_type` field)
- Regex fallback classifier (`query_classifier.py`)
- Optional LLM classifier (if DSPy enabled)

**Types:** `drug` | `disease` | `comparative` | `procedure` | `evidence` | `general`

### 4.2 Cache Check
Redis key format: `v{prompt_version}:{model_id}:{query_type}:{md5(normalized_query)}`
- Hit → return immediately, skip all downstream work
- Miss → continue

### 4.3 Source Routing
`source_router.py` extracts drug/disease entities and selects the model tier:
- Drug queries → Haiku (fast, cheap)
- Disease / comparative / procedure → Sonnet (powerful, slow)
- Condition context is extracted for "drug in condition" queries (e.g., "metformin in CKD")

### 4.4 Parallel Data Fetch
`data_fetcher.py` fires all API calls concurrently with `asyncio.gather`. Each source is independent and fails silently. Results are merged into a `FetchedData` dataclass.

**Sources:**

| Source | What It Provides |
|--------|-----------------|
| OpenFDA | Drug labels, adverse events |
| PubMed/NCBI | Guideline abstracts, PMC full text |
| RxNorm | Drug names, interactions |
| DailyMed | Full FDA drug labels |
| MedlinePlus | Patient-friendly summaries |
| Semantic Scholar | Research paper metadata |
| StatPearls/NCBI Bookshelf | Medical monographs |
| MedIndia | Indian drug info (fallback) |

### 4.5 LLM Call
Two modes controlled by `source_mode` and `DSPY_ENABLED`:

- **Format mode**: Feed raw API data + schema into a prompt; LLM structures it
- **Generate mode**: LLM uses its training knowledge (fallback when fetch returns nothing)
- **DSPy mode**: Two-stage — `MedicalQueryAnalysis` determines required sections, `MedicalResponseGeneration` fills them

Token budgets per type:
- Drug: 2048 tokens (Haiku)
- Disease: 6144 tokens (Sonnet)
- Generate fallback: 4096 tokens

### 4.6 Post-Processing
1. JSON repair (LLM output is often malformed)
2. Citation validation (sources must be in the approved whitelist)
3. Drug name normalization (fuzzy match + metaphone)
4. Safety checking
5. Rich hyperlinking (PMID/DOI → URLs)

### 4.7 Response Shape

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

| Flag | Current Default | Effect When Enabled |
|------|----------------|---------------------|
| `API_FETCH_ENABLED` | `true` | Live medical API retrieval |
| `DSPY_ENABLED` | `true` | DSPy adaptive two-pass pipeline |
| `ADAPTIVE_SECOND_PASS_ENABLED` | `true` | Retry with relaxed constraints on sparse output |
| `MODEL_ROUTING_ENABLED` | `true` | Auto-select Haiku vs Sonnet |
| `VECTOR_SEARCH_ENABLED` | `false` | pgvector similarity search from uploaded PDFs |
| `SEMANTIC_CACHE_ENABLED` | `false` | Cache similar (not just identical) queries |
| `FAIL_CLOSED_EVIDENCE_ONLY` | `true` | Reject responses without evidence citations |

---

## 6. Adding a New AI Agent

The pipeline is designed to accept additional agents at specific integration points. Below are the primary hooks.

### 6.1 Add a New Query Type

1. **Add the type** to the `QueryType` enum in `schemas/query.py`
2. **Create a response schema** (e.g., `TriageResponse`) in `schemas/query.py`
3. **Add a classifier branch** in `query_classifier.py` (regex patterns or LLM prompt)
4. **Add fetch logic** in `data_fetcher.py` (new async function, add to `FetchedData`)
5. **Add a prompt builder** in `prompt_engine.py` (`build_<type>_prompt()`)
6. **Add a source route** in `source_router.py` (model tier, entity extraction)
7. **Add a frontend renderer** in `frontend/src/components/results/`
8. **Update `AdaptiveResultRenderer.tsx`** to handle the new type

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

Then add it to the `asyncio.gather()` call in `data_fetcher.py`'s main fetch function, and add a field to `FetchedData`.

### 6.3 Add a New LLM Provider

In `llm_factory.py`, add a new branch to the provider switch. The factory returns an object with a `.complete(prompt, max_tokens)` interface. Follow the existing Anthropic/OpenAI pattern.

### 6.4 Add a Specialist Sub-Agent (Multi-Agent Pattern)

The current pipeline is single-agent (one LLM call per query). To add a specialist sub-agent (e.g., a drug-interaction checker, a triage classifier, or a dosing calculator):

**Recommended approach — sequential agent handoff:**
```
rag_pipeline.process_query()
  ├─ [existing] Data fetch + format LLM
  └─ [new] specialist_agent.run(fetched_data, llm_output)
       └─ Returns enrichment dict merged into final response
```

Create `backend/app/services/agents/` and add:
- `base_agent.py` — Abstract interface: `async def run(context: dict) -> dict`
- `<name>_agent.py` — Concrete implementation
- Register in `rag_pipeline.py` as a post-processing step

**Recommended approach — parallel agent fan-out:**
```python
results = await asyncio.gather(
    existing_rag_call(query),
    drug_interaction_agent(entities),
    dosing_calculator_agent(entities),
)
merged = merge_agent_results(results)
```

### 6.5 Add a DSPy Module

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

## 7. Improvement Areas & Known Gaps

These are explicitly documented as incomplete or disabled:

| Area | Status | Notes |
|------|--------|-------|
| Vector search (pgvector) | Disabled (`VECTOR_SEARCH_ENABLED=false`) | Infrastructure exists; embeddings stored; needs activation and tuning |
| Semantic cache | Disabled (`SEMANTIC_CACHE_ENABLED=false`) | Would cache similar (not just identical) queries using cosine similarity |
| PDF document pipeline | Partial | Upload works, vectors stored, but RAG retrieval not integrated into main query path |
| Local LLM | Not implemented | Config stubs exist; needs llama.cpp or Ollama integration |
| Incomplete LLM output | Ongoing (`plans/incomplete-output-remediation-plan.md`) | DSPy second-pass is the current mitigation |
| Multi-turn conversations | Not implemented | Each query is stateless; no session context carried between queries |
| Specialist agents | Not implemented | Single LLM call per query; no sub-agent decomposition |
| Streaming responses | Not implemented | Frontend shows a spinner; could stream token-by-token |

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
