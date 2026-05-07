# Iatronix — AI Agent Architecture Reference
# READ THIS FIRST before searching the codebase — it will save tokens.

## Server
- Public IPv4: 46.225.233.128
- IPv6: 2a01:4f8:1c19:acb7::1
- OS: Linux (Ubuntu), shell: bash
- Project root: /root/projects/med-ai-project/

## Domains
- med.kayomarz.com → PRODUCTION (main git branch, Docker prod compose)
- med.debkay.com   → DEVELOPMENT (dev git branch, Docker dev compose)

## Port Map
| Service            | Host port (nginx upstream) | Container port |
|--------------------|---------------------------|----------------|
| prod frontend      | 127.0.0.1:3200            | 3000 (Next.js) |
| prod backend       | 127.0.0.1:8200            | 8000 (FastAPI) |
| dev frontend       | 127.0.0.1:3201            | 3000           |
| dev backend        | 127.0.0.1:8201            | 8000           |
| waves backend      | 127.0.0.1:8300            | 8000 (FastAPI) |
| postgres           | internal only             | 5432           |
| redis (prod)       | internal only             | 6379           |
| redis (dev)        | internal only             | 6379           |

## Tech Stack
- Frontend: Next.js 15, React 19, TypeScript, Tailwind CSS v4, Lucide icons
- Backend: FastAPI, Python 3.12, async SQLAlchemy, pgvector, Redis
- LLM: Cerebras Llama 3.1 8B (default BYOK) + Anthropic Claude (optional BYOK) + LangChain + DSPy + LangGraph
- Auth: Firebase (client-side) + Firebase Admin SDK (server-side)
- CDN/proxy: Cloudflare → nginx → Docker containers

## Critical Frontend Files
| File | Purpose |
|------|---------|
| frontend/src/app/page.tsx | Homepage — search input, category cards |
| frontend/src/app/query/page.tsx | Results page — progressive BLUF + section rendering |
| frontend/src/app/about/page.tsx | About page |
| frontend/src/app/settings/page.tsx | Settings, API keys |
| frontend/src/app/waves/page.tsx | Waves tab (spirometry/ECG) |
| frontend/src/app/layout.tsx | Root layout + metadata + favicon |
| frontend/src/components/layout/Header.tsx | Nav header, logo, tabs |
| frontend/src/components/ui/SearchBar.tsx | Search input component |
| frontend/src/components/ui/SearchSuggestions.tsx | Autocomplete dropdown |
| frontend/src/components/ui/IatronixLogo.tsx | Favicon-based SVG logo |
| frontend/src/components/results/AdaptiveResultRenderer.tsx | Main result display; filters empty sections; `getSourceFallbackUrl()` helper for source-aware reference links (FDA → accessdata.fda.gov, NICE → nice.org.uk, ClinicalTrials → clinicaltrials.gov, etc.) |
| frontend/src/components/results/MermaidClient.tsx | Mermaid chart rendering (legacy — no longer used by FlowchartRenderer) |
| frontend/src/components/results/FlowchartRenderer.tsx | Clinical pathway flowcharts — custom CSS step flow, no Mermaid; branch steps rendered from "Condition → Outcome" format |
| frontend/src/components/providers/QueryProvider.tsx | Stream state — handles bluf/section_complete/token events; exposes streamingSectionTitles, streamingFlowcharts, streamingTables |
| frontend/src/components/waves/SpirometryUploader.tsx | Spirometry upload UI |
| frontend/src/hooks/useSearchSuggestions.ts | Debounced suggestion hook |
| frontend/src/lib/types.ts | TypeScript interfaces |
| frontend/src/lib/api.ts | API call utilities + StreamEvent union type |
| frontend/src/lib/constants.ts | App-wide constants |
| frontend/src/app/globals.css | CSS variables + Tailwind config |

