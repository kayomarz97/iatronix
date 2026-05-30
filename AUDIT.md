# AUDIT.md — Iatronix Phase 1 Structured Audit

> **Purpose:** Read-only reconnaissance for the provider-agnostic refactor (see `Code_refactor.md`).
> **Branch:** `dev` · **HEAD at audit:** `f9abb3f` · **Checkpoint:** `ea457b9` (tag `pre-refactor-20260530`) · **Date:** 2026-05-30
> **Method:** 9 parallel read-only agents over 219 tracked files; every "dead/unused" claim grep-verified; **code is ground truth, docs treated as possibly stale.**

---

## 0. Executive summary — what the refactor must defeat

| # | Finding | Why it matters for the refactor |
|---|---------|--------------------------------|
| **A** | **Four overlapping, partly-divergent model catalogs** (`config.py` role fields + duplicate `cost_*` pricing; `model_registry._REGISTRY`; `schemas/models.AVAILABLE_MODELS`; frontend `modelRegistry.ts`/`QueryProvider.tsx`/`constants.ts`). | This is the core of Phase 3: all four must collapse into one `config/providers.yaml`. |
| **B** | **Provider identity is imperative, not data** — `llm_factory.get_provider()` guesses provider from model-id prefixes; `create_llm()`, `dspy_lm`, `byok`, `embedder`, `circuit_breaker`, `source_router`, `cost_estimator`, `rag_pipeline` all branch on `provider == "anthropic"` etc. | A YAML can supply metadata, but the dispatch tables must *read* it instead of string-comparing. |
| **C** | **Two correctness bugs surfaced:** (1) `ingestion.py:24` imports a non-existent `Embedder` → `ImportError`. (2) `backend/tests/test_dspy_comparison.py:~28` contains a **hardcoded API key** (committed secret). | (1) is a latent break; (2) violates the no-secrets rule — **rotate + remove**. Both pre-date the refactor. |
| **D** | **Medical-safety flag default mismatch:** `FAIL_CLOSED_EVIDENCE_ONLY` = `true` in `.env.example`/docs but `False` in `config.py:150`. The gate it controls is now **dead** (generate-mode removed in `f9abb3f`); grounding is enforced upstream by the Evidence Floor. | Reconcile the default; document that the Evidence Floor — not this flag — is now the grounding gate. |
| **E** | **One pre-existing LangGraph island already exists** (`run_search_graph` in `langgraph_search.py`); everything else is hand-rolled `asyncio.gather`/`await`. | Phase 6 extends an existing pattern, not a greenfield build. |
| **F** | **Cerebras prompt caching is byte-fragile** — it works only because `_STATIC_*` prefixes are constant and the concat order is static→data→dynamic. | Constraint: any prompt reorder silently kills Cerebras cache hits. Preserve verbatim. |
| **G** | **Dead code is concentrated in the frontend** (a superseded result-rendering layer + unused UI primitives + the whole Mermaid chain) plus leftover `scripts/log_*.txt` and a tracked `Iatronix (1).zip`. Backend is clean. | Phase 7 deletion set is well-bounded and low-risk. |

---

## 1. File Map

### 1.1 `backend/app/services/` (35 files)

