# Iatronix

Iatronix is the medical reference website running at `med.debkay.com`.

This README describes the website as it works now:
- the current frontend
- the current backend
- the current production deployment
- the current query flow

It describes only the current product.

## 1. Production Architecture

Live traffic follows this path:

`Browser -> Cloudflare -> Nginx -> Next.js frontend -> FastAPI backend -> PostgreSQL + Redis`

Current production routing on this server:
- `med.debkay.com/` -> Next.js frontend
- `med.debkay.com/api/v1/*` -> FastAPI backend API

Current container layout from `docker-compose.yml`:

| Service | Role | Port binding |
| --- | --- | --- |
| `iatronix-frontend` | Next.js web app | `127.0.0.1:3200 -> 3000` |
| `iatronix-backend` | FastAPI API and retrieval pipeline | `127.0.0.1:8200 -> 8000` |
| `iatronix-db` | PostgreSQL with pgvector extension installed | internal |
| `iatronix-redis` | Redis cache | internal |

Important current reality:
- There is no local LLM runtime.
- There is no local embedding model in active use.
- Vector search is currently disabled.
- Semantic cache is currently disabled.
- All LLM usage is BYOK: the user brings their own key.

## 2. What the Website Does

Iatronix lets a signed-in user ask medical questions in plain language.

The system:
- analyzes the query
- retrieves live public medical data
- optionally uses the user's own LLM key to structure that evidence
- returns a typed result page with a direct answer first and evidence-backed detail below

The website currently handles these query families:
- drug questions
- disease questions
- comparative questions
- procedure questions
- evidence and safety questions
- adaptive mixed questions through the DSPy pipeline

## 3. Frontend: Current User Experience

The frontend is a Next.js app in `frontend/`.

Main pages:

| Route | Purpose |
| --- | --- |
| `/` | Home page with hero search, category shortcuts, and search history sidebar |
| `/query` | Result page for all medical answers |
| `/settings` | User profile, source mode, theme, and BYOK LLM key management |
| `/about` | Product explanation and source overview |
| `/login` | Email/password login |
| `/register` | Account creation |
| `/documents` | Document management UI |

Current query UX:
- the user must be signed in
- the API key is stored in browser local storage
- source mode is stored in local storage
- selected model is stored in local storage
- submitting a search sends the query through the Next.js proxy route `/api/query`

Current source modes exposed in the UI:

| Mode | Meaning |
| --- | --- |
| `ai` | Live retrieval plus LLM formatting using the user's own key |
| `scraping` | Live retrieval only, with no AI formatting |
| `pdfs` | Personal document mode; UI exists, but active vector-based document answering is not fully enabled right now |

Current result design:
- top hero block with direct answer first
- detailed evidence sections below
- references below the answer
- safety and evidence warnings at the bottom, not the top

Current result renderers:

| File | Current responsibility |
| --- | --- |
| `frontend/src/components/results/DrugInfoResult.tsx` | Drug detail view |
| `frontend/src/components/results/DiseaseInfoResult.tsx` | Disease detail view |
| `frontend/src/components/results/ComparativeResult.tsx` | Side-by-side comparison view |
| `frontend/src/components/results/ProcedureResult.tsx` | Procedure view |
| `frontend/src/components/results/EvidenceResult.tsx` | Evidence synthesis view |
| `frontend/src/components/results/GeneralResult.tsx` | General clinical summary view |
| `frontend/src/components/results/AdaptiveResultRenderer.tsx` | DSPy adaptive answer view |
| `frontend/src/components/results/ResultChrome.tsx` | Shared visual shell for result pages |

## 4. Backend: Current API and Responsibilities

The backend is a FastAPI app in `backend/`.

Main responsibilities:
- authentication
- BYOK LLM key storage
- query processing
- live evidence retrieval
- DSPy adaptive answer generation
- caching
- history logging
- profile management

Main API routes currently mounted under `/api/v1`:

