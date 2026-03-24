# Iatronix — Complete Architecture & Workflow Reference

> Auto-generated from codebase scan. Update this file whenever structural changes are made.
> Last updated: 2026-03-23

---

## Table of Contents
1. [System Overview](#system-overview)
2. [Infrastructure & Deployment](#infrastructure--deployment)
3. [Full Request Lifecycle](#full-request-lifecycle)
4. [Backend Architecture](#backend-architecture)
5. [Frontend Architecture](#frontend-architecture)
6. [Database Schema](#database-schema)
7. [Authentication & BYOK](#authentication--byok)
8. [PDF Ingestion Pipeline](#pdf-ingestion-pipeline)
9. [RAG Pipeline (Query Flow)](#rag-pipeline-query-flow)
10. [External API Sources](#external-api-sources)
11. [Caching & Circuit Breaker](#caching--circuit-breaker)
12. [Environment Variables](#environment-variables)
13. [File Index](#file-index)
14. [Pending Changes / Roadmap](#pending-changes--roadmap)

---

## System Overview

Iatronix is an AI-powered medical reference platform. Users log in, enter their own LLM API keys (BYOK), and query drug/disease/comparative/procedure questions. The backend fetches authoritative data from free medical APIs, feeds it to the user's LLM for formatting into structured, evidence-graded responses.

**Stack:**
- **Database**: PostgreSQL 16 + pgvector (vector similarity search)
- **Cache**: Redis 7
- **Backend**: Python 3.12 + FastAPI (port 8200 → internal 8000)
- **Frontend**: Next.js 15 + TypeScript (port 3200 → internal 3000)
- **Reverse Proxy**: Nginx on VPS host (external) → Cloudflare (CDN/DDoS)
- **Containerization**: Docker Compose

---

## Infrastructure & Deployment

```
Internet → Cloudflare (CDN + SSL) → VPS Nginx → Docker Compose
                                          ↓
                              ┌─────────────────────┐
                              │  iatronix-net       │
                              │  ┌───────────────┐  │
                              │  │  iatronix-db  │  │
                              │  │  (PostgreSQL) │  │
                              │  └───────────────┘  │
                              │  ┌───────────────┐  │
                              │  │iatronix-redis │  │
                              │  └───────────────┘  │
                              │  ┌───────────────┐  │
                              │  │   backend     │  │
                              │  │  :8200→8000   │  │
                              │  └───────────────┘  │
                              │  ┌───────────────┐  │
                              │  │   frontend    │  │
                              │  │  :3200→3000   │  │
                              │  └───────────────┘  │
                              └─────────────────────┘
```

**Port bindings (host-side):**
- `127.0.0.1:8200` → backend FastAPI
- `127.0.0.1:3200` → frontend Next.js

**Nginx on VPS host** (not inside Docker) proxies:
- `med.example.com` → `127.0.0.1:3200` (frontend)
- `med.example.com/api/` → `127.0.0.1:8200` (or via frontend proxy)

**Cloudflare** handles SSL termination and DDoS protection in front of Nginx.

> Note: `traefik/` directory in this repo is a leftover — Traefik is NOT used. Safe to remove.

---

## Full Request Lifecycle

### Search Query
```
User types query
  → Frontend SearchBar (page.tsx)
  → POST /api/query (Next.js route: src/app/api/query/route.ts)
  → POST http://iatronix-backend:8000/api/v1/query (backend internal)
      → middleware stack:
          1. PayloadLimitMiddleware (max 64KB)
          2. RateLimitMiddleware (30 req/min per IP pre-auth)
          3. ApiKeyAuthMiddleware (validate JWT, load user + BYOK key)
          4. PerKeyRateLimitMiddleware (10 req/min per key)
      → api/v1/query.py
      → rag_pipeline.py (main orchestrator):
          1. query_classifier → type (drug/disease/comparative/procedure/general)
          2. cache.check(hash(query+type+model)) → return cached if hit
          3. circuit_breaker check
          4. source_router → extract entity names, select model tier
          5. data_fetcher → parallel async fetch (OpenFDA, PubMed, RxNorm, etc.)
          6. vector_search → top-k chunks from pgvector
          7. prompt_engine → build format-mode or generate-mode prompt
          8. llm_factory.create_llm(user_key) → LLM call
          9. json_repair → fix malformed JSON
         10. citation_validator → verify sources
         11. safety_checker → content safety
         12. drug_linker → normalize drug names
         13. cache.set(result, ttl)
         14. async_log → write to query_logs table
      ← structured JSON response
  ← frontend renders with DrugInfoResult/DiseaseInfoResult/etc.
```

### PDF Upload
```
User selects PDF
  → POST /api/documents/upload (Next.js route)
  → POST http://iatronix-backend:8000/api/v1/documents/upload
      → pdf_verifier.verify_pdf() — check publisher signatures
      → ingest_pdf():
          1. pdfplumber → extract text per page
          2. RecursiveCharacterTextSplitter → ~2000 char chunks, 400 overlap
          3. Embedder (all-MiniLM-L6-v2 local) → 384-dim embeddings
          4. Store Document + DocumentChunks in PostgreSQL pgvector
      ← document metadata (id, title, verified, publisher)
```

---

## Backend Architecture

### File Structure
```
backend/
├── app/
│   ├── main.py              FastAPI app init, lifespan, middleware, routes
│   ├── config.py            All settings via pydantic-settings (single source of truth)
│   │
│   ├── api/v1/
│   │   ├── auth.py          JWT token auth routes
│   │   ├── auth_routes.py   POST /register, /login
│   │   ├── documents.py     GET/POST /documents, POST /documents/upload
│   │   ├── health.py        GET /health
│   │   ├── models.py        GET /models (available LLMs)
│   │   └── query.py         POST /query (main entry point)
│   │
│   ├── core/
│   │   └── auth.py          Password hashing (bcrypt), JWT token generation
│   │
│   ├── db/
│   │   ├── session.py       SQLAlchemy async session factory
│   │   └── init_db.py       DB init helper
│   │
│   ├── middleware/
│   │   ├── payload_limit.py Max request body 64KB
│   │   ├── api_key_auth.py  API key validation, user lookup, BYOK decrypt
│   │   └── rate_limit.py    IP-based rate limiting (pre-auth)
│   │
│   ├── models/              SQLAlchemy ORM
│   │   ├── base.py          id, created_at, updated_at
│   │   ├── user.py          Users (see schema below)
│   │   ├── document.py      PDF/PMC/PubMed documents + embeddings
│   │   └── query_log.py     Audit trail + full responses (JSONB, ≤1MB)
│   │
│   ├── schemas/             Pydantic request/response models
│   │   ├── auth.py          Login/register request/response
│   │   ├── models.py        Model info
│   │   └── query.py         Drug/Disease/Comparative/Procedure/General/Evidence response types
│   │
│   └── services/            Business logic
│       ├── rag_pipeline.py  Main orchestrator (see flow above)
│       ├── source_router.py Entity extraction (regex, zero-AI), model tier selection
│       ├── data_fetcher.py  Parallel async HTTP fetching from 7 medical APIs
│       ├── query_classifier.py Classify query type (drug/disease/comparative/procedure/general)
│       ├── prompt_engine.py Format-mode + generate-mode prompts for all query types
│       ├── llm_factory.py   Claude + OpenRouter clients, BYOK support, fallback
│       ├── cache.py         Redis: 30d structured, 24h general
│       ├── circuit_breaker.py pybreaker: 5 failures → 30s open → fallback
│       ├── embedder.py      all-MiniLM-L6-v2 wrapper (local, 384-dim)
│       ├── vector_search.py pgvector top-k similarity (min 0.3)
│       ├── ingestion.py     PDF/PMC/StatPearls/PubMed ingestion → vector store
│       ├── pdf_verifier.py  Publisher signature validation
│       ├── byok.py          Fernet encryption for user LLM keys at rest
│       ├── drug_linker.py   Fuzzy matching + metaphone drug name normalization
│       ├── citation_validator.py Approved source list (NICE, AHA, FDA, WHO, etc.)
│       ├── safety_checker.py Content safety validation
│       └── json_repair.py   Fix malformed LLM JSON output
│
├── data/
│   ├── drug_dictionary.json FDA drug reference (~16KB)
│   └── indian_drugs.json    25 curated Indian drugs (nimesulide, domperidone, etc.)
│
└── migrations/              Alembic versioned migrations
    └── versions/
        ├── 001_initial_schema.py  users, documents, query_logs
        └── 002_vector_search.py   pgvector extension, embeddings
```

### Middleware Stack (execution order)
```
Request in →
  1. PayloadLimitMiddleware    (reject >64KB bodies)
  2. RateLimitMiddleware       (30/min per IP, pre-auth)
  3. ApiKeyAuthMiddleware      (validate JWT, decrypt BYOK key, attach to request state)
  4. PerKeyRateLimitMiddleware (10/min per authenticated key)
→ Route handler
```

### Model Routing
| Query Type | Model | Reason |
|-----------|-------|--------|
| Drug | `claude-haiku-4-5-20251001` | Structured FDA data only needs formatting |
| Disease | `claude-sonnet-4-20250514` | Must synthesize multiple society guidelines |
| Comparative | Sonnet | Complex multi-drug analysis |
| Procedure | Sonnet | Multi-step synthesis |
| General | Sonnet | Open-ended synthesis |

Controlled by `MODEL_ROUTING_ENABLED` env flag. If disabled, always uses Sonnet.

---

## Frontend Architecture

### Pages (App Router)
| Route | File | Purpose |
|-------|------|---------|
| `/` | `app/page.tsx` | Home with search bar, featured queries |
| `/login` | `app/login/page.tsx` | Login form |
| `/query?q=...` | `app/query/page.tsx` | Results with type-specific renderers |
| `/documents` | `app/documents/page.tsx` | PDF upload & management |
| `/settings` | `app/settings/page.tsx` | BYOK key management, user settings |

### API Routes (Next.js proxy layer)
| Route | Method | Proxies To |
|-------|--------|------------|
| `/api/query` | POST | `backend:8000/api/v1/query` |
| `/api/auth/login` | POST | `backend:8000/api/v1/auth/login` |
| `/api/auth/register` | POST | `backend:8000/api/v1/auth/register` |
| `/api/auth/llm-key` | POST | `backend:8000/api/v1/auth/llm-key` |
| `/api/documents` | GET | `backend:8000/api/v1/documents` |
| `/api/documents/upload` | POST | `backend:8000/api/v1/documents/upload` |
| `/api/documents/[id]` | GET/DELETE | `backend:8000/api/v1/documents/{id}` |

### Result Renderers
| Component | Query Type | Key Sections |
|-----------|-----------|--------------|
| `DrugInfoResult.tsx` | drug | Mechanism, indications, dosing, interactions, PK, monitoring |
| `DiseaseInfoResult.tsx` | disease | Etiology, pathophysiology, diagnostics, treatment lines, complications |
| `ComparativeResult.tsx` | comparative | Side-by-side table |
| `ProcedureResult.tsx` | procedure | Indications, steps, complications, guidelines |
| `EvidenceResult.tsx` | evidence | Supporting/opposing studies |
| `GeneralResult.tsx` | general | Summary, key points, related queries |

### Evidence System
Every claim carries:
- `loe` — Level of Evidence: I, II, III
- `cor` — Class of Recommendation: I, IIa, IIb, III-harm, III-no-benefit
- `source` — Must be an approved guideline/database
- `source_year` — Publication year
- `confidence` — 0–1 float; <0.6 triggers frontend warning

---

## Database Schema

### `users` table
| Column | Type | Notes |
|--------|------|-------|
| id | int PK | |
| key_id | varchar(64) UNIQUE | Public API key identifier |
| key_hash | varchar(128) | Hashed API key |
| email | varchar(255) | Optional |
| role | enum | admin / user / readonly |
| scopes | JSONB | Permission scopes |
| expires_at | timestamp | Key expiry (null = no expiry) |
| encrypted_llm_key | text | User's LLM key, Fernet-encrypted |
| llm_provider | varchar(20) | 'anthropic' or 'openai' |
| password_hash | varchar(255) | bcrypt hash |
| created_at / updated_at | timestamp | Auto-managed |

> **Planned additions**: username, country, position (med student/intern/resident/etc.), institute, preferences (JSONB), search_history, tier/subscription

### `documents` table
| Column | Type | Notes |
|--------|------|-------|
| id | int PK | |
| title | text | |
| source_type | varchar | 'pdf', 'pmc', 'pubmed', 'statpearls' |
| file_name | varchar | Original filename |
| pdf_size_bytes | int | |
| page_count | int | |
| uploaded_by_user_id | int FK→users | null = system |
| verified | bool | Publisher verified |
| publisher | varchar | Detected publisher |
| pmid / pmcid | varchar | For PubMed/PMC sources |
| chunks stored in `document_chunks` | | |

### `document_chunks` table
| Column | Type | Notes |
|--------|------|-------|
| id | int PK | |
| document_id | int FK | |
| content | text | Chunk text (~2000 chars) |
| chunk_index | int | Order within document |
| page_number | int | Source page |
| embedding | vector(384) | pgvector embedding |
| metadata_ | JSONB | section name, year, journal |

### `query_logs` table
| Column | Type | Notes |
|--------|------|-------|
| id | int PK | |
| user_id | int FK | |
| query_type | varchar | drug/disease/comparative/etc. |
| query_text | text | |
| response_json | JSONB | Full response ≤1MB |
| model_used | varchar | |
| tokens_used | int | |
| timestamp | datetime | |

---

## Authentication & BYOK

### Flow
```
Register → email + password → bcrypt hash → store in users table
Login → email + password → verify hash → issue JWT
Query → JWT in Authorization header → middleware decrypts BYOK key → passes to LLM factory
```

### BYOK (Bring Your Own Key)
- User enters their Anthropic or OpenAI API key in settings
- Key is encrypted with Fernet (symmetric) before storage
- `ENCRYPTION_KEY` env var is the master key (must be set in production)
- Decrypted only at LLM call time, never logged
- If user has no BYOK key: falls back to server keys (if configured) — **this should be removed** per new requirements

### Current Issue
`config.py` still has `anthropic_api_key` and `openrouter_api_key` as server-side keys. Per architecture goal, ALL LLM calls should use user's BYOK key. Server keys should be removed.

---

## PDF Ingestion Pipeline

```
User uploads PDF
  ↓
pdf_verifier.verify_pdf(bytes)   → check known publisher signatures
  ↓
pdfplumber.extract_text()        → text per page
  ↓
RecursiveCharacterTextSplitter   → ~2000 char chunks, 400 char overlap
  ↓
Embedder.embed_texts()           → all-MiniLM-L6-v2 (local, FREE, 384-dim)
  ↓
PostgreSQL + pgvector             → Document + DocumentChunks rows
```

**Cost estimation (planned):**
- Word count script runs before full ingestion
- Approx tokens = word_count × 1.33
- Approx cost displayed to user before they confirm upload
- Cost deducted from user's API key quota (per Anthropic pricing)

**Approved text sharing (planned):**
- If PDF is from verified publisher → user is notified it will be added to shared DB
- Only file path / metadata stored (not raw file) to save space
- Other users searching similar topics can benefit from verified chunks

---

## RAG Pipeline (Query Flow)

### Format-Mode (primary, ~80% of queries)
```
Fetched data (FDA/PubMed/RxNorm/etc.)
  → prompt_engine.build_format_prompt(data, query_type)
  → LLM call (user BYOK key): "format this data into the schema"
  → ~2048 output tokens (drugs) / ~4096 (diseases)
```

### Generate-Mode (fallback, all fetches failed)
```
  → prompt_engine.build_generate_prompt(query)
  → LLM call: "generate from your training data"
  → ~4096 output tokens
```

### Data Sources (parallel fetch)
See [External API Sources](#external-api-sources) below.

### Token Budget
| Mode | Model | Max Output Tokens |
|------|-------|-------------------|
| Format (drug) | Haiku | 2048 |
| Format (disease) | Sonnet | 4096 |
| Generate (fallback) | Sonnet | 4096 |

---

## External API Sources

| Source | Data Type | Rate Limit | API Key Needed |
|--------|----------|-----------|---------------|
| OpenFDA | Drug labels, adverse events | 240/min (no key) / 1000/min (key) | Optional (`OPENFDA_API_KEY`) |
| PubMed/NCBI | Guideline abstracts, PMC full text | 3/s (no key) / 10/s (key) | Optional (`PUBMED_API_KEY`) |
| RxNorm | Drug names, interactions | Unlimited | No |
| DailyMed | Drug labels | Unlimited | No |
| MedlinePlus | Patient-friendly drug info | Unlimited | No |
| Semantic Scholar | Research paper metadata | 100/s | No |
| MedIndia | Indian drug info (fallback) | Scrape | No |
| StatPearls/NCBI Bookshelf | Medical monographs | Via NCBI | Optional (`PUBMED_API_KEY`) |

**Indian drug fallback chain:**
`OpenFDA → DailyMed → indian_drugs.json (25 entries) → MedIndia scrape`

---

## Caching & Circuit Breaker

### Redis Cache
| Response Type | TTL | Key Format |
|--------------|-----|-----------|
| Structured (drug/disease/comparative/procedure) | 30 days | `hash(query + type + model_id)` |
| General | 24 hours | `hash(query + type + model_id)` |

### Circuit Breaker (pybreaker)
- 5 consecutive LLM failures → circuit opens
- 30-second open period → all requests fail-fast
- Falls back to OpenRouter when Claude circuit is open
- **Note**: OpenRouter fallback will be removed per BYOK-only architecture

---

## Environment Variables

See `.env.example` for full list. Key variables:

| Variable | Purpose | Required |
|----------|---------|---------|
| `POSTGRES_DB/USER/PASSWORD` | Database credentials | Yes |
| `INTERNAL_API_URL` | Frontend→Backend (Docker: `http://iatronix-backend:8000`) | Yes |
| `ENCRYPTION_KEY` | Fernet key for encrypting user LLM keys | Yes (prod) |
| `DATABASE_URL` | asyncpg connection string | Yes |
| `REDIS_URL` | Redis connection | Yes |
| `ALLOWED_ORIGINS` | CORS whitelist | Yes |
| `ANTHROPIC_API_KEY` | **(Planned removal)** Server fallback key | No |
| `OPENROUTER_API_KEY` | **(Planned removal)** OpenRouter fallback | No |
| `IATRONIX_API_KEY` | **(Planned removal)** Client auth key | No |
| `PUBMED_API_KEY` | Raises NCBI rate limit to 10/s | Optional |
| `OPENFDA_API_KEY` | Raises OpenFDA rate limit to 1000/min | Optional |
| `API_FETCH_ENABLED` | Toggle fetch-then-format mode | Default: true |
| `MODEL_ROUTING_ENABLED` | Toggle Haiku/Sonnet auto-routing | Default: true |
| `SENTRY_DSN` | Error tracking | Optional |

---

## File Index

### Files to Remove (confirmed unused)
| File/Dir | Reason |
|----------|--------|
| `traefik/` | Not used; Nginx on host handles proxying |
| `docker-compose.override.yml.bak` | Backup, not used |

### Files Using OpenRouter (to refactor for BYOK-only)
| File | Usage |
|------|-------|
| `backend/app/services/llm_factory.py` | Server OpenRouter fallback on lines 63-75 |
| `backend/app/config.py` | `openrouter_api_key`, `anthropic_api_key` server keys (lines 7-8) |
| `backend/app/services/circuit_breaker.py` | May reference OpenRouter fallback |

---

## Pending Changes / Roadmap

### Infrastructure
- [ ] Remove `traefik/` directory (confirmed: Nginx handles proxying)
- [ ] Add `nginx.conf` template to repo for easy domain migration
- [ ] Document how to change domain in Cloudflare + Nginx config
- [ ] Evaluate Vercel (frontend) + Supabase (DB) free tier for scale

### Backend — Architecture
- [ ] Remove server-side `ANTHROPIC_API_KEY` / `OPENROUTER_API_KEY` from config
- [ ] All LLM calls must use user BYOK key only; return error if no key set
- [ ] Fix AI parsing error (remove .env dependency for LLM calls)
- [ ] Replace local `all-MiniLM-L6-v2` embedder with Anthropic embeddings API (user key)
- [ ] Add word-count + cost estimation script before PDF ingestion
- [ ] Save only file path/metadata for approved texts (not raw bytes)
- [ ] Change scraper to fetch full article sections, not just abstract
- [ ] Chunk-based context: only feed relevant section to LLM per query
- [ ] Token minimization: LLM answers concise first, then expands with LOE/COR

### Backend — User Model
- [ ] Add to users table: `username`, `country`, `position` (enum), `institute`
- [ ] Add: `preferences` (JSONB), `search_history` (JSONB array or separate table)
- [ ] Add: `tier` enum (free/premium) for future monetization
- [ ] Add: `subscription_expires_at` timestamp

### Backend — Features
- [ ] Search history per user (stored in DB, synced across devices)
- [ ] "Use AI" toggle: if off, return raw scraped data with warning
- [ ] User settings persistence (stored in `preferences` JSONB, apply on login)
- [ ] Freemium gate: middleware checks user tier before premium features
- [ ] Rate limiting for free tier users

### Frontend — Pages
- [ ] Login page: eye toggle for password visibility
- [ ] Register flow: 2-step (account → profile + API keys)
- [ ] Multi-key support: Anthropic, OpenAI, Gemini with link to get each
- [ ] Search history sidebar
- [ ] Medical "thinking" animations during search
- [ ] "Use AI" / "Use documents" toggles on search page
- [ ] Documents page: approved text disclaimer
- [ ] Username dropdown: profile edit, delete account, settings, logout
- [ ] Settings page: preferences, API key update, dark/light toggle
- [ ] Dark mode default; smooth Apple-like transitions
- [ ] Fix dark/light mode hidden text issues

### Scalability (1000+ concurrent users)
- [ ] Investigate Vercel free tier for frontend (removes VPS CPU load)
- [ ] Investigate Supabase free tier for PostgreSQL (removes VPS RAM load)
- [ ] Increase uvicorn workers from 1 → multi-worker or use gunicorn
- [ ] Add connection pooling (PgBouncer) for PostgreSQL
- [ ] Redis rate limiting already in place; tune limits
- [ ] Consider background job queue (Celery/ARQ) for PDF ingestion
- [ ] CDN caching for static assets (Cloudflare already in place)