| file | purpose |
|------|---------|
| `__init__.py` | Empty package marker. |
| `article_registry.py` | Per-query immutable registry of fetched articles; O(1) lookup by PMID/NCT/DOI/title/token; **guarantees** every entry has a validated article-level URL. Entry: `build_article_registry()`. |
| `byok.py` | BYOK key handling: Fernet encrypt/decrypt, masking, format + live validation against Anthropic/OpenAI. Keys never logged. |
| `cache.py` | Redis exact-match response cache: query normalization, versioned key, TTL-by-type, weekly bucket for guideline freshness. |
| `chat_service.py` | OpenRouter Gemma primary/fallback chain (paid Gemma 4 → free Gemma 4 → free Llama 3.3); advances on 402/429/500. |
| `circuit_breaker.py` | pybreaker breakers per provider (anthropic/openai) + per-provider reset timeouts; `is_provider_available()`. |
| `citation_validator.py` | Validates claims/citations against approved-source allowlist + actually-fetched sources; returns warnings. |
| `cost_estimator.py` | Pre-op cost/scope estimate (PDF ingestion + query). **Always assumes Haiku**, reads divergent `config.cost_haiku_*`. |
| `data_fetcher.py` | Core parallel async fetcher of free medical APIs (FDA, RxNorm, ChEMBL/PubChem/EMA/WHO, PubMed + snowball); defines `FetchedData`. |
| `drug_linker.py` | Detects drug mentions in response text (exact + fuzzy Levenshtein/double-metaphone) → linkable `TextNode`s. |
| `dspy_lm.py` | `get_dspy_lm()` — builds `dspy.LM` per model/provider with litellm prefix + provider api_base. |
| `dspy_signatures.py` | DSPy `Signature` defs for query analysis + structured medical response. |
| `embedder.py` | BYOK embeddings: `get_langchain_embedder()` (OpenAI/Google/Voyage), `embed_query`, `embed_texts`. **No `Embedder` class** (see §3 bug). |
| `evidence_floor.py` | `has_minimum_evidence()` + `ensure_evidence()` (5 progressive broadening strategies, 2.5s each) → raises `EvidenceFloorError`. The grounding gate. |
| `ingestion.py` | Document ingestion (PDF, PMC, StatPearls, PubMed) → chunk → embed → pgvector. **Broken import of `Embedder` (`:24`).** |
| `json_repair.py` | Robust LLM-JSON parse: strip fences → orjson → `json_repair` fallback. |
| `langgraph_search.py` | **The one existing LangGraph graph** (`run_search_graph`): fetch + vector + semantic-cache nodes concurrently over `SearchState`. |
| `llm_factory.py` | `create_llm()` (LangChain Anthropic/OpenAI/OpenRouter/Cerebras); `get_provider()` prefix routing; error mapping. |
| `model_registry.py` | `_REGISTRY` dict — id→provider/display/pricing/cache/speed. Self-labeled "add models here only" but **already out of sync**. |
| `pdf_verifier.py` | Auto-verifies uploaded PDFs against known publishers (metadata/DOI/ISBN). |
| `prompt_engine.py` | Central prompt builder; `build_ref_map()` defines cached prefix bytes; `_STATIC_*` constants (Cerebras cache); all message builders. |
| `query_classifier.py` | `classify_query_llm` → one of drug/disease/comparative/procedure/evidence/complex; regex/no-LLM fallback + intent. |
| `r2_storage.py` | Cloudflare R2 (boto3 S3) PDF storage; async wrappers. |
| `rag_pipeline.py` | **Main orchestrator** — `process_query()` at `:2636`; rank/assess/expand/synthesize/ground/validate/log. ~3,700 lines. |
| `rag_pipeline_stream.py` | SSE wrapper (`stream_query`) emitting stage/token/bluf/section_complete/done/error. |
| `ranking.py` | Evidence ranking by study type/relevance/recency/fulltext/citations; animal/off-population penalties. |
| `safety_checker.py` | `check_safety()` — flags high-risk drugs + contraindication pairs. |
| `scraping_response.py` | Builds `GeneralResponse` from raw API data with **no LLM** (`source_mode="scraping"`). |
| `semantic_cache.py` | pgvector semantic cache + stale-while-revalidate; `is_stale`/`is_cache_hit` helpers. |
| `source_router.py` | `route_query`/`extract_entities` — fallback routing + model-tier (Haiku primary / Sonnet fallback). |
| `spirometry_ai.py` | Waves vision path: **module-level `MODEL_ID="claude-sonnet-4-6"`, raw `anthropic` SDK — bypasses `llm_factory`.** |
| `stance_neutralizer.py` | `neutralize_query()` — strips stance words → neutral clinical question; LLM-primary + regex fallback. |
| `url_builder.py` | Deterministic, allowlist-constrained URL enrichment from PMID/DOI/source; LLM never trusted for URLs. |
| `user_service.py` | `get_or_create_user()` from Firebase UID/email. |
| `vector_search.py` | pgvector cosine search over `document_chunks` (HNSW) with BYOK embeddings; verified/uploader visibility. |

### 1.2 Backend (non-services, 47 non-test files + 18 tests)

**`app/` root:** `main.py` (FastAPI entrypoint: lifespan, CORS, router registration, middleware, Sentry) · `config.py` (`BaseSettings` — central env config) · `__init__.py`.

**`api/v1/` (13 route modules):** `auth_routes.py` (auth + BYOK key mgmt) · `config_routes.py` (`/config/llm` — exposes cerebras+anthropic only) · `documents.py` · `health.py` · `history.py` · `models.py` (`/models` from `AVAILABLE_MODELS`) · `openrouter_oauth.py` (PKCE) · `query.py` (core query/stream) · `service_keys.py` (NCBI/PMC/openFDA keys) · `suggestions.py` · `version.py` · `waves.py` (**requires anthropic provider**).

**`core/`:** `auth.py` (`generate_api_key` `iatx.<id>.<secret>`, bcrypt verify).
**`db/`:** `session.py` (async engine) · `init_db.py` (`SELECT 1` + cache tables).
**`middleware/`:** `firebase_auth.py` · `payload_limit.py` · `rate_limit.py` (Redis + in-memory fallback).
**`models/` (ORM):** `base.py` · `document.py` (+ `DocumentChunk`, pgvector) · `query_audit.py` · `query_cache.py` · `query_log.py` · `search_history.py` · `service_key.py` · `user.py` (**one nullable BYOK column per provider**).
**`schemas/`:** `auth.py` (provider `Literal` enums) · `models.py` (`AVAILABLE_MODELS` — 3rd catalog) · `query.py` (`QueryRequest/Response`, `EvidencedClaim`; default `model_id` hardcoded `:255`).
**`migrations/`:** 001–007 + `e325edba0af9` (branch sits 005→e325→006→007); `env.py`.
**`tests/` (18):** citation grounding, evidence floor, generate-mode lockout, stance, prompt-injection, registry, semantic cache, milestone `test_m1`–`m3b`, langgraph wiring, dspy comparison (**standalone benchmark w/ hardcoded key**), `integration/test_rag_pipeline.py`.

> **Stale doc note:** `backend/waves/` directory **does not exist** — the only waves file is `app/api/v1/waves.py`. `AGENT_ARCHITECTURE.md` references `backend/waves/main.py` + `backend/waves/scripts/spirometry_ai.py`; actual file is `app/services/spirometry_ai.py`.