| Route group | Purpose |
| --- | --- |
| `/health` | Health check |
| `/auth/register` | Register account |
| `/auth/login` | Login and rotate API key |
| `/auth/me` | Return current user profile |
| `/auth/profile` | Update current user profile |
| `/auth/llm-key` | Save, read, or delete encrypted user LLM key |
| `/models` | Return available model list |
| `/query` | Run the medical query pipeline |
| `/documents/*` | Document endpoints |
| `/history/*` | Search history endpoints |

Core backend files:

| File | What it does now |
| --- | --- |
| `backend/app/main.py` | App setup, middleware, router mounting, startup and shutdown |
| `backend/app/config.py` | Runtime settings |
| `backend/app/api/v1/query.py` | Main query endpoint |
| `backend/app/services/rag_pipeline.py` | Query orchestration, retrieval, DSPy path, formatting, validation, caching |
| `backend/app/services/data_fetcher.py` | Live medical data retrieval |
| `backend/app/services/dspy_modules.py` | DSPy module chain |
| `backend/app/services/dspy_signatures.py` | DSPy analysis and response signatures |
| `backend/app/services/prompt_engine.py` | Standard format-mode prompts |
| `backend/app/services/llm_factory.py` | Provider client creation |
| `backend/app/services/byok.py` | User-key encryption and validation |

## 5. Authentication and BYOK

Current auth model:
- user registers with email and password
- backend generates an API key
- frontend stores that API key locally
- all application requests use `X-API-Key`

Current BYOK behavior:
- the backend does not rely on your server-side Anthropic or OpenAI keys for routine answering
- users store their own LLM key through Settings
- keys are encrypted before storage

Supported user LLM providers currently exposed by the backend:
- `anthropic`
- `openai`
- `openrouter`

Current practical note:
- the site works best right now with user-provided Anthropic or OpenAI keys
- scraping mode works without an LLM key, but the answer is retrieval-only and less polished

## 6. Exact Query Flow

This is the current end-to-end request path for a normal website search.

### Browser and Next.js

1. User types a question on `/` or `/query`.
2. Frontend reads:
   - user API key from local storage
   - source mode from local storage
   - model selection from local storage
3. Frontend calls `frontend/src/lib/api.ts`.
4. Next.js receives the request at `frontend/src/app/api/query/route.ts`.
5. Next.js forwards the request to the backend at:
   - `http://iatronix-backend:8000/api/v1/query` inside Docker

### FastAPI

6. Backend middleware runs in this order:
   - payload limit
   - pre-auth IP rate limit
   - API key auth
   - per-key rate limit
7. Backend resolves the current user and query body.
8. Backend enters `process_query()` in `rag_pipeline.py`.

### Query Analysis

9. The pipeline determines source mode and model choice.
10. DSPy is the primary adaptive path when the user has an LLM key.
11. Lightweight structural fallback logic is used if DSPy or the adaptive analysis path is unavailable.

### Retrieval

12. The backend performs live retrieval from relevant sources.
13. Retrieval is scored for sufficiency.
14. If evidence is weak, a second targeted retrieval pass runs.

### Response Generation

15. If source mode is `ai` and user key is present:
   - DSPy or format-mode generation structures the answer
16. If source mode is `scraping`:
   - backend returns retrieval-backed data without AI formatting
17. The answer is validated, citations are enriched, and safety checks run.
18. The response is cached and search history is logged asynchronously.

### Frontend Rendering

19. `/query` selects the correct result renderer from `query_type`.
20. The page now displays:
   - direct answer first
   - detailed sections second
   - references after that
   - warnings and disclaimer at the bottom

## 7. Current Retrieval Sources

The backend currently pulls from live sources, not a static local medical knowledge base.

Current live sources in the pipeline:
- RxNorm
- OpenFDA
- DailyMed
- PubMed / NCBI
- PMC / StatPearls when available
- MedlinePlus
- NICE when relevant
- Semantic Scholar when relevant
- MedIndia as supplementary India-focused live drug information