## Critical Backend Files
| File | Purpose |
|------|---------|
| backend/app/services/rag_pipeline.py | Main RAG orchestrator — `process_query()` entry point; parallel + single-call paths |
| backend/app/services/model_registry.py | **Source of truth for all LLM models** — pricing, display names, provider mapping. Edit here to add/update models. |
| backend/app/api/v1/config_routes.py | `GET /api/v1/config/llm` — public endpoint serving model config to frontend (no auth required) |
| backend/app/services/rag_pipeline_stream.py | SSE streaming wrapper — emits stage/token/bluf/section_complete/done/error |
| backend/app/services/data_fetcher.py | Parallel fetch from 10+ medical APIs; includes `_cascade_pubmed_for_complex()` and `_fetch_comorbidities()` for complex multi-condition queries; new NCBI Books + ClinicalTrials.gov sources |
| backend/app/services/ranking.py | Evidence quality ranker — multi-factor scoring (study type, relevance, recency, fulltext, citations) with penalties for animal/off-population studies |
| backend/app/services/prompt_engine.py | All prompt builders: `build_adaptive_messages`, `build_bluf_only_messages`, `build_section_messages`, `build_complex_bluf_messages`, `build_complex_section_messages` (complex multi-condition queries) |
| backend/app/services/langgraph_search.py | LangGraph parallel search (fetch + vector + semantic_cache) |
| backend/app/services/dspy_lm.py | DSPy LM factory |
| backend/app/services/dspy_signatures.py | DSPy signature definitions |
| backend/app/schemas/query.py | Request/response Pydantic models |
| backend/app/routes/suggestions.py | /api/v1/suggestions endpoint |
| backend/app/config.py | All feature flags including PARALLEL_SECTIONS_ENABLED |
| backend/waves/main.py | Waves FastAPI app (spirometry/ECG) |
| backend/waves/scripts/spirometry_ai.py | Spirometry analysis using Claude vision |

## Deployment Files
| File | Purpose |
|------|---------|
| docker-compose.prod.yml | Production Docker services |
| docker-compose.dev.yml | Development Docker services |
| nginx/iatronix-prod.conf | Nginx config for med.kayomarz.com |
| nginx/iatronix-dev.conf | Nginx config for med.debkay.com |
| scripts/deploy-prod.sh | Deploy to production |
| scripts/deploy-dev.sh | Deploy to development |
| .env | Production environment variables (gitignored) |
| .env.dev | Development environment variables (gitignored) |
| .env.example | Template showing all required variables |
| DEPLOY_COMMANDS.md | All Linux commands for managing both envs (gitignored) |

