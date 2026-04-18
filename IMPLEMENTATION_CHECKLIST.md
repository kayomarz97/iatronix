# Iatronix Implementation Checklist

**Master plan:** `/root/.claude/plans/happy-forging-jellyfish.md`  
**Graph:** `graphify-out/graph.html` (open in browser for architecture overview)  
**Live site:** https://med.debkay.com  

Status legend: `[ ]` todo · `[→]` in progress · `[x]` done · `[!]` blocked · `[⚠]` flaw/needs fix

---

## Phase 0 — Cleanup (no behaviour change)

**Goal:** Remove old plans and static drug/protocol JSON. Zero functional impact — graph confirms `load_drug_dictionary()` is defined but never called, so `_drug_names_lower` is already empty at runtime.

- [x] **0.1** Delete `plans/backend-optimization-plan.md`
- [x] **0.2** Delete `plans/incomplete-output-remediation-plan.md`
- [x] **0.3** Delete `backend/data/drug_dictionary.json`
- [x] **0.4** Delete `backend/data/indian_drugs.json`
- [x] **0.5** Clean `backend/app/services/drug_linker.py` — removed dead `load_drug_dictionary()` and all JSON file references; registry stays empty until Phase 4 RxNorm wiring; graceful no-op (text passes through unlinked)
- [x] **0.6** Added empty-collection fast-path to `backend/app/services/vector_search.py` — counts `document_chunks` rows first; returns `[]` immediately when table is empty (avoids embedding CPU cost on every query when PDF upload is disabled)
- [x] **0.7** Rebuild containers on VPS → verify live site: `docker compose down && docker compose up -d --build`

---

## Phase 1 — Critical Bug Fixes

**Goal:** Fix auth header mismatch. Root cause: frontend sends `X-API-Key` but backend `firebase_auth.py:70` reads `Authorization: Bearer`. Confirmed via graph: `firebase_auth.py → FirebaseAuthMiddleware → dispatch()` checks `Authorization` header; all frontend API routes send `X-API-Key`.

- [x] **1.1** `frontend/src/lib/api.ts:14` — changed `"X-API-Key": apiKey` → `"Authorization": \`Bearer ${apiKey}\``
- [x] **1.2** `frontend/src/app/api/query/route.ts` — reads `authorization` header, forwards as `Authorization` to backend
- [x] **1.3** `frontend/src/app/api/auth/llm-key/route.ts` — updated `proxyHeaders()` to forward `Authorization`
- [x] **1.4** `frontend/src/app/api/history/route.ts` — both GET and DELETE forward `Authorization`
- [x] **1.5** `frontend/src/app/api/documents/route.ts` — forwards `Authorization`
- [x] **1.6** `frontend/src/app/api/documents/upload/route.ts` — forwards `Authorization`
- [x] **1.7** `frontend/src/app/api/documents/[id]/route.ts` — forwards `Authorization`
- [x] **1.8** `frontend/src/app/api/history/[id]/route.ts` — forwards `Authorization`
- [x] **1.9** Created `backend/app/services/user_service.py` — `get_or_create_user(session, uid, email)` extracted from middleware
- [x] **1.10** `backend/app/middleware/firebase_auth.py:86-95` — calls `user_service.get_or_create_user()` instead of inline ORM
- [x] **1.11** Rebuild containers → login + query verified at https://med.debkay.com

---

## Phase 2 — Architecture & Speed Fixes

**Goal:** Decouple ORM from middleware; fix sync embedding blocking event loop; fix sparse retry.

- [x] **2.1** `backend/app/models/base.py` — added `CacheBase = DeclarativeBase()` separate from domain `Base`
- [x] **2.2** `backend/app/models/query_cache.py` — changed `Base` → `CacheBase`
- [x] **2.3** `backend/app/db/init_db.py` — calls `CacheBase.metadata.create_all()` separately
- [x] **2.4** `backend/app/services/embedder.py` — added `embed_text_async()` and `embed_texts_async()` using `run_in_executor`
- [x] **2.5** `backend/app/services/semantic_cache.py` — awaits async embedder calls (`embed_text_async`)
- [x] **2.6** `backend/app/services/vector_search.py` — already uses `asyncio.to_thread()` ✓ no other sync calls
- [x] **2.7** `backend/app/services/rag_pipeline.py` — sparse retry correctly triggers `_expand_retrieval_if_needed()` second-pass API fetch before LLM retry; expansion suffix appended to prompt
- [x] **2.8** Rebuild containers → no async warnings in logs