### 1.3 Frontend `frontend/src/` (65 files)

**`app/` pages:** `layout.tsx` · `page.tsx` (home) · `about/page.tsx` **[PROVIDER-HARDCODE: prose "GPT-OSS 120B via Cerebras"/"Claude"]** · `query/page.tsx` · `login/page.tsx` · `register/page.tsx` **[PROVIDER-HARDCODE: anthropic+openai tabs]** · `settings/page.tsx` **[PROVIDER-HARDCODE: cerebras+anthropic cards, model names, key placeholders]** · `documents/page.tsx` · `waves/page.tsx` · `globals.css` · `favicon.svg`.
**`app/api/` proxy routes (12):** query, query/stream, suggestions, history(+[id]), documents(+[id], upload), auth/llm-key, service-keys(+[service]), waves/spirometry — all target `INTERNAL_API_URL`.
**`components/`:** layout (Footer, Header, **MobileNav — dead**) · providers (Auth, PostHog, Query) · results (AdaptiveResultRenderer = the live one; **ClaimItem, EvidenceBadge, ReferenceList, TruncatedList, MermaidClient, MermaidRenderer — dead**; FlowchartRenderer, TableRenderer, ResultChrome, DisclaimerBanner live) · ui (**Accordion, Button, Skeleton, ThinkingAnimation — dead**; Badge, Card, IatronixLogo, PasswordInput, SearchBar, SearchHistorySidebar, SearchSuggestions, TetrisModal live) · waves (EcgComingSoon, SpirometryUploader) · LoadingScreen, ServiceKeyManager.
**`hooks/`:** useSearchHistory, useSearchSuggestions, useTheme.
**`lib/`:** `api.ts` · `constants.ts` **[PROVIDER-HARDCODE: `DEFAULT_PROVIDER="cerebras"`]** · `firebase.ts` · `formatters.ts` (**`confidenceColor`/`severityColor` dead**) · `modelRegistry.ts` **[PROVIDER-HARDCODE: fallback catalog]** · `types.ts`.

---

## 2. Provider / Model Touch-Points (the collapse list → `config/providers.yaml`)

**De-facto sources of truth today = 4 catalogs + scattered dispatch code.** Every row below is a place a provider/model string is hardcoded.

