# Iatronix — AI-Powered Medical Reference Platform

> Evidence-based answers for healthcare professionals. Every claim is graded with Level of Evidence, Class of Recommendation, and a source citation. Not a substitute for clinical judgment.

---

## What It Does

You type a medical question. Iatronix figures out what kind of question it is (drug, disease, comparison, procedure, evidence lookup, or a quick clinical summary), pulls authoritative data from free public APIs, feeds it to an AI model to structure — not invent — the answer, and returns a graded, cited response in under 30 seconds.

**Examples:**
- *"metformin dosing in CKD"* → drug profile with renal dose adjustments, contraindications, evidence grade
- *"heart failure management"* → staged treatment algorithm from NYHA class I–IV with society guideline citations
- *"lisinopril vs losartan"* → side-by-side comparison on efficacy, safety, dosing, cost, and guideline preference
- *"surviving sepsis"* → rapid clinical card: Sepsis-3 criteria, 1-hour bundle, antibiotic timing, fluid targets
- *"is metformin safe in pregnancy"* → evidence synthesis with supporting/opposing studies and PMID links

---

## Table of Contents

1. [System Architecture](#system-architecture)
2. [How a Query Flows Through the System](#how-a-query-flows-through-the-system)
3. [Services and What They Do](#services-and-what-they-do)
4. [Evidence Grading](#evidence-grading)
5. [Query Types](#query-types)
6. [AI Models and Cost](#ai-models-and-cost)
7. [PDF Uploads and Storage](#pdf-uploads-and-storage)
8. [Caching](#caching)
9. [Authentication and BYOK](#authentication-and-byok)
10. [Deployment: Docker, Nginx, and Cloudflare](#deployment-docker-nginx-and-cloudflare)
11. [Vercel (Optional Frontend Deployment)](#vercel-optional-frontend-deployment)
12. [Environment Variables](#environment-variables)
13. [Running Locally](#running-locally)
14. [Development Commands](#development-commands)
15. [Disclaimer and License](#disclaimer-and-license)

---

## System Architecture

```
Internet → Cloudflare CDN → Nginx → Docker Compose
                                         │
                    ┌────────────────────┼────────────────────┐
                    │                    │                     │
             Next.js 15            FastAPI + Python      PostgreSQL 16
             (frontend :3200)      (backend :8200)       + pgvector
                    │                    │
                    │              Redis 7 (cache)
                    │
             Optional: Vercel (frontend only, cloud deploy)
```

**Four Docker containers run together:**

| Container | Technology | Port | Purpose |
|-----------|-----------|------|---------|
| `iatronix-frontend` | Next.js 15 (TypeScript) | 3200 | UI: search, results, settings, PDF upload |
| `iatronix-backend` | FastAPI + Python 3.12 | 8200 | API: all logic, LLM calls, data fetching |
| `iatronix-db` | PostgreSQL 16 + pgvector | 5432 | Stores users, queries, PDF chunks, vector embeddings |
| `iatronix-redis` | Redis 7 | 6379 | Caches LLM responses so the same query doesn't cost twice |

---

## How a Query Flows Through the System

Here is exactly what happens when you type "metformin dosing" and press enter:

```
1.  Browser sends the query to Next.js frontend
2.  Frontend proxies it to FastAPI backend (via /api/v1/query)
3.  Middleware stack runs:
    a. Payload size check (max 64 KB) — blocks oversized requests
    b. IP rate limit (30 requests/minute per IP)
    c. API key authentication (checks X-API-Key header)
    d. Per-key rate limit (10 requests/minute per key)
4.  Query is classified: "drug" (score 0.92)
5.  Cache check in Redis: have we answered this before? → No
6.  Circuit breaker check: is the LLM currently failing? → No
7.  PARALLEL (runs at the same time):
    a. Fetch from OpenFDA drug label API
    b. Fetch from RxNorm (drug name normalisation)
    c. Fetch from DailyMed (full prescribing information)
    d. Fetch from PubMed (practice guidelines + systematic reviews)
    e. Fetch from MedlinePlus (patient-friendly drug summary)
    f. Vector search in PostgreSQL — find similar queries in uploaded PDFs
8.  All fetched data is merged into a structured context block
9.  Model routing: drug query → use claude-haiku-4-5 (cheaper, fast)
    Disease query → use claude-sonnet-4 (more reasoning needed)
10. Prompt is built:
    - If highlights intent detected ("surviving X", "approach to", "key points"):
        → Clinical pearls prompt — 5-8 actionable bullets with specific numbers
    - If full mode:
        → Format-mode prompt — LLM structures the pre-fetched data into schema
    - If all APIs failed:
        → Generate-mode prompt — LLM generates from training knowledge (more tokens)
11. LLM call (Claude or OpenRouter fallback)
12. JSON repair — fixes malformed JSON output automatically
13. JSON schema validation — checks all required fields are present
14. Citation validator — rejects sources not in the approved list
    (NICE, AHA/ACC, ESC, WHO, FDA, Cochrane, PubMed systematic reviews, UpToDate, etc.)
15. Safety check — flags responses that could cause patient harm
16. Drug linker — hyperlinks drug names to their reference pages
17. Response returned to frontend (rendered by typed React component)
18. ASYNC (non-blocking, runs after response is sent):
    a. Query logged to PostgreSQL
    b. New PubMed articles from step 7 embedded and stored in vector DB
```

The "fetch-then-format" approach (steps 7–10) means the AI is not inventing data — it's restructuring facts already retrieved from authoritative sources. This reduces hallucination and cuts token usage compared to pure generation.

---

## Services and What They Do

### Backend (`backend/app/services/`)

| File | What it does |
|------|-------------|
| `rag_pipeline.py` | The main orchestrator — calls everything in the right order |
| `query_classifier.py` | Pattern-matching classifier: drug / disease / comparative / procedure / evidence / general. Also detects "highlights" intent for clinical pearl responses |
| `source_router.py` | Entity extraction (zero AI) — pulls drug names, disease names from the query. Selects Haiku vs Sonnet based on query type |
| `data_fetcher.py` | Parallel async HTTP fetcher — OpenFDA, PubMed, RxNorm, DailyMed, MedlinePlus, Semantic Scholar, MedIndia. Falls back to `data/indian_drugs.json` for India-specific drugs |
| `prompt_engine.py` | Builds the prompt string. Format-mode (LLM structures pre-fetched data), generate-mode (LLM generates from scratch), highlights-mode (clinical pearls card) |
| `llm_factory.py` | Creates the LLM client (Claude or OpenAI-compatible). Uses user's BYOK key first, falls back to server key |
| `citation_validator.py` | Checks that every cited source is from an approved list of guidelines and databases |
| `ingestion.py` | Handles PDF uploads: extract text → split into chunks → embed → store in pgvector |
| `r2_storage.py` | Cloudflare R2 uploader (see PDF Storage section below) |
| `vector_search.py` | Semantic search over uploaded PDFs and indexed PubMed articles using pgvector |

### Frontend (`frontend/src/`)

| File/Directory | What it does |
|----------------|-------------|
| `app/page.tsx` | Home page with search bar |
| `app/query/page.tsx` | Results page — routes to the right renderer based on query type |
| `app/settings/page.tsx` | API key management, profile display, appearance toggle |
| `components/results/` | Typed renderers: `DrugResult`, `DiseaseResult`, `ComparativeResult`, `ProcedureResult`, `EvidenceResult` |
| `components/ui/ThinkingAnimation` | Animated indicator shown while the backend is processing |
| `hooks/useTheme.ts` | Dark/light mode — reads OS preference first, respects manual override, listens for OS changes in real time |
| `lib/types.ts` | TypeScript interfaces that mirror the backend Pydantic schemas |

---

## Evidence Grading

Every factual claim in a structured response carries four fields:

| Field | Meaning | Values |
|-------|---------|--------|
| `loe` | Level of Evidence — quality of the research behind the claim | I (RCT/meta-analysis), II (observational), III (expert opinion) |
| `cor` | Class of Recommendation — strength of the guideline recommendation | I (beneficial), IIa (probably beneficial), IIb (may be beneficial), III-harm (harmful), III-no-benefit |
| `source` | Which guideline or database the claim comes from | e.g., "AHA/ACC 2022", "NICE NG28", "FDA drug label" |
| `source_year` | Year of the guideline | e.g., 2022 |
| `confidence` | Model's confidence in the claim | 0.0–1.0 (low < 0.7 shows a warning in the UI) |

The frontend renders these with colour-coded badges. Claims with confidence below 0.7 show a caution indicator.

---

## Query Types

| Type | Detected by | What you get |
|------|-------------|-------------|
| **Drug** | Drug name, dosage keywords, pharmacology terms | Mechanism, indications, dosing table, interactions, pharmacokinetics, monitoring parameters |
| **Disease** | Disease/syndrome/disorder keywords, treatment/diagnosis keywords | Etiology, pathophysiology, diagnostic criteria, first/second/third-line treatment, complications, prognosis |
| **Comparative** | "vs", "versus", "compare", "difference between" | Side-by-side table: efficacy, safety, dosing, cost, guidelines, which to prefer and when |
| **Procedure** | "when to", "how to", intubation/catheter/lumbar puncture etc. | Indications, step-by-step, complications, contraindications, society guideline LOE/COR |
| **Evidence** | "is X given in", "can X be used for", "off-label", "evidence for" | Supporting studies, opposing studies, guideline status, PMIDs, final recommendation |
| **General / Highlights** | Everything else, or queries with "surviving", "approach to", "key points" | Clinical pearls card (5–8 bullets with specific numbers and thresholds) or general summary |

The classifier uses regex pattern scoring. If the confidence is below 0.7 the query falls back to "general". If comparative language is detected it always wins — comparative is the most specific type.

---

## AI Models and Cost

### Model Routing

| Query Type | Default Model | Why |
|-----------|--------------|-----|
| Drug | `claude-haiku-4-5-20251001` | FDA data is highly structured — Haiku just formats it. Very fast, very cheap. |
| Disease | `claude-sonnet-4-20250514` | Disease management requires synthesising multiple society guidelines. Sonnet reasons better. |
| Comparative | `claude-sonnet-4-20250514` | Cross-domain synthesis needed |
| Procedure | `claude-haiku-4-5-20251001` | Mostly structured checklist formatting |
| Evidence | `claude-haiku-4-5-20251001` | Study lookup and formatting |
| General/Highlights | `claude-haiku-4-5-20251001` | Concise output, minimal reasoning |

Turn off auto-routing with `MODEL_ROUTING_ENABLED=false` in `.env` — all queries will use the model the user selects.

### How Much Does a Query Cost?

Approximate cost per query using server-side keys (Anthropic pricing, March 2025):

| Scenario | Input tokens | Output tokens | Cost |
|----------|-------------|---------------|------|
| Drug query (Haiku, format-mode) | ~3,000 | ~2,048 | ~$0.003 |
| Disease query (Sonnet, format-mode) | ~4,000 | ~4,096 | ~$0.07 |
| Highlights query (Haiku) | ~1,500 | ~512 | ~$0.001 |
| Cached query | 0 | 0 | $0 |

Caching (30 days for structured, 24 hours for general) means the second identical query is free.

### BYOK — Bring Your Own Key

Users can add their own Anthropic or OpenAI API key in Settings. The key is encrypted with Fernet (AES-128-CBC) before storage. When a user has their own key set, all LLM calls for that user use their key — the server's key is not touched. This shifts the AI cost entirely to the user.

---

## PDF Uploads and Storage

### What Happens When You Upload a PDF

```
1.  Browser uploads PDF to /api/v1/documents/upload
2.  Size check: max 20 MB
3.  pdfplumber extracts all text
4.  Text is split into ~500-token chunks with 100-token overlap
    (langchain-text-splitters RecursiveCharacterTextSplitter)
5.  Each chunk is embedded with all-MiniLM-L6-v2 (runs locally, zero API cost)
    → 384-dimensional vector
6.  Chunks + vectors stored in PostgreSQL (pgvector)
7.  Document record created in database (status: pending_review)
8.  [OPTIONAL] Binary PDF uploaded to Cloudflare R2 if configured
```

### Where Are PDFs Stored?

**Text chunks (always):** PostgreSQL — the `document_chunks` table stores the extracted text and its vector embedding. This is what powers semantic search.

**Binary PDF file (optional):** Cloudflare R2 (Cloudflare's object storage, S3-compatible). This is only active when you set `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, and `R2_SECRET_ACCESS_KEY` in `.env`. If R2 is not configured, the PDF binary is not persisted anywhere — only the text chunks remain.

**Current default:** R2 is NOT configured out of the box. PDFs are chunked and searchable, but the original file is not downloadable after upload unless you configure R2.

### How Cloudflare R2 Works

R2 is Cloudflare's version of Amazon S3 — it stores files (objects) in a bucket, accessible via an S3-compatible API. The backend uses `boto3` (Amazon's AWS SDK) pointed at Cloudflare's endpoint instead of AWS:

```
boto3 → https://{account_id}.r2.cloudflarestorage.com → R2 bucket
```

When a public URL is configured (`R2_PUBLIC_URL`), uploaded files get a public HTTPS URL (e.g., from Cloudflare's CDN). Without a public URL, files are private and only accessible via the API.

**To enable R2:**
1. Create a Cloudflare account → R2 → Create bucket named `iatronix-documents`
2. Create an R2 API token with Object Read/Write permission
3. Add to `.env`:
   ```
   R2_ACCOUNT_ID=your_cloudflare_account_id
   R2_ACCESS_KEY_ID=your_r2_access_key
   R2_SECRET_ACCESS_KEY=your_r2_secret_key
   R2_BUCKET_NAME=iatronix-documents
   R2_PUBLIC_URL=https://pub-xxx.r2.dev  # optional, for public access
   ```

### PDF Lifecycle

- Non-approved PDFs (not verified by admin) are automatically deleted after 48 hours
- A cleanup job runs every 60 minutes to remove expired PDFs and their chunks
- Approved PDFs persist indefinitely and are searchable by all users

---

## Caching

Redis stores the complete LLM response so identical queries skip the AI call entirely.

**Cache key** = SHA256 hash of (query text + query type + model ID)

**TTL:**
- Structured responses (drug, disease, comparative, procedure, evidence): **30 days**
- General/highlights responses: **24 hours**

**Cache invalidation:** Set `FLUSH_REDIS=1` in `.env` and restart to flush all cached responses (useful after a model or prompt update).

---

## Authentication and BYOK

### How Login Works

Iatronix uses API-key-based authentication, not username/password sessions.

1. Register with email + password → backend creates an account and generates a random API key
2. Every subsequent request includes the API key in the `X-API-Key` header
3. Backend validates the key on every request (checked in middleware)

Passwords are hashed with bcrypt. API keys are random 32-byte hex strings stored in PostgreSQL.

### Bring Your Own Key (BYOK)

In Settings, users can enter their own Anthropic or OpenAI API key. The flow:

```
User enters key → encrypted with Fernet (AES-128-CBC, server-side ENCRYPTION_KEY)
                → stored in PostgreSQL as ciphertext
                → decrypted on each LLM request
                → sent to Anthropic/OpenAI API
```

The server's own LLM key (`ANTHROPIC_API_KEY` in `.env`) is the fallback — used when a user has no BYOK key set. If neither exists, the API returns HTTP 402 with a message to add a key.

---

## Deployment: Docker, Nginx, and Cloudflare

### Docker Compose

All four services run together in Docker. On a VPS:

```bash
git clone <repo>
cp .env.example .env
# Edit .env with your keys
docker compose build
docker compose up -d
```

The `backend/entrypoint.sh` script runs database migrations (`alembic upgrade head`) then starts Gunicorn with 4 UvicornWorker processes.

### Nginx as Reverse Proxy

Nginx sits in front of Docker and routes traffic:

```
:80/:443 → Nginx
  /api/*          → http://localhost:8200  (FastAPI backend)
  everything else → http://localhost:3200  (Next.js frontend)
```

Nginx also handles SSL termination (HTTPS certificates from Let's Encrypt or Cloudflare origin certs).

**Simple Nginx config example:**
```nginx
server {
    listen 443 ssl;
    server_name yourapp.com;

    location /api/ {
        proxy_pass http://127.0.0.1:8200;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 130s;  # matches backend pipeline timeout
    }

    location / {
        proxy_pass http://127.0.0.1:3200;
        proxy_set_header Host $host;
    }
}
```

### Cloudflare

Cloudflare sits in front of Nginx and provides:

- **CDN** — caches static assets globally (Next.js JS/CSS bundles)
- **DDoS protection** — absorbs traffic spikes before they hit your VPS
- **SSL** — Cloudflare terminates HTTPS from the browser; Nginx-to-Cloudflare uses origin certificates
- **DNS** — manages A/CNAME records pointing to your VPS IP

**How it connects:**

```
User browser → Cloudflare edge (SSL, CDN, firewall)
             → Your VPS public IP (Cloudflare's IP in server logs)
             → Nginx (listens on :443)
             → Docker (backend :8200 or frontend :3200)
```

No code changes are needed in the app. The app just sees normal HTTP requests — Cloudflare handles everything outside.

---

## Vercel (Optional Frontend Deployment)

`frontend/vercel.json` is included for deploying **only the Next.js frontend** to Vercel's cloud while the backend stays on your VPS.

```json
{
  "regions": ["sin1", "bom1"],
  "env": {
    "INTERNAL_API_URL": "https://api.yourapp.com"
  }
}
```

- `sin1` = Vercel Singapore region
- `bom1` = Vercel Mumbai region
- `INTERNAL_API_URL` = your backend URL (FastAPI running on VPS)

With this setup:
- Frontend is globally distributed via Vercel CDN (fast page loads)
- Backend stays on your VPS (you control the data, LLM keys, database)
- The Next.js API route (`/app/api/query/route.ts`) proxies requests from Vercel to your backend

**This is optional.** By default everything runs in Docker on a single VPS — no Vercel needed.

---

## Environment Variables

Copy `.env.example` to `.env` and fill in these values:

### Required

| Variable | Example | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | `sk-ant-...` | Claude API key — used when no user BYOK key is set |
| `POSTGRES_PASSWORD` | `strongpassword` | PostgreSQL database password |
| `ENCRYPTION_KEY` | (Fernet key) | 32-byte URL-safe base64 key for encrypting BYOK keys. Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `IATRONIX_API_KEY` | `abc123...` | Master API key for the frontend to talk to the backend |

### Optional but Recommended

| Variable | Description |
|----------|-------------|
| `OPENROUTER_API_KEY` | Fallback LLM provider (circuit breaker triggers this) |
| `PUBMED_API_KEY` | NCBI key — raises PubMed rate limit from 3 to 10 requests/second |
| `OPENFDA_API_KEY` | OpenFDA key — raises rate limit from 40 to 1000 requests/minute |

### Optional R2 Storage

| Variable | Description |
|----------|-------------|
| `R2_ACCOUNT_ID` | Cloudflare account ID |
| `R2_ACCESS_KEY_ID` | R2 API token key ID |
| `R2_SECRET_ACCESS_KEY` | R2 API token secret |
| `R2_BUCKET_NAME` | R2 bucket name (default: `iatronix-documents`) |
| `R2_PUBLIC_URL` | Public CDN URL for bucket (optional) |

### Tuning

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL_ROUTING_ENABLED` | `true` | Auto-select Haiku vs Sonnet based on query type |
| `API_FETCH_ENABLED` | `true` | Use fetch-then-format mode (set false to skip API calls) |
| `FLUSH_REDIS` | `0` | Set to `1` on startup to clear cache (set back to `0` after) |
| `ALLOWED_ORIGINS` | `http://localhost:3100` | CORS origins (comma-separated for multiple) |
| `LOG_LEVEL` | `INFO` | Logging level |

---

## Running Locally

### Prerequisites

- Docker and Docker Compose
- Git

### Steps

```bash
# 1. Clone
git clone <repo>
cd med-ai-project

# 2. Configure
cp .env.example .env
# Open .env and set ANTHROPIC_API_KEY, POSTGRES_PASSWORD, ENCRYPTION_KEY, IATRONIX_API_KEY

# 3. Build and start
docker compose build
docker compose up -d

# 4. Check it's running
docker compose logs -f backend   # watch for "Application startup complete"

# 5. Open
# Frontend: http://localhost:3200
# Backend API docs: http://localhost:8200/docs
```

### First-time Setup

On first startup, Alembic migrations run automatically and create all tables. Register an account via the frontend — your API key is shown after registration.

### Rebuilding After Code Changes

```bash
docker compose build backend   # rebuild backend only
docker compose up -d           # recreate containers with new images
```

**Note:** `docker compose restart` does NOT pick up `.env` changes or rebuilt images. Always use `docker compose up -d` to apply changes.

---

## Development Commands

### Backend (Python)

```bash
cd backend

# Lint (check for errors)
ruff check app/

# Format (check only, no changes)
ruff format --check app/

# Format (apply changes)
ruff format app/

# Run migrations
alembic upgrade head

# Generate a new migration
alembic revision --autogenerate -m "description"
```

### Frontend (TypeScript)

```bash
cd frontend

# Install dependencies
npm ci

# Type check
npx tsc --noEmit

# Lint
npx next lint

# Production build (checks for errors)
npm run build

# Development server (with hot reload)
npm run dev
```

### Docker

```bash
cd med-ai-project

docker compose up -d          # Start all services
docker compose down           # Stop all services
docker compose build          # Rebuild all images
docker compose build backend  # Rebuild backend only
docker compose logs -f        # Follow all logs
docker compose logs -f backend # Follow backend logs only
docker compose ps             # Check running status
```

---

## Circuit Breaker and Fallback

The LLM call is wrapped in a circuit breaker (`pybreaker`):

- After **5 consecutive failures**, the circuit "opens" for **30 seconds**
- During the open state, requests immediately fail with an error (no waiting for timeout)
- When the circuit resets, one test request is allowed through; if it succeeds, the circuit closes
- If `OPENROUTER_API_KEY` is set, failed Claude calls fall back to OpenRouter automatically before the circuit opens

---

## Vector Search

Every query runs a semantic vector search in parallel with the API fetches:

1. The query text is embedded with `all-MiniLM-L6-v2` (384 dimensions, runs in-process, no API call)
2. pgvector finds the top 5 most similar document chunks by cosine similarity
3. Only chunks above 0.3 similarity threshold are included
4. Results are appended to the LLM context as additional reference material

The model downloads once on first startup to `/app/models/` inside the container. No external service needed.

---

## Data Sources (All Free)

| Source | What it provides |
|--------|-----------------|
| OpenFDA | Drug labels, adverse events, recalls |
| PubMed/NCBI | Practice guidelines, systematic reviews, clinical trials |
| PMC (PubMed Central) | Full-text articles including StatPearls monographs |
| RxNorm | Drug name normalisation and concept IDs |
| DailyMed | Full FDA prescribing information |
| MedlinePlus | Patient-friendly drug and condition summaries |
| Semantic Scholar | Academic paper metadata and citations |
| MedIndia | Indian drug information (supplementary) |
| `data/indian_drugs.json` | Curated local fallback for 25 India-specific drugs |

---

## Disclaimer and License

Iatronix is a clinical reference tool for **qualified healthcare professionals**. It is not a substitute for professional medical judgment, direct patient assessment, or primary literature review. Always verify critical decisions with primary sources and current institutional guidelines.

**Private. All rights reserved.**