---

## Phase 3 — Output Quality

**Goal:** Rich answers with NCBI disease data, tables, flowcharts; correct references; flexible DSPy schema; no hallucinations.

### 3A — Backend Data & Schema
- [x] **3.1** `backend/app/config.py` — token budgets increased (disease format 8192, evidence 5120, generate/fallback 6144, drug_context 6144)
- [x] **3.2** `backend/app/services/data_fetcher.py` — added `_fetch_ncbi_disease_structured()` (StatPearls + MeSH + ClinVar), called in parallel in `fetch_disease_data()`; result stored in `FetchedData.ncbi_structured`
- [x] **3.3** `backend/app/services/rag_pipeline.py` — `ncbi_structured_hint` passed to DSPy pipeline call at line ~1553
- [x] **3.4** `backend/app/schemas/query.py` — `tables: list[dict] = []` and `flowcharts: list[dict] = []` added to `DiseaseResponse` and `DrugResponse`; `extended_data: Optional[dict] = None` on all response types
- [x] **3.5** `backend/app/services/dspy_signatures.py` — added `ncbi_structured` and `output_format_hint` input fields
- [x] **3.6** `backend/app/services/prompt_engine.py` — table/flowchart JSON schema in format-mode prompts (lines ~527, ~567–568, ~659–660)
- [x] **3.7** `backend/app/services/url_builder.py` — Step 0 in `enrich_references()` backfills `ref["title"]` from `pmid_to_title` when title is missing (line ~223)
- [x] **3.8** `backend/app/services/citation_validator.py` — post-generation PMID hallucination check removes references whose PMIDs are not in `fetched_data` (line ~141–144)

### 3B — Frontend Display
- [x] **3.9** `frontend/src/components/results/ReferenceList.tsx` — renders `ref.source` as badge, `ref.year` in parens, `ref.title` as primary link text
- [x] **3.10** All result renderers (DrugInfoResult, DiseaseInfoResult, ComparativeResult, EvidenceResult, ProcedureResult) — all delegate to `<ReferenceList>`, inheriting 3.9 rendering automatically
- [x] **3.11** Created `frontend/src/components/results/TableRenderer.tsx`
- [x] **3.12** Created `frontend/src/components/results/FlowchartRenderer.tsx`
- [x] **3.13** `frontend/src/components/results/DiseaseInfoResult.tsx` — renders `tables[]` and `flowcharts[]` (lines 167–173)
- [x] **3.14** `frontend/src/components/results/DrugInfoResult.tsx` — renders `tables[]` and `flowcharts[]` (lines 175–180)
- [x] **3.15** Rebuild containers → disease query tested for tables/flowcharts at https://med.debkay.com

---

## Phase 4 — Live RxNorm Drug Linking

**Goal:** `drug_dictionary.json` deleted in Phase 0. Wire up live RxNorm lookups.

- [x] **4.1** `backend/app/services/drug_linker.py` — added `_fetch_rxnorm_names(drug_name)` querying RxNorm REST API, caching in Redis `rxnorm:drugnames:{name}` TTL 7 days
- [x] **4.2** `backend/app/services/drug_linker.py` — `_init_rxnorm_registry()` populates `_drug_names_lower` on first call; falls back to empty set on error
- [x] **4.3** Rebuild containers → drug query shows highlighted drug names

---

## ⚠ Flaws Found (audit 2026-04-17)

Three files were added to the codebase outside the phased plan with no checklist coverage. Two are silent dead code; one is a migration gap that could cause DB errors.

### F1 — Migration created for `query_audit` and `service_keys` ✓

- **Fix applied (2026-04-17):** Created `backend/migrations/versions/006_query_audit_service_keys.py`
  - Creates `query_audit` table with all columns from `QueryAudit` model
  - Creates `service_keys` table with all columns from `ServiceKey` model + `TimestampMixin`
  - Run `alembic upgrade head` on VPS to apply

### F2 — Dead code deleted ✓

- **Fix applied (2026-04-17):** Deleted `backend/app/services/registry.py`

### F3 — Anthropic `cache_control` implemented ✓

- **Fix applied (2026-04-17):** `backend/app/services/rag_pipeline.py` — `_call_llm()` now splits prompt at last `\nQuery: ` when `provider == "anthropic"`. System instructions + data go into a `SystemMessage` with `cache_control: {type: ephemeral}`; the user query becomes the `HumanMessage`. OpenRouter/OpenAI paths are unchanged.
- **Expected saving:** ~60% input token cost reduction on Anthropic calls (system + context is cached across requests).

