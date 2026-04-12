# Backend Optimization Plan

Date: 2026-03-30

## Objective

Rebuild the backend so it has no hard-coded medical routing, does not depend on any local LLM-style model runtime, resolves drug brands to salts/generics using live online sources instead of local repositories, uses only the user's own API key, and remains DSPy-driven so answers stay adaptive.

## What I Found In The Current Codebase

1. Drug lookup is still partly hard-coded.
   - `backend/app/services/data_fetcher.py` loads `backend/data/indian_drugs.json` and uses it as a fallback.
   - `backend/app/services/query_classifier.py` and `backend/app/services/source_router.py` rely on large regex and name lists.

2. Adaptive behavior is not actually adaptive enough.
   - Classification, entity extraction, and routing are still regex-first.
   - Docker currently forces `DSPY_ENABLED: "true"` in `docker-compose.yml`, which can make the backend brittle if the DSPy path is weak.
   - The DSPy path is not yet strong enough to replace the hard-coded routing it still depends on.

3. The backend still runs a local embedding model.
   - `backend/app/services/embedder.py` uses `sentence-transformers` with `all-MiniLM-L6-v2`.
   - That affects vector search and semantic cache.

4. BYOK/provider support is incomplete.
   - `backend/app/api/v1/auth_routes.py` only accepts `anthropic` and `openai`.
   - `backend/app/services/llm_factory.py` treats slash-based models as OpenAI-compatible, but there is no first-class `openrouter` provider path.
   - Frontend model selection is static and Anthropic-only.

5. Cache cleanup is only partial.
   - Redis can be flushed on startup via `FLUSH_REDIS=1`, but the Docker volume persists.
   - Semantic cache also lives in Postgres.

## Constraints I Will Follow

1. No server-owned LLM key usage for query generation.
2. No exposing stored user keys in logs, responses, README examples, or frontend state beyond current encrypted storage behavior.
3. No local LLM runtime.
4. No local or static repository for Indian brand-to-salt mapping. Drug resolution must be online.
5. Hard-coded disease/drug routing is to be removed, not merely reduced.
6. DSPy remains the primary adaptive answer engine.
7. PubMed/NCBI search must not be restricted to a fixed journal subset. Priority ranking is allowed, exclusion is not.
8. Backend first. Deployment and production push happen only after your go-ahead.

## Execution Plan

### Phase 1: Remove hard-coded medical routing and replace it with DSPy-led intent/entity analysis

1. Replace regex-first classification with a DSPy-driven query analysis layer that:
   - reads the raw user query,
   - extracts likely entities, query intent, and clinical context,
   - determines whether the query is drug, disease, comparative, evidence, or procedure without relying on curated drug or disease term banks.

2. Keep only a minimal non-medical fallback for parser failure cases.
   - Acceptable fallback: generic structural checks such as detecting explicit `vs` comparisons or obvious procedure phrasing.
   - Not acceptable: drug-name lists, disease-name lists, suffix-based medical routing, or local medical taxonomies used as the main decision path.

3. Refactor `query_classifier.py` and `source_router.py` so they become:
   - lightweight orchestration helpers,
   - not the primary medical knowledge source,
   - not the main classification authority.

4. Move routing decisions to a combination of:
   - DSPy analysis,
   - online retrieval results,
   - evidence completeness,
   - answerability confidence.

### Phase 2: Rebuild drug search around online brand-to-salt resolution instead of local repositories

1. Remove the local Indian drug fallback path entirely.
   - stop loading `backend/data/indian_drugs.json`,
   - remove the local India-only merge logic,
   - update README/docs accordingly.

2. Introduce a drug resolution pipeline:
   - Step A: normalize the user-entered string,
   - Step B: resolve whether it is a brand, generic, combination brand, or misspelled drug,
   - Step C: derive salt/generic names,
   - Step D: search authoritative drug directories using the resolved generic/salt names,
   - Step E: merge and rank results by confidence and source quality.

3. Data-source order for India-aware lookup:
   - live brand/salt resolution source first,
   - RxNorm / DailyMed / OpenFDA when the query already resolves cleanly or after generic resolution,
   - India-specific live source lookup after brand-to-salt resolution,
   - MedIndia or equivalent public source as fallback,
   - India Drug Index app access only if it exposes a legitimate network API, web endpoint, or reproducible searchable source.

4. India Drug Index app workstream:
   - inspect whether the Play Store app talks to a public API or web backend,
   - if it does, build a connector with clear rate limits and failure handling,
   - if it does not, do not hard-wire brittle scraping of private app traffic into the core path,
   - keep the connector optional behind a source adapter interface.

5. Build a new `drug_resolver` service to own:
   - normalization,
   - brand/generic/salt aliasing,
   - combination-drug splitting,
   - source ranking,
   - confidence scoring.

6. Do not ship any local brand-name repository as a fallback dataset.

### Phase 3: Keep DSPy as the adaptive core and fix the adaptive search path

1. Audit the current DSPy path in `rag_pipeline.py` and rebuild around it rather than around regex routing.
   - DSPy should become the primary query-analysis and response-shaping layer.
   - Non-DSPy logic should be fallback behavior, not the main path.

2. Redesign adaptive search around retrieval completeness:
   - fetched evidence decides response depth,
   - query intent decides section layout,
   - source availability decides whether to answer narrowly or broaden search.