| # | file:loc | kind | layer | what's hardcoded / why it resists single-file config |
|---|----------|------|-------|------------------------------------------------------|
| 1 | `config.py:114-137` | model-id | config | One pydantic field per role: `model_haiku/sonnet/classify/generate`, `openai/openrouter/cerebras` defaults, 3-model gemma chain. Role→model belongs in YAML. |
| 2 | `config.py:120,124-136` | base-url | config | `openrouter_api_base/oauth_url/token_url`, `cerebras_api_base` as scalar settings, not keyed by provider. |
| 3 | `config.py:16,216-219` | pricing | config | **Second pricing block** (`cost_haiku_* 0.25/1.25`, `cost_sonnet_* 3.0/15.0`) that **disagrees** with registry (0.80/4.00). Also `embedding_model`. |
| 4 | `llm_factory.py:50-66` | routing | backend | `get_provider()` guesses provider from id prefix (`gpt-oss`→cerebras **before** `gpt-`→openai; `/`→openrouter; `gemini`→gemini; else anthropic). |
| 5 | `llm_factory.py:20-47,96-154` | provider | backend | `create_llm()` hardwires LangChain client class + base_url + retries per provider; Anthropic-specific error strings. |
| 6 | `model_registry.py:5-24` | pricing | backend | `_REGISTRY` — the real catalog; **missing** gpt-4o-mini/gemini/openrouter-gemma. The primary thing YAML replaces. |
| 7 | `schemas/models.py:11-42` | model-id | backend | `AVAILABLE_MODELS` — **3rd list**; advertises `opus` + `gemini-flash-1.5(-8b)` that exist in no other file → `/api/v1/models` can return unroutable models. |
| 8 | `config_routes.py:8-20` | routing | backend | `/config/llm` hardcodes that FE sees only `{cerebras, anthropic}` and default=`cerebras`. |
| 9 | `source_router.py:137-145` | routing | backend | Haiku-primary/Sonnet-fallback tier policy, Anthropic-specific. |
| 10 | `chat_service.py:49-61` | routing | backend | OpenRouter 3-model fallback chain pinned to `provider="openrouter"`. |
| 11 | `rag_pipeline.py:971-981` | model-id | backend | `_model_tier`: capability from substring (`opus`→3/`sonnet`→2/`haiku`→1; non-Anthropic→2). |
| 12 | `rag_pipeline.py:2031-2056,2729-2778` | routing | backend | `_default/_normalize_model_for_provider` branch per provider (overlaps llm_factory + source_router). |
| 13 | `rag_pipeline.py:1101-2426,3332-3470` | routing | backend | Prompt-cache strategy branches on `provider=="anthropic"` vs Cerebras/others. |
| 14 | `rag_pipeline.py:2672-2690` | key-column | backend | provider→DB-column map + preference order `(cerebras, anthropic, openai)`. |
| 15 | `dspy_lm.py:15-28` | routing | backend | litellm prefix (`anthropic/` vs `openai/`) + per-provider api_base. |
| 16 | `byok.py:23-176` | base-url | backend | per-provider validate URLs + **hardcoded probe model `claude-haiku-4-5`** + Anthropic API version. |
| 17 | `spirometry_ai.py:42,50-61` | model-id | backend | `MODEL_ID="claude-sonnet-4-6"`, **raw anthropic SDK, bypasses llm_factory** (vision role). |
| 18 | `cost_estimator.py:34-43` | pricing | backend | always-Haiku + reads the divergent `cost_haiku_*`. |
| 19 | `embedder.py:25-54` | model-id | backend | embedding model per provider (`text-embedding-3-small`/`text-embedding-004`/`voyage-3`); **Voyage is a hidden provider not in registry**. |
| 20 | `auth_routes.py:166-265` | provider | backend | allowed-provider allowlist + provider→column map. |
| 21 | `schemas/auth.py:83-99` | provider | backend | `Literal["anthropic","cerebras","openai","openrouter"]` freezes the set at schema layer. |
| 22 | `models/user.py:52-55` | key-column | backend | **one nullable column per provider** (`gemini/anthropic/openrouter/cerebras` key). **Hardest to collapse — needs a migration.** |
| 23 | `circuit_breaker.py:17-40` | provider | backend | named `anthropic`/`openai` breakers + per-provider reset; cerebras/openrouter fall through to anthropic breaker. |
| 24 | `query.py:9,74` | provider | backend | debug header hardwires the two named breakers. |
| 25 | `schemas/query.py:255` | model-id | backend | request default `model_id="claude-haiku-4-5-20251001"`. |
| 26 | `waves.py:29-67` | provider | backend | feature requires `provider=="anthropic"` (vision capability in code, not config). |
| 27 | `frontend/lib/modelRegistry.ts:1,32-36` | model-id | frontend | fallback catalog (ids/display/pricing) + `LLMProvider` union freezes set. |
| 28 | `frontend/QueryProvider.tsx:20-225` | model-id | frontend | `PROVIDER_DEFAULT_MODELS`, default name string, bare-fallback `gpt-oss-120b`, label map. |
| 29 | `frontend/lib/constants.ts:3` | provider | frontend | `DEFAULT_PROVIDER="cerebras"` + union. |
| 30 | `frontend/settings/page.tsx:21-639` | display | frontend | which 2 providers render BYOK cards + descriptions + `csk-`/`sk-ant-` placeholders. |
| 31 | `frontend/register/page.tsx:66-584` | provider | frontend | **different** provider pair (anthropic+openai) — inconsistent across pages. |
| 32 | `frontend/about/page.tsx:14-107` | display | frontend | marketing copy names default model + provider URLs. |
| 33 | `.env.example:15-37` | model-id | env | mirrors the `MODEL_*` role fields (one var per role). |
| 34 | `scripts/run_quality_tests.py:224-233` | model-id | config | pins `gpt-oss-120b` + `X-Cerebras-Key` header. |

**What `config/providers.yaml` must own:** a per-provider record `{name, client kind/class, base_url, oauth endpoints, key-format/placeholder, validation endpoint + probe model, enabled flag, default model, embedding model, supports_caching + strategy, supports_vision}` and a per-model record `{id, provider, display, input/output/cache pricing, capability tier, role tags}` — replacing items 1,3,6,7 and the frontend fallbacks, and *driving* (not deleting) the dispatch in items 4,5,11–24. **Prefix-based `get_provider()` and per-provider DB columns cannot become pure data** — they must read YAML metadata, and key columns ideally consolidate behind one keyed store (migration).

**Correctness flags found while auditing:** (a) Haiku pricing differs `config.py` (0.25/1.25) vs `model_registry.py` (0.80/4.00); (b) `AVAILABLE_MODELS` advertises models the backend can't price or route.

---

## 3. Latent Bugs & Secrets surfaced (not in any plan)

1. **Broken import — `ingestion.py:24`:** `from app.services.embedder import Embedder` — `embedder.py` exports only `get_langchain_embedder`/`embed_query`/`embed_texts`, **no `Embedder`**. Any code path importing `ingestion` raises `ImportError`. Likely masked because document-ingestion is rarely exercised. **Fix:** import the real symbol or restore the class.
2. **Committed secret — `backend/tests/test_dspy_comparison.py:~28`:** hardcoded API key in a standalone benchmark (not a pytest test; needs two live servers). **Action:** remove the key, **rotate it**, and either delete the file or move it to a `.gitignore`d scratch location. Violates the project no-secrets rule.
3. **Tracked archive — `Iatronix (1).zip`** (30 KB, repo root): a source snapshot checked into git. Now covered by the new `*.zip` gitignore but already in history; safe-delete candidate (history rewrite out of scope).

---

## 4. Env Toggle Inventory (`.env.example` → code)

**34 vars classified.** 28 USED in app code, 1 used at shell/deploy level, 4 UNUSED-by-app, 1 fully dead.