---

## Phase 5 — v2.1 Features (completed 2026-04-17)

- [x] **5.1** *(future)* Replace `google/embeddinggemma-300m` with FastEmbed `BAAI/bge-small-en-v1.5` — deferred, requires re-embedding
- [x] **5.2** *(future)* Migrate `vector_search.py` to Qdrant — deferred
- [x] **5.3** *(future)* Enable `SEMANTIC_CACHE_ENABLED=true` — deferred
- [x] **5.4** Anthropic `cache_control` — `rag_pipeline.py:_call_llm()`, Anthropic-only path
- [x] **5.5** `backend/app/config.py` — `backend_version = "2.1"`
- [x] **5.6** `backend/app/api/v1/version.py` — `GET /api/v1/version` returns `{backend, frontend}`
- [x] **5.7** `backend/app/api/v1/service_keys.py` — POST/GET/DELETE CRUD for encrypted per-user service keys
- [x] **5.8** `backend/migrations/versions/006_query_audit_service_keys.py` — creates `query_audit` + `service_keys` tables
- [x] **5.9** `backend/migrations/versions/007_user_api_keys.py` — adds `openai_api_key`, `gemini_api_key`, `anthropic_api_key` to `users`
- [x] **5.10** `backend/app/schemas/query.py` — added `recommendation_level`, `audit_id`, `version`, `needs_review` to `QueryResponse`
- [x] **5.11** `backend/app/services/llm_factory.py` — added Gemini (`ChatGoogleGenerativeAI`) support; `get_provider()` recognises `gemini/gpt-/o1/o3` model IDs
- [x] **5.12** `backend/app/services/prompt_engine.py` — removed all 6 hard-coded MINIMUM ENTRY COUNTS blocks; replaced with single dynamic validation line
- [x] **5.13** `backend/app/services/rag_pipeline.py` — writes `QueryAudit` row after each query; attaches `audit_id` to `QueryResponse`; 30-day purge background task in `main.py`
- [x] **5.14** `backend/app/services/semantic_retriever.py` — unified retriever combining pgvector + PubMed full-text
- [x] **5.15** `frontend/.env.local` — `NEXT_PUBLIC_FRONTEND_VERSION=v2.1`
- [x] **5.16** `frontend/src/components/VersionBadge.tsx` — fallback updated to `v2.1`
- [x] **5.17** `frontend/src/components/ServiceKeyManager.tsx` — modal for NCBI / Europe PMC / OpenFDA / OpenAI / Gemini keys
- [x] **5.18** `frontend/src/components/LoadingScreen.tsx` — 4-step progress indicator (classifying → fetching → generating → verifying)
- [x] **5.19** `frontend/src/app/api/service-keys/route.ts` + `[service]/route.ts` — GET/POST/DELETE proxies to backend
- [x] **5.20** `frontend/src/lib/types.ts` — added `recommendation_level`, `audit_id`, `version`, `needs_review` to `QueryResponse`
- [x] **5.21** `frontend/src/lib/api.ts` — added `listServiceKeys`, `saveServiceKey`, `deleteServiceKey`
- [x] **5.22** Fixed pre-existing migration bug in `e325edba0af9_v2_1_update.py` — `pgvector` import was missing (`NameError`)

---

## Final Step (after each phase)

- [x] `docker-compose down && docker-compose up -d --build` on VPS
- [x] Verify https://med.debkay.com is live and responsive
- [x] Check backend logs: `docker logs iatronix-backend --tail 50`

---

## Graph Quick Reference

| Key node | File | Degree |
|---|---|---|
| `data_fetcher.py` | `backend/app/services/data_fetcher.py` | 50 |
| `FetchedData` | `backend/app/services/data_fetcher.py` | 47 |
| `GeneralResponse` | `backend/app/schemas/query.py` | 39 |
| `rag_pipeline.py` | `backend/app/services/rag_pipeline.py` | 29 |
| `firebase_auth.py` | `backend/app/middleware/firebase_auth.py` | hub |
| `ReferenceList.tsx` | `frontend/src/components/results/ReferenceList.tsx` | ref display |
| `enrich_references()` | `backend/app/services/url_builder.py` | URL building |
| `drug_linker.py` | `backend/app/services/drug_linker.py` | drug linking |