Important current behavior:
- brand-to-generic resolution is live and online
- PubMed retrieval is broad corpus retrieval, not a narrow hard filter to a small journal list
- journal preferences are used as ranking hints, not as a hard exclusion wall

## 8. Current Answering Strategy

The backend is configured around evidence-first answering.

Current strategy:
- retrieval first
- answer second
- fail closed when evidence is too weak for a supported answer

Current DSPy behavior:
- query intent is analyzed first
- section requirements are inferred
- question-first output is enforced
- drug-in-disease answers prioritize condition-management guidance before generic label material
- disease answers prioritize the asked clinical need before background detail

Current answer shape across the UI:
- direct answer
- detailed supporting content
- references
- warnings and disclaimer footer

## 9. Current Data Storage

### PostgreSQL

Currently used for:
- users
- encrypted LLM provider metadata
- query logs
- search history
- document metadata
- vector-related tables that still exist in schema

### Redis

Currently used for:
- exact-match response cache
- request-frequency metrics
- runtime caching support

Current cache reality:
- Redis is active
- semantic vector cache is disabled

## 10. Current Document and Vector Status

This section clarifies the current document and vector status.

Current status:
- document endpoints and UI exist
- pgvector is installed in Postgres
- local embeddings have been removed
- vector search is disabled by configuration
- semantic cache is disabled by configuration
- document answering is not the primary active product path right now

So the current production website is fundamentally:
- live web retrieval
- optional BYOK LLM formatting
- evidence-backed structured answers

It is not currently a full active PDF-semantic-RAG product.

## 11. Current Runtime Settings That Matter

Important current settings from `backend/app/config.py`:

| Setting | Current value / meaning |
| --- | --- |
| `dspy_enabled` | `True` |
| `adaptive_second_pass_enabled` | `True` |
| `fail_closed_evidence_only` | `True` |
| `vector_search_enabled` | `False` |
| `semantic_cache_enabled` | `False` |
| `embedding_model` | `"disabled"` |
| `api_fetch_enabled` | `True` |
| `api_fetch_timeout_seconds` | `12.0` |
| `byok_enabled` | `True` |

Current default model routing values:
- Haiku for lighter structured work
- Sonnet for heavier disease synthesis
- OpenAI default model entry exists
- OpenRouter default model entry exists

## 12. Current Frontend-to-Backend Contract

Frontend sends this shape to the query proxy:
- `query`
- `model_id`
- `model_explicit`
- `query_type` or `null`
- `source_mode`

Backend returns a typed `QueryResponse` with:
- `query_type`
- `model_used`
- `response`
- `text_nodes`
- `safety_warnings`
- `validation_warnings`
- `disclaimer`
- `cached`
- `truncated`
- `latency_ms`

The frontend then picks one renderer based on `query_type`.

## 13. Current Deployment Commands

The website is currently deployed with Docker Compose.

Build and run:

```bash
docker compose up -d --build
```

Check container state:

```bash
docker compose ps
```

Backend health:

```bash
docker exec med-ai-project-iatronix-backend-1 \
  python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health').read().decode())"
```

Expected backend health response:

```json
{"status":"healthy","db":"connected","redis":"connected"}
```

## 14. Local Development

Backend:

```bash
cd backend
python -m uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Typecheck frontend:

```bash
cd frontend
npm exec -- tsc --noEmit
```

## 15. What This README Intentionally Does Not Claim

This README does not claim that the website currently:
- runs a local LLM
- uses active local embeddings
- uses a static local Indian drug repository
- is primarily a PDF-vector answering product

Those are not the current production truth.

## 16. Summary

The current website is:
- a Cloudflare and Nginx fronted medical reference site
- a Next.js frontend
- a FastAPI backend
- a PostgreSQL and Redis backed application
- a live retrieval system over medical web sources
- a BYOK AI formatting system with DSPy as the main adaptive answering path
- a question-first result UI with warnings at the bottom

That is the current product.