| var | status | evidence |
|-----|--------|----------|
| `IATRONIX_API_KEY` | **UNUSED (dead)** | No reader anywhere; FE uses literal string `"iatronix_api_key"` as a localStorage key, not the env var. Docs mark "planned removal". |
| `DATABASE_URL` | USED | `db/session.py:6`. |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | **UNUSED-by-app** | Infra-only: consumed by pgvector container + healthcheck; app authenticates via `DATABASE_URL`. **Keep** (infra needs them). |
| `REDIS_URL` | USED | `main.py:83` + 4 others. |
| `INTERNAL_API_URL` | USED | `next.config.ts:4` + ~12 FE proxy routes. |
| `ALLOWED_ORIGINS` | USED | `main.py:181` (CORS split). |
| `SENTRY_DSN` | USED | `main.py:78` (gated). |
| `PROMPT_VERSION` | USED | `cache.py:30` (cache key). |
| `API_FETCH_ENABLED` | USED | `rag_pipeline.py:2946`. |
| `MODEL_ROUTING_ENABLED` | USED | `rag_pipeline.py:3185`. |
| `MODEL_HAIKU` | USED | `config_routes.py:13` + 7 others. |
| `MODEL_SONNET` | USED | `source_router.py:144`. |
| `MODEL_CLASSIFY` | USED | `rag_pipeline.py:2778`. |
| `MODEL_GENERATE` | USED | `source_router.py:137` + 2. |
| `DSPY_ENABLED` | USED | `rag_pipeline.py:2081` (compose hard-sets `"true"`, overriding `.env`). |
| `ADAPTIVE_SECOND_PASS_ENABLED` | USED | `rag_pipeline.py:729`. |
| `FAIL_CLOSED_EVIDENCE_ONLY` | USED | `rag_pipeline.py:3123`. **⚠ DEFAULT MISMATCH:** `.env.example`/docs = `true`, `config.py:150` code default = `False`. (Gate is now dead — see §6.) |
| `SEMANTIC_CACHE_ENABLED` | USED | `semantic_cache.py:61`. **⚠ DOC CONTRADICTION:** `.env.example` + code default = `True`, but `AGENT_INTEGRATION_GUIDE.md:316,656` say `false`. Doc stale. |
| `SEMANTIC_CACHE_THRESHOLD` | USED | `semantic_cache.py:94` (=0.92, matches default). |
| `ENCRYPTION_KEY` | USED | `service_keys.py:15` (Fernet). |
| `FLUSH_REDIS` | **USED (shell)** | `backend/entrypoint.sh:8` — deploy-time Redis flush, not pydantic. |
| `PARALLEL_SECTIONS_ENABLED` | USED | `rag_pipeline.py:3244`. |
| `CITATION_REF_TOKENS_ENABLED` | USED | `prompt_engine.py:698` + 4. |
| `PUBMED_EXPANSION_ENABLED` | USED | `rag_pipeline.py:2137`. |
| `SNOWBALL_ENABLED` | USED | `data_fetcher.py:1041`. |
| `SNOWBALL_MAX_REFS` | USED | `data_fetcher.py:1043` (=15). |
| `OPENROUTER_CALLBACK_BASE` | USED | `openrouter_oauth.py:69` (default empty — must set per-env). |
| `OPENROUTER_GEMMA_PRIMARY` | USED | `chat_service.py:50`. |
| `OPENROUTER_GEMMA_FALLBACK` | USED | `chat_service.py:51`. |
| `CEREBRAS_DEFAULT_MODEL` | USED | `config_routes.py:12` + 5. |
| `CEREBRAS_API_BASE` | USED | `llm_factory.py:142` (commented in example but code default effective). |

**Read in code but MISSING from `.env.example`** (should be added so the template is honest): `VECTOR_SEARCH_ENABLED`, `STANCE_NEUTRALIZER_ENABLED`, `REFERENCE_FILTER_V2_ENABLED`, `EVIDENCE_FLOOR_ENABLED`, `PUBMED_VECTOR_CACHE_ENABLED`, `RETRY_ON_SPARSE_ENABLED` (unused — see §6), `BYOK_ENABLED`, `LOG_LEVEL`, `GUNICORN_WORKERS` (entrypoint/compose), `FIREBASE_CREDENTIALS`, `R2_ACCOUNT_ID/ACCESS_KEY_ID/SECRET_ACCESS_KEY/BUCKET_NAME/PUBLIC_URL`, `PUBMED_API_KEY/OPENFDA_API_KEY/NICE_API_KEY`, `ANTHROPIC_API_KEY/OPENAI_API_KEY` (back-compat, unused), `OPENAI_DEFAULT_MODEL/OPENROUTER_DEFAULT_MODEL/OPENROUTER_API_BASE/OPENROUTER_META_FALLBACK/OPENROUTER_OAUTH_URL/OPENROUTER_TOKEN_URL`, and all FE `NEXT_PUBLIC_*` (Firebase config, PostHog, `ENABLE_OPENROUTER_OAUTH`, `ENABLE_LEGACY_ENGINE_TOGGLE`).

> **Phase 7 guidance:** only `IATRONIX_API_KEY` is safe to *remove* (fully dead). `POSTGRES_*` are infra (keep). Everything else is USED or should be *added* to the template. `RETRY_ON_SPARSE_ENABLED` gates dead code — flag as `UNCLEAR` pending decision.

---

## 5. Redundant / Dead Code Candidates (Phase 7 deletion gate)