3. Improve adaptive search behavior for:
   - underspecified searches,
   - misspelled drug brands,
   - mixed brand + disease queries,
   - India-specific brands,
   - comparative queries with weak initial matches.

4. Add observability for adaptive failures:
   - classified intent,
   - extracted entities,
   - source hits/misses,
   - response mode chosen,
   - fallback reason.

5. Add regression tests for the exact broken categories above.

### Phase 4: Remove local embedding dependency and make backend usable without local model runtime

1. Remove `sentence-transformers` usage from:
   - vector search,
   - ingestion,
   - semantic cache.

2. Replace embedding generation with API-based embeddings only when a user key/provider supports them.

3. If no embedding-capable provider/key is present:
   - disable semantic cache gracefully,
   - disable vector search gracefully,
   - keep the core live-source medical search working.

4. Make this behavior explicit in config and health reporting.

### Phase 5: Add proper OpenRouter support and Gemini free usability

1. Add `openrouter` as a first-class provider in:
   - backend auth schemas,
   - key validation,
   - model listing,
   - LLM factory,
   - frontend settings,
   - frontend model selector.

2. Make OpenRouter use the user's key only.
   - no server fallback key,
   - no hidden provider fallback,
   - no writing keys into logs.

3. Add a supported OpenRouter model list including a Gemini free option.
   - expose a working default OpenRouter Gemini model id in the UI,
   - make provider/model validation explicit,
   - keep Anthropic support intact for users who bring Anthropic keys.

4. Ensure model routing does not silently rewrite an OpenRouter selection into an Anthropic-only model.

### Phase 6: Expand PubMed/NCBI retrieval so journal lists are only a ranking hint

1. Change PubMed/NCBI search so the system can search the full relevant corpus, not just predefined journal subsets.

2. Keep the journal registry only as a priority/ranking hint.
   - If high-priority journals return results, rank them higher.
   - If they do not, fall back automatically to the wider PubMed/NCBI result space.

3. Remove any retrieval logic that effectively blocks broader PubMed/NCBI evidence when the specialty journal filter is too narrow.

4. Score and structure the returned evidence after retrieval.
   - search broadly,
   - rank sources,
   - grade claims using LoE/CoR rules,
   - do not pre-restrict the evidence base more than necessary.

5. Add tests for:
   - zero results in priority journals but valid results elsewhere in PubMed,
   - rare diseases,
   - uncommon Indian drug-condition queries,
   - broad evidence queries that should not collapse to one narrow journal class.

### Phase 7: Clean old cache state and simplify cache strategy

1. Delete old cache/Redis state:
   - flush Redis keys,
   - remove the Redis Docker volume,
   - review semantic query cache rows in Postgres.

2. Version cache keys so the new backend never trusts old entries.

3. Revisit whether semantic cache should stay enabled once local embeddings are removed.
   - If embedding support is unavailable, disable semantic cache rather than keeping a broken path.

4. Add a documented cache reset procedure for Docker deployments.

### Phase 8: Documentation and deployment, after your approval

1. Update the README to reflect:
   - no local LLM/embedding requirement,
   - new provider support,
   - new drug resolution flow,
   - cache reset behavior,
   - Docker Compose deployment steps.

2. Then deploy with Docker Compose.
   - rebuild containers,
   - reset old Redis/cache state,
   - run migrations,
   - verify backend and frontend health,
   - then push to the website.

## Files Likely To Change

- `backend/app/services/query_classifier.py`
- `backend/app/services/source_router.py`
- `backend/app/services/data_fetcher.py`
- `backend/app/services/rag_pipeline.py`
- `backend/app/services/llm_factory.py`
- `backend/app/services/byok.py`
- `backend/app/services/embedder.py`
- `backend/app/services/semantic_cache.py`
- `backend/app/services/vector_search.py`
- `backend/app/services/ingestion.py`
- `backend/app/api/v1/auth_routes.py`
- `backend/app/api/v1/models.py`
- `backend/app/schemas/auth.py`
- `backend/app/schemas/models.py`
- `backend/app/config.py`
- `backend/Dockerfile`
- `docker-compose.yml`
- `frontend/src/app/settings/page.tsx`
- `frontend/src/hooks/useModelSelection.ts`
- `frontend/src/components/ui/ModelSelector.tsx`
- `README.md`

## Acceptance Criteria

1. A query with an Indian brand name resolves to salt/generic form through live online lookup, not a local JSON repository.
2. Hard-coded drug/disease routing is removed from the primary path.
3. DSPy is the primary adaptive query-analysis and answer-shaping layer.
4. PubMed/NCBI retrieval can widen to the full corpus, with journal lists used only for ranking priority.
5. Adaptive search returns materially better results for ambiguous and India-specific queries.
6. The backend does not require `sentence-transformers` or another local model runtime.
7. Users can save and use an OpenRouter key, including a Gemini free model path.
8. Only user-supplied API keys are used.
9. Old Redis/cache state can be deleted cleanly and documented.
10. Docker Compose deployment and README update are completed only after approval.

## Order I Recommend

1. Remove hard-coded medical routing from the primary path.
2. Build the online drug resolution layer.
3. Rebuild DSPy-led adaptive search.
4. Expand PubMed/NCBI retrieval.
5. Remove local embedding dependency.
6. Add OpenRouter and Gemini free support.
7. Reset cache strategy.
8. Update README and deploy with Docker Compose after approval.