## Key Environment Variables (see .env.example for full list)
- DATABASE_URL — PostgreSQL connection string (shared prod/dev DB)
- REDIS_URL — Redis URL (separate prod/dev)
- ENCRYPTION_KEY — Fernet key for BYOK key encryption
- SENTRY_DSN — Error tracking (optional)
- MODEL_CLASSIFY / MODEL_GENERATE — LLM model IDs
- CEREBRAS_DEFAULT_MODEL — Cerebras model ID (default: gpt-oss-120b); one-line change to switch models
- CEREBRAS_API_BASE — Cerebras API base URL (default: https://api.cerebras.ai/v1)
- Note: `NEXT_PUBLIC_CEREBRAS_MODEL` is removed; model identity is served via `GET /api/v1/config/llm`
- PARALLEL_SECTIONS_ENABLED — true/false; enables parallel section agent pipeline (default true on dev, false on prod until verified)

## API Route Patterns
- Frontend Next.js API routes: frontend/src/app/api/**
- Backend FastAPI routes: backend/app/routes/ (registered in backend/app/main.py)
- All frontend API routes proxy to backend at /api/v1/

## Medical APIs Used in data_fetcher.py
OpenFDA, DailyMed, RxNorm, PubMed/NCBI, PMC/StatPearls, NICE, MedlinePlus, Semantic Scholar, **NCBI Books** (StatPearls/GeneReviews), **ClinicalTrials.gov** (completed trial summaries)

### Evidence Ranking & Confidence Engine
- **New module:** `backend/app/services/ranking.py` — Multi-factor evidence scoring (study type, relevance, recency, fulltext availability, citations) with penalties for animal-only/off-population studies
- **Integration:** Articles scored after fetch, ranked by quality **before** LLM synthesis so highest-evidence studies survive the abstract budget
- **Recency tiers:** Recent (≤5y: 2.0), Current (6-15y: 1.0), Foundational (16-25y: 0.5), Obsolete (>25y: 0.0) — preserves landmark trials (HOPE 2000, ALLHAT 2002, ADVANCE 2008, etc.)
- **Confidence engine:** Replaces binary insufficient/sufficient with structured levels (low/moderate/high/strong) based on guideline + RCT + systematic review counts
- **LLM intent extraction:** 10 clinical intents (treatment, diagnosis, drug_dosing, drug_safety, drug_comparison, guideline, side_effect, contraindication, prognosis, general) — enables intent-driven routing and search strategy refinement

### Citation Validation & Source Attribution (May 2026)
- **Source rollup:** `FetchedData.data_sources` now populated from all sub-result sources (`DrugFetchResult.data_sources`, etc.), enabling accurate `DataSourceBadges` at bottom of results
- **NA literal replacement:** LLM-output "NA"/"N/A" source strings replaced with actual data source (e.g., "PubMed") or "Medical literature" fallback
- **Strict-mode procedure queries:** Citation validation now enforces strict source matching for `procedure` type (in addition to `complex`), preventing LLM from citing drugs/treatments not in fetched data block
- **Discontinued FDA filter:** OpenFDA label searches now filter by `product_type:"HUMAN PRESCRIPTION DRUG" OR "OTC DRUG"` to exclude historical/withdrawn drug entries
- **Prompt guardrails:** Explicit "never use NA/N/A as source" guidance in system prompts; LLM directed to use "Expert opinion" for unmatched sources
- **Non-PubMed source links** (May 2026): Multi-layer source attribution — FDA references link to accessdata.fda.gov, NICE to nice.org.uk, ClinicalTrials.gov trials to clinicaltrials.gov, etc. Backend (`url_builder.py`) enforces source-specific URL routing with Step 2 source guard (no PubMed match for non-PubMed sources) + Step 5 NCT ID lookup. Frontend (`AdaptiveResultRenderer.tsx`) uses source-aware fallback URLs when backend URL is null. Applies to both backend-injected references (`_inject_fetched_refs`) and LLM-provided references.
- **Expert Consensus normalization + Complete Reference List** (May 2026): Non-Anthropic models (GPT, Cerebras) frequently return `"Expert Consensus"` or `"Clinical Consensus"` variants. Pipeline: (1) Normalizes all consensus variants to canonical `"Expert opinion"`, (2) Builds complete reference list = LLM-cited refs + ALL fetched PubMed/NICE/FDA articles (deduped by PMID/title), (3) Assigns article-level URLs directly from PMID/NCT ID fields (no homepage fallbacks), (4) Filters unfixable expert-opinion refs when real linked refs exist. Result: UI shows every source consulted with correct article-level links (never homepages).

### Universal Source URL Flow (May 2026)
- **DrugFetchResult extended:** New field `label_url: Optional[str]` stores human-readable label page URL from fetch (DailyMed or FDA application)
- **DailyMed:** During fetch, `setid` extracted and URL constructed: `https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={setid}`
- **FDA labels:** Application number extracted from `openfda.application_number`, stripped to digits, and URL constructed: `https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo={app_num}`
- **NICE guidelines:** Each recommendation dict includes `url` field: `https://www.nice.org.uk/guidance/{item_id}`
- **Reference schemas:** All LLM prompt reference schemas now include `url` field. LLM instructed to copy URLs verbatim from data block
- **URL propagation:** URLs travel from fetch → format helper (data block text) → LLM reference field → url_builder validation → frontend render. No hardcoded patterns per source.
- **Backward compatible:** Any new source added to fetcher automatically gets correct links if: (1) fetch stores URL, (2) format helper includes `URL:` in text, (3) LLM copies verbatim, (4) domain added to allowlist

## Response Schema (query.py)
Union of: AdaptiveResponse | DrugResponse | DiseaseResponse | ComparativeResponse |
          ProcedureResponse | EvidenceResponse | GeneralResponse | DegradedResponse

All query types produce `AdaptiveResponse` with dynamic `sections[]` — no separate per-type renderers.

## SSE Streaming Events (rag_pipeline_stream.py)
| Event | Payload | When emitted |
|-------|---------|--------------|
| `stage` | `{stage: "classifying"\|"fetching"\|"generating"}` | Pipeline checkpoints |
| `token` | `{text: "..."}` | Single-call path — raw LLM tokens as they stream |
| `bluf` | `{headline, body, key_points, caveats, section_titles, flowcharts, tables}` | Parallel path — immediately after Phase 1 completes (includes flowcharts/tables so they render with BLUF) |
| `section_complete` | `{title, content_items, loe, cor, index}` | Parallel path — as each section agent finishes |
| `model_info` | `{is_fallback: bool, model: string}` | OpenRouter path — emitted before sections if primary Gemma model failed and fallback was used |
| `done` | `{result: QueryResponse}` | Always — full structured result for caching/latency |
| `error` | `{detail: "..."}` | On pipeline failure |

## OpenRouter OAuth PKCE Flow
Users can connect their OpenRouter account via OAuth PKCE to use Gemma 4 without manually pasting a key.

### New Routes
| Route | Auth | Purpose |
|-------|------|---------|
| `GET /api/v1/auth/openrouter/login` | Public | Initiates PKCE; redirects to openrouter.ai/auth |
| `GET /api/v1/auth/openrouter/callback` | Public | Receives code; exchanges for key; saves encrypted |
| `DELETE /api/v1/auth/openrouter/key` | Firebase auth | Disconnect OpenRouter |
| `GET /api/v1/auth/openrouter/status` | Firebase auth | Check if connected |

### Security
- `state` param: 32-byte `secrets.token_urlsafe()` stored in Redis with 600s TTL (CSRF protection)
- `code_verifier`: 32-byte `secrets.token_urlsafe()` — never logged; used in S256 challenge
- `openrouter_key` always encrypted with Fernet before DB write
- Login/callback routes are exempt from FirebaseAuthMiddleware

### New DB Column
`users.openrouter_key VARCHAR` — added via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` in lifespan

### New Env Vars
- `OPENROUTER_CALLBACK_BASE` — base URL for OAuth callback (e.g. `https://med.debkay.com`)
- `OPENROUTER_GEMMA_PRIMARY` — primary model (default: `google/gemma-4-31b-it`)
- `OPENROUTER_GEMMA_FALLBACK` — fallback model (default: `google/gemma-4-26b-a4b-it:free`)

## ChatService (chat_service.py)
`backend/app/services/chat_service.py` — primary/fallback routing for OpenRouter Gemma 4 queries.

When a user has an OAuth-linked `openrouter_key` (not a manually pasted key):
1. `process_query()` decrypts `user.openrouter_key` and uses it with `use_chat_service=True`
2. Default model is set to `openrouter_gemma_primary` if not specified
3. `_run_parallel_pipeline()` uses `chat_with_fallback()` for the BLUF call
4. On 402/429/500 from primary → falls back to `openrouter_gemma_fallback`
5. Emits `model_info` SSE event with `is_fallback=True` so frontend shows amber badge

## Cerebras BYOK (Default Provider — Paid Tier)

Cerebras provides an OpenAI-compatible API for open-source model inference.
Users bring their own Cerebras API key — stored per-provider in `users.cerebras_api_key` (Fernet-encrypted).

### LLM Provider Detection (llm_factory.py)
`get_provider(model_id)` routes requests by model ID prefix:
- `gpt-oss-*` → Cerebras (May 2026: fixed to route before OpenAI `gpt-` check)
- `llama-*`, `qwen-*`, `mistral-*` → Cerebras
- `gpt-`, `o1`, `o3` → OpenAI
- `gemini` → Google
- `/` (slash in ID) → OpenRouter
- Default → Anthropic

The `gpt-oss` prefix check must come before `gpt-` to avoid misrouting Cerebras models to OpenAI provider.

### Selected Model
`gpt-oss-120b` — Production default (3,000 tokens/sec, $0.35/$0.75 per 1M).
**To change the model:** update `CEREBRAS_DEFAULT_MODEL` in `.env` / `.env.dev` and rebuild.
No other code changes needed — the model name flows through `model_registry.py` and `GET /api/v1/config/llm`.

Cerebras client now respects the user's actual model_id rather than always using the config default, enabling true LLM agnosticism if other Cerebras models are available in future.

### Model Registry (source of truth)
`backend/app/services/model_registry.py` — single file listing all supported models, their providers,
display names, and pricing. Adding a new model only requires editing this file.

### Public Config Endpoint
`GET /api/v1/config/llm` — returns `{default_provider, providers: {cerebras: {...}, anthropic: {...}}}`.
Frontend reads this on page load; changing `CEREBRAS_DEFAULT_MODEL` in `.env` auto-propagates to UI.

### Paid Tier Limits (gpt-oss-120b)
| Quota | Limit |
|-------|-------|
| Max context | 32,768 tokens |
| Requests/min | 2,000 |
| Tokens/min | 2,000,000 |
| Input cost | $0.35 / 1M tokens |
| Output cost | $0.75 / 1M tokens |

### API Integration
- Uses `ChatOpenAI` (langchain_openai) with `base_url = settings.cerebras_api_base`
- Provider detected from model ID prefix: `llama*`, `qwen*`, `gpt-oss*`, `mistral*` → `cerebras`
- Prompt caching: Cerebras auto-caches by prefix match — no `cache_control` needed. Static system text first, dynamic last for best hit rate.

### BYOK Key Columns (per-provider, independent)
| Column | Provider |
|--------|----------|
| `users.cerebras_api_key` | Cerebras |
| `users.anthropic_api_key` | Anthropic |
| `users.openai_api_key` | OpenAI |
| `users.openrouter_key` | OpenRouter (OAuth) |
| `users.encrypted_llm_key` | Legacy fallback (preserved for backward compat) |

### New Env Vars
| Var | Default | Purpose |
|-----|---------|---------|
| `CEREBRAS_DEFAULT_MODEL` | `gpt-oss-120b` | Active model — change here to switch models |
| `CEREBRAS_API_BASE` | `https://api.cerebras.ai/v1` | API base URL |

### Cost vs Anthropic Haiku
| Provider | Per complex query | Annual (1000 queries/day) |
|----------|-------------------|--------------------------|
| Cerebras gpt-oss-120b | ~$0.015 | ~$5,475 |
| Anthropic Haiku 4.5 | ~$0.046 | ~$16,790 |
| **Savings** | **~3×** | **~$11,315/year** |

## Parallel Section Agent Pipeline (PARALLEL_SECTIONS_ENABLED=true)
```
process_query()
  │
  ├─ Phase 1: build_bluf_only_messages() → LLM call (4096 tokens)
  │    └─ Returns: bluf, section_titles, response_focus, related_topics, flowcharts[], tables[]
  │    └─ Emits: bluf SSE event immediately (with section_titles, flowcharts, tables)
  │
  └─ Phase 2: asyncio.gather() — one LLM call per section title (8192 tokens each)
       ├─ Section agent 1 → emits section_complete
       ├─ Section agent 2 → emits section_complete
       └─ Section agent N → emits section_complete
            ↓
       Merge sections + dedup references → AdaptiveResponse → done SSE event
       (flowcharts/tables from Phase 1 propagated into final AdaptiveResponse)
```

**Token budgets:** Phase 1 BLUF = 4096 tokens (`parallel_bluf_max_tokens`). Phase 2 sections = 8192 tokens each (`parallel_sections_max_tokens`).

**Quality preservation:** Each section agent receives full fetched API data + BLUF text for coherence + list of all other section titles to prevent overlap.

**Fallback:** If Phase 1 (BLUF call) fails, falls back to single-call path automatically.

**Per-claim citations:** Every `content_item` in section agents must have `source` (required), `pmid` (optional PubMed ID), `url` (optional direct URL). Source field determines URL routing: FDA → accessdata.fda.gov, NICE → nice.org.uk, ClinicalTrials → clinicaltrials.gov, etc. When `url` is null, frontend `ClaimRow` uses `getSourceFallbackUrl(source, pmid)` to generate source-appropriate fallback links instead of unconditional PubMed URLs.

## Comparative Drug Query — Drug Interactions
When `query_type == "comparative"` and `fetched_data.comparative_drug_data` has ≥ 2 entries, the prompt guidance automatically includes:
> "Drug Interactions Between Compared Agents (severity: major/moderate/minor, mechanism, management)"

Detection in `rag_pipeline.py`: `comparative_is_drug` flag passed to `build_adaptive_messages()` and `build_bluf_only_messages()`.

## Flowcharts (MermaidClient.tsx)
- Always use graph TD (never LR — breaks mobile)
- Use branching TD for decision trees, linear TD for sequential steps
- Wrapped in overflow-x:auto for mobile scrollability
- Custom dark theme: lineColor #94a3b8, primaryColor #1e293b

## Waves Tab
- Frontend: /waves page → SpirometryUploader.tsx + EcgComingSoon.tsx
- Backend: separate Docker service at port 8300, nginx proxies /api/waves/
- Uses user's stored Anthropic key (same key as main app) for Claude vision API
- Spirometry: Claude claude-sonnet-4-6 with base64 image → deterministic ATS/ERS logic
- ECG: Coming Soon placeholder

## Testing a Change
1. Edit code on dev branch
2. docker compose -f docker-compose.dev.yml up -d --build
3. Verify on https://med.debkay.com
4. If approved: git checkout main && git merge dev && bash scripts/deploy-prod.sh

## Files That Must Never Break
- backend/app/services/vector_store.py (pgvector)
- backend/app/middleware/ (rate limiting, circuit breaker)
- frontend/src/lib/firebase.ts (auth)
- docker-compose.prod.yml (production)