**Backend is clean** — every low-import service module is genuinely invoked; `cache.py` (exact) and `semantic_cache.py` (vector) are complementary, not duplicates. Dead code is **frontend-concentrated**: a superseded result-rendering layer (`AdaptiveResultRenderer.tsx` defines its own inline `EvidenceBadge`/`ClaimRow`/`ReferenceRow`).

### 5a. Safe-to-delete (reachable=false, grep-verified zero live importers)

| path | lines | reason | confidence |
|------|-------|--------|-----------|
| `frontend/.../results/MermaidRenderer.tsx` | 1-9 | Never imported; superseded by `FlowchartRenderer`. | high |
| `frontend/.../results/MermaidClient.tsx` | 1-62 | Only consumer is dead `MermaidRenderer`; sole user of `mermaid` npm dep. | high |
| `frontend/.../results/ClaimItem.tsx` | 1-14 | Zero importers; superseded by inline `ClaimRow`. | high |
| `frontend/.../results/EvidenceBadge.tsx` | 1-55 | Imported only by dead `ClaimItem`; live code uses a different inline badge. | high |
| `frontend/.../results/ReferenceList.tsx` | 1-61 | Zero importers; refs rendered inline. | high |
| `frontend/.../results/TruncatedList.tsx` | 1-34 | Zero importers (orphans `TRUNCATION_LIMIT`). | high |
| `frontend/.../layout/MobileNav.tsx` | 1-22 | Zero importers; Header renders its own inline mobile menu. | high |
| `frontend/.../ui/Button.tsx` | 1-35 | Zero references. | high |
| `frontend/.../ui/Accordion.tsx` | 1-37 | Zero references. | high |
| `frontend/.../ui/ThinkingAnimation.tsx` | 1-144 | Zero references. | high |
| `frontend/.../ui/Skeleton.tsx` | 1-27 | Zero imports (only a code comment mentions it). | high |
| `frontend/.../lib/formatters.ts` | 6-28 | `confidenceColor` + `severityColor` never imported (keep `formatLatency`). | high |
| `scripts/log_backend.txt`, `log_cohesiveness.txt`, `log_frontend.txt`, `log_security.txt`, `log_speed.txt` | all | Leftover agent-run logs (Apr 15); unreferenced. | high |
| `Iatronix (1).zip` | all | Tracked archive snapshot; unreferenced (history rewrite out of scope — see §3). | high |
| `frontend/package.json` | 14 | `mermaid ^11.0.0` — unused once Mermaid chain deleted. Drop **after** confirming no re-enable plan. | medium |

### 5b. Reachable — DO NOT auto-delete (needs explicit decision)

| path | reason | confidence |
|------|--------|-----------|
| `backend/tests/test_dspy_comparison.py` | Runnable manual benchmark (not a pytest test); **contains a hardcoded key (§3)**. Confirm with owner + rotate key before deleting. | medium |
| `rag_pipeline.py:1174-1230, 2074-2131` | `_analyze_query_with_dspy` + `_rewrite_query` — **legacy 2-call path**, still reachable as the else-fallback (`:2825/:2831`) when merged `_analyze_and_expand_query` returns None. Keep unless fallback intentionally retired. | medium |
| `rag_pipeline.py:872-913` + `config.py:191` | `_is_critically_sparse` / `_adaptive_sparse_reasons` + `RETRY_ON_SPARSE_ENABLED` — **defined, zero callers**. Dead, but tied to a flag; confirm before removing (see §6). | medium |

---

## 6. Prompt-Caching Touch-Points

Two distinct things are called "cache": **LLM prompt-prefix caching** (token reuse inside the model API) and **application response caching** (skip the whole pipeline). All three synthesis paths build the same `(static_system, dynamic_system, data_block, user_text)` tuple and branch on `provider == "anthropic"`.

| layer | mechanism | file:line | refactor stance |
|-------|-----------|-----------|-----------------|
| **Cerebras** (prefix auto-cache) | Server auto-caches a stable prefix; **enforced purely by byte-identical `_STATIC_*` constants + static→data→dynamic concat order**. Hit read via `prompt_tokens_details.cached_tokens`. | `prompt_engine.py:271-281,850-862,522`; `rag_pipeline.py:2400-2426`; `article_registry.py:324` | **PRESERVE — load-bearing & fragile.** Any reorder/interpolation silently kills hits. |
| **Anthropic** (prompt caching) | `cache_control:{"type":"ephemeral"}` on `static_system` block + conditional on `data_block` (`>1024` / `>4096` chars). Dynamic block uncached. Read/write tokens accounted; registry has cache prices. | `rag_pipeline.py:2382-2399,1101-1124,3332-3349,3470-3492`; `model_registry.py:7-9` | **PRESERVE + clean up:** docstring `:2375` claims **1h TTL but none is set** (`"ttl":"1h"` absent); thresholds inconsistent (1024 vs 4096); logic duplicated across **3 paths** → consolidate behind one block-builder in the adapter. No `anthropic-beta` header set (relies on SDK GA). |
| **OpenAI / OpenRouter** | **No explicit code** — fall into the same `else` concat branch as Cerebras; benefit only from implicit upstream prefix caching. OpenRouter is opaque pass-through (`input/output=0.0`). | `llm_factory.py:121-136`; `rag_pipeline.py:2400` | Keep shared path; document as no-op caching. Optional telemetry/pricing later. |
| **Redis exact-match** (app response) | `v{prompt_version}:{model}:{type}:{sha256(norm_query)}`; weekly bucket for guideline types; 7d/24h TTL; fail-open; `cache_get_any_version` for circuit-open fallback. | `cache.py:12-92`; `config.py:86-87`; `rag_pipeline.py:2789,2897,2926,3723` | PRESERVE. Keep `prompt_version` in key so prompt refactors invalidate stale answers. |
| **Semantic cache** (pgvector + SWR) | embed query → cosine ≥ threshold over `query_cache` (filtered by type+model) → return **only if fresh** (`is_stale` gate); background revalidate. Runs inside `run_search_graph`. | `semantic_cache.py:27-204`; `langgraph_search.py:90-130`; `rag_pipeline.py:2969-3037,3726-3736`; `migrations/004` | PRESERVE. Fresh-only return is a medical-safety choice. |

