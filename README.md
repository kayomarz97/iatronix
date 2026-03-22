# Iatronix

AI-powered medical reference platform with evidence-based grading. Query drugs, diseases, procedures, or compare treatments — every claim is graded with Level of Evidence and Class of Recommendation.

## Features

- **Structured medical queries** — Drug info, disease management, procedure guidelines, clinical evidence synthesis, and head-to-head treatment comparisons
- **Evidence grading** — Every claim carries LOE (I–III), COR (I, IIa, IIb, III), source citation, and confidence level
- **Fetch-then-format pipeline** — Pulls authoritative data from free APIs (OpenFDA, PubMed, RxNorm, DailyMed, MedlinePlus) first, then uses the LLM only to format — not generate — knowledge
- **Vector knowledge base** — Local embeddings (all-MiniLM-L6-v2, zero API cost) with pgvector. Auto-indexes PMC full-text articles and StatPearls monographs on every query
- **PDF upload & verification** — Upload medical PDFs with auto-verification against known publishers (Elsevier, Springer, WHO, AHA, etc.). Verified PDFs become searchable by all users
- **BYOK (Bring Your Own Key)** — Users provide their own Claude or OpenAI API key, encrypted at rest with Fernet
- **Intent-aware answers** — Detects management, diagnosis, prognosis, or pathophysiology intent and scopes responses accordingly
- **Hyperlinked references** — All PMIDs link to PubMed, all DOIs link to doi.org
- **Circuit breaker + fallback** — Automatic failover between Claude and OpenRouter with cached degraded responses
- **Model routing** — Drug queries use Haiku (structured FDA data), disease queries use Sonnet (guideline synthesis)

## Query Types

| Type | Example | Output |
|------|---------|--------|
| Drug | "metformin dosing and interactions" | Mechanism, indications, dosing, interactions, PK, monitoring |
| Disease | "heart failure management" | Etiology, pathophysiology, diagnostics, treatment lines, complications |
| Comparative | "lisinopril vs losartan" | Side-by-side across efficacy, safety, dosing, cost, guidelines |
| Procedure | "when to change a central line" | Indications, steps, complications, society guidelines with LOE/COR |
| Evidence | "is Telmisartan given in CKD" | Supporting/opposing studies with PMIDs, recommendation, guideline status |
| General | anything else | Summary, key points, related drugs/conditions |

## Architecture

```
User query → classify → [parallel] API fetch + vector search + cache check
           → merge context → intent-aware prompt → LLM → JSON validation
           → citation check → safety check → hyperlink refs → response
           → [async] index fetched PubMed/PMC data into vector DB
```

Multi-container Docker stack: **PostgreSQL 16 + pgvector** | **Redis 7** | **FastAPI** (Python 3.12) | **Next.js 15** (TypeScript)

### Data Sources (all free)

OpenFDA, PubMed/PMC, StatPearls (NCBI Bookshelf), RxNorm, DailyMed, MedlinePlus, Semantic Scholar, user-uploaded PDFs

## Setup

```bash
cp .env.example .env
# Fill in: ANTHROPIC_API_KEY, POSTGRES_PASSWORD, ENCRYPTION_KEY

docker compose build
docker compose up -d
```

Set `FLUSH_REDIS=1` in `.env` for first deploy to clear old cache, then set back to `0`.

### Key Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key (server default) |
| `OPENROUTER_API_KEY` | No | Fallback LLM provider |
| `DATABASE_URL` | Yes | PostgreSQL asyncpg connection string |
| `REDIS_URL` | Yes | Redis connection |
| `ENCRYPTION_KEY` | Yes | Fernet key for BYOK encryption |
| `PUBMED_API_KEY` | No | NCBI key (raises rate limit to 10 req/s) |
| `OPENFDA_API_KEY` | No | OpenFDA key (raises rate limit to 1000 req/min) |

## Development

```bash
# Backend
cd backend && ruff check app/ && ruff format app/

# Frontend
cd frontend && npx tsc --noEmit && npx next lint && npm run build
```

## Disclaimer

Iatronix is a medical reference tool for healthcare professionals. It is not a substitute for professional medical judgment or direct patient care. Always verify with primary sources.

## License

Private. All rights reserved.