> **Phase 4 contract:** the adapter's `apply_cache()` must (1) keep Cerebras byte-identical prefix ordering, (2) reproduce the Anthropic block-with-`cache_control` assembly, (3) no-op cleanly for OpenAI/OpenRouter/others. The two app-level caches are orthogonal and stay in the pipeline, not the adapter.

---

## 7. Pipeline Orchestration — the contract LangGraph must preserve

**Entry:** `process_query()` (`rag_pipeline.py:2636`), via `query.py:32` (stream) / `:70` (non-stream). One linear `await` chain with **4 internal `asyncio.gather` fan-outs + 1 existing LangGraph subgraph**.

### 7.1 Stages (as actually wired)
- **Stage 0 — Setup (`:2645-2765`):** BYOK key resolution (OpenRouter OAuth → per-provider columns → legacy `encrypted_llm_key`), service keys, model normalize, `detect_intent`.
- **Stage 1 — Analyze ∥ Cache-prefetch ∥ Stance (`:2782-2805`):** `gather(_analyze_and_expand_query, cache_get[speculative], neutralize_query)`. Neutral question → `retrieval_query`; original kept for cache keys. Legacy fallback `gather(_analyze_query_with_dspy, _rewrite_query)` at `:2824`.
- **Stage 2 — Type finalize + exact-cache short-circuit (`:2848-2941`):** resolve type (request→analysis→`classify_query_llm`), normalize unknown→`complex`, re-check cache, circuit-breaker check.
- **Stage 3 — Routing (`:2954-2964`):** `route_query()` (sync).
- **Stage 4 — Parallel retrieval (`:2969-2985`):** `run_search_graph()` = **the one existing LangGraph `StateGraph`** (`langgraph_search.py:116-135`): `fetch_node` (wait_for `api_fetch_timeout`) ∥ `vector_node` ∥ `semantic_cache_node`. Neutral query for fetch/vector, original for semantic cache.
- **Stage 5 — Evidence expansion + floor (`:3042-3089`):** `_expand_retrieval_if_needed()` → Pass 2 adaptive second pass (per-type `gather`) → Pass 3 Evidence Floor (`ensure_evidence`, 5 strategies × 2.5s) → rerank + recompute confidence. `EvidenceFloorError` caught `:3065` → `no_evidence`.
- **Stage 6 — Synthesis (`:3091-3530`):** `prompt_mode="format"` **hardcoded** (`:3092`). Three mutually-exclusive paths: parallel section pipeline (`_run_parallel_pipeline`, BLUF → `gather` over sections, Semaphore-bounded), chat_service 3-model fallback (OpenRouter OAuth), or single direct call (+ one-shot JSON-parse retry).
- **Stage 7 — Post-process (`:3532-3765`):** **load-bearing order** — `_resolve_ref_tokens` → `_title_rescue_pass` → `sanitize_response_pmids` → `_normalize_consensus_sources` → `_backfill_from_registry` → `attach_orphans_to_references` → `_quarantine_sourceless_items` → `to_reference_list()`. Then build → `validate_citations` → `check_safety` → drug-linker → audit log → costing → fire-and-forget `cache_set`/`semantic_cache_set`/`_log_search_history`.

### 7.2 Concurrency points
C1 `:2782` (analyze∥cache∥stance) · C2 `:2824` (legacy fallback) · **C3 `langgraph_search.py:123-130`** (fetch∥vector∥semantic) · C4–C9 `:747/757/775/782/795/838` (per-type second-pass fetches) · C10 `:2593` (section agents, Semaphore) · C11 `evidence_floor.py:177-234` (sequential, each wait_for-bounded — **not** gathered).

### 7.3 Short-circuits / `DegradedResponse` triggers
Exact-cache hit (`:2900`) · circuit-open+stale (`:2929`) · circuit-open no-cache (`:2935`) · **semantic-cache hit only if fresh** (`:3008`, stale falls through `:3021`) · **Evidence Floor exhausted → `no_evidence` (`:3065-3089`, code set `:3084`, raised `evidence_floor.py:250`)** · scraping mode (`:3096`) · parse failure (`:3514`) · 401/429/402 (`:3388-3424`) · build failure (`:3594`). `DegradedResponse` at `:2712,2938,3074,3128,3158,3394,3420,3524,3600`.

### 7.4 Dead branches (confirm before relying on them)
- **Generate-mode fully removed** (`f9abb3f`): `prompt_mode` always `"format"` (`:3092`). The **fail-closed gate (`:3123`) and hallucination guard (`:3143`) are now statically unreachable**. Grounding is enforced upstream by the Evidence Floor.
- **No sparse-response retry exists:** `_is_critically_sparse`/`_adaptive_sparse_reasons` + `RETRY_ON_SPARSE_ENABLED` have **zero callers**. The only post-gen retry is the single JSON-parse retry (`:3458-3500`). LangGraph must **not** model a sparse-retry node.

### 7.5 Timeouts / backoff to preserve **verbatim** (constraint #4)
`api_fetch` = `api_fetch_timeout_seconds(20.0)+1.0` = **21.0s** (`:2975`); `run_search_graph` default 31.0s (`langgraph_search.py:144`); Evidence-Floor `_PER_ATTEMPT_TIMEOUT`=**2.5s** ×5 ≈12.5s; stance LLM **0.8s** hard timeout; `_emit_fetching` delay 1.2s; `llm_retry_backoff_seconds`=2.0; `llm_timeout_seconds`=90; `pipeline_timeout_seconds`=120; `proxy_timeout_seconds`=130; `cb_reset_timeout`=30; `semantic_cache_swr_ttl`=604800; `cache_ttl_structured/general`=604800/86400; `parallel_sections_max_concurrent`=3; section tokens=8192; BLUF tokens=6144. **Catalogued, not changed.**

### 7.6 Invariants LangGraph must keep
1. Neutral query for retrieval, original for caching. 2. Three freshness-gated cache exits. 3. Evidence Floor is the grounding gate (no synthesis without ≥1 URL-bearing source; exhaustion → `no_evidence`, never ungrounded). 4. `prompt_mode` always `"format"`. 5. Stage-7 post-processing order is load-bearing. 6. `run_search_graph` is the only pre-existing LangGraph island.

---

## 8. Git-History Learnings (for `ENGINEERING_JOURNAL.md`)

**Total commits:** 101. Two seams account for almost every regression.

### 8.1 Recurring themes
Reference/citation grounding (~15 commits, dominant) · provider/model toggle & routing (~12) · streaming/mid-stream UX (~8) · hallucination guards (~8) · dark mode (~7, early) · reference URL building (~6) · classifier/intent (~6) · cache stale/semantic (~5).

### 8.2 Reversals / "didn't we fix this before?" loops
- **References disappearing — fixed ≥5×:** `ec0a4d9`→`ef8fdeb`→`0043476`→`e634961`→`fd8345d`(Fix1)→`53f8957`. Ended only when grounding became a deterministic token map + registry anchor.
- **Per-section vs response-level refs — true reversal:** `ec0a4d9` (≥1 ref/section) caused mid-stream shrinkage → `dd907dd` ("never shrink on done — refs at response level").
- **Provider toggle stuck — re-fixed:** `344832e`/`806153e` → root-caused in `fd8345d` Fix2 (backend "first-key-wins" vs `engine_pref`; FE stale closure; no server-canonical `active_provider`).
- **Expert Consensus invented sources — whack-a-mole:** `916c1c0`→`d8d5671`→`87d7d4f`→`f6ea408`. Fixed by forbidding all variants except canonical "Expert opinion".
- **Default model flip-flop:** `ccb99d7`/`8044dd9`→`ada8e6f`→`f16c6ec`. The moving default is itself churn.

### 8.3 Hard-won gotchas to memorialize
1. **`gpt-oss*`→Cerebras must precede `gpt-`→OpenAI** in `get_provider()` (`llm_factory.py:56-66`) or `gpt-oss-120b` 404s on OpenAI.
2. **`[REF_N]` tokens** = deterministic attribution; `_resolve_ref_tokens` **must run before `sanitize_response_pmids`**; re-emit valid tokens in *every* section prompt.
3. **`__UNRESOLVED_TOKEN__` sentinel** (not `""`) so backfill can target unresolved citations.
4. **Expert-opinion backfill**: normalize variants to canonical first, then inherit nearest ref.
5. **Demote, don't drop** (`_quarantine_sourceless_items`, gated on `fetched_data`; v2 Jaccard ≥0.5) — drop-based logic is what made ref lists vanish.
6. **Evidence Floor** closes the ungrounded generate-mode bypass; paired fix: `langgraph_search.py:60-63` fetch-timeout returns `fallback_to_llm=False` so the floor can retry.
7. **Article Registry** guarantees article-level URLs + orphan rescue; needs `semanticscholar.org`/`ncbi.nlm.nih.gov` in allowed domains (`31fb5e8`).
8. **Stance Neutralizer** strips valence before retrieval; audit-only metadata, regex fallback.
9. **URL builder** rebuilds from structured IDs late; **never null an existing URL**.

> **One-line:** every regression traces to (a) citation grounding under a changing pipeline, or (b) provider/model selection state drifting between a stale FE closure and a "first-key-wins" backend. The refactor's single-registry + adapter design directly attacks seam (b); the evidence-only contract hardens seam (a).

---

*End of AUDIT.md — Phase 1 deliverable. Proceeding to Phase 2 (`REFACTOR_PLAN.md`).*
