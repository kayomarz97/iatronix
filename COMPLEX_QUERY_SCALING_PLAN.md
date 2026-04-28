# Goal Description

Enable Iatronix to answer highly complex multi-stage medical queries (e.g., specific drug rules in conditions with comorbidities) and support scaling beyond 20 concurrent users without hitting blocking bottlenecks.

Crucially, **Anthropic Claude-Sonnet will be entirely removed from the required routing**, and the system will be refactored into a **Provider-Agnostic Tiered Architecture** enabling seamless, hot-swappable changing of LLM providers/models for all query types.

This file is located on the server at: `/root/projects/med-ai-project/COMPLEX_QUERY_SCALING_PLAN.md`.

## User Review Required

Please review the proposed architectural modifications for the provider-agnostic classifier and the rate limit adjustments. The **Future Scalability** section details changes (like PgBouncer and WebSockets) that shouldn't be executed immediately but are critical to your long-term success. No code has been executed or altered yet.

## Current System Scan & Syntax Verification Results
- **Syntax Check**: All backend python files pass compilation correctly (`python3 -m compileall backend/app` returned Exit code 0).
- **Prompt Caching Verification**: Prompt caching **IS WORKING AS EXPECTED**. Code scan confirms `{"type": "text", "text": ..., "cache_control": {"type": "ephemeral"}}` is successfully injected around `system` and `data_block` tokens across all LLM logic inside `rag_pipeline.py`.
- **Scaling Limits**: The "queuing at >20 users" bottleneck is a side effect of two hardcoded synchronous limits in your configuration:
  1. `data_fetcher.py` enforces a maximum HTTPX connection limit of `20`.
  2. `session.py` forces PostgreSQL connection pool size to `14`. 
  Once 20 concurrent users hit search, the system forcefully throttles the HTTP/DB pipes waiting for earlier inferences to finish.

---

## Proposed Changes

### Provider-Agnostic LLM Routing (Removing Sonnet)

#### [MODIFY] backend/app/config.py
- Remove specific `model_sonnet` and `model_haiku` configurations.
- Introduce agnostic tier levels that can be swapped to OpenRouter, Gemini, OpenAI, or any endpoint:
  - `MODEL_TIER_COMPLEX`: Default to a high-reasoning open model via OpenRouter (e.g., `google/gemini-1.5-pro` or `meta-llama/llama-3.3-70b-instruct`).
  - `MODEL_TIER_STANDARD`: Default to standard reasoning model.
  - `MODEL_TIER_FAST`: Default to a fast/cheap routing model.
- Add `DEFAULT_LLM_PROVIDER` to uniformly route fallback/keys easily if the user hasn't explicitly supplied one for a tier.

#### [MODIFY] backend/app/services/source_router.py
- Replace all hardcoded references routing disease/comparative queries specifically to `settings.model_sonnet`.
- Update the router to map `complex`, `comparative`, and `disease` queries to `settings.model_tier_complex`.
- Map standard generic queries to `settings.model_tier_standard` and fast formatting tasks (like `drug`) to `settings.model_tier_fast`.

#### [MODIFY] backend/app/services/llm_factory.py
- Ensure the `create_llm` object fully supports hot-swapping providers on the fly based on the prefix of the tier variables (e.g., parsing `openrouter/...` vs `gemini/...` vs `openai/...`) instead of defaulting unparsed model IDs to Anthropic models (e.g., removing hardcoded safety nets that force Anthropic when slashes `/"` aren't detected).

### Database connection pool adjustment

#### [MODIFY] backend/app/db/session.py
- Increase SQL pool connection limit to mitigate blocking queue timeouts.
- Change `pool_size=14` to `pool_size=50`.
- Change `max_overflow=2` to `max_overflow=20`, giving connections breathing room during high traffic bursts.

### External Source Limiting (The 20-User Bottleneck)

#### [MODIFY] backend/app/services/data_fetcher.py
- Update `limits=httpx.Limits(max_connections=20, max_keepalive_connections=10)` to `max_connections=150, max_keepalive_connections=50`.
- Apply this fix gracefully to all nested async client blocks for OpenFDA, PubMed, and SemanticScholar, allowing simultaneous fetching across a significantly larger concurrent user base.

### Query Classification (Handling Complex Multi-stage Intents)

#### [MODIFY] backend/app/schemas/query.py
- Add `"complex"` into the `QueryType` enum.
- Define a `ComplexResponse` Pydantic schema structure for returning multi-stage logic arrays (e.g. `[Base Condition Rules, Comorbidity Conflicts, Final Synthesized Evidence]`).

#### [MODIFY] backend/app/services/query_classifier.py
- Add `"complex"` to `_VALID_TYPES` array.
- In `LLM_CLASSIFY_PROMPT`, strictly define the `complex` rule: `"complex = multi-step medical scenarios, drugs in specific diseases accompanied with specific comorbidities or varying factors".`
- Add a regex heuristic `_COMPLEX_RE` in the fallback mechanism to catch queries referencing multiple medical conditions or containing tokens like "with", "complication", "dialysis", or "failure".

### LLM Prompting & Aggregation 

#### [MODIFY] backend/app/services/prompt_engine.py
- Introduce a `build_complex_messages()` function.
- Create explicit prompt guardrails demanding a systematic decomposition. 
- *Hallucination Guard*: The prompt must require `["Extracted Rule from guideline", "Conflicts noted in data constraints", "Verified Synthesized action"]` enforcing `citation_validator.py` verification at every subset.
- Add the caching `ephemeral` block mapping to ensure complex queries cache as effectively as drug/disease queries on supported providers.

#### [MODIFY] backend/app/services/rag_pipeline.py
- Update `_run_single_call_pipeline()` and `_run_parallel_pipeline()` to intercept `query_type == 'complex'`.
- Pass to the pipeline using the newly configured `MODEL_TIER_COMPLEX` logic.

#### [MODIFY] backend/app/services/dspy_signatures.py
- Update `MedicalQueryAnalysis` signature and descriptions to acknowledge the `"complex"` typing metric.

---

## Deployment Steps (To execute after approval)
1. Commit and push these modifications targeted to the `dev` branch.
2. Log into the VPS terminal and run rebuilding commands exactly as stated in `DEPLOY_COMMANDS.md`:
   ```bash
   git checkout dev
   docker compose -f docker-compose.dev.yml up -d --build
   ```
3. Push UI and verify behavior live via `med.debkay.com`.

---

## Future Updates for Scaling (>1,000 Concurrent Users Roadmap)
*Note: Do not implement these immediately. This resolves your requested future scoping.*

1. **Implement PgBouncer**: As traffic rises past 100 concurrent streams, scaling `pool_size` creates RAM bottlenecks. A lightweight Postgres connection pooler supports thousands of connections securely mapped into a controlled queue.
2. **WebSocket / Polling Job Queue**: HTTP requests (FastAPI) are held hostage while waiting 30-80s for an LLM to generate complex medical answers. Migrating to an async worker queue (e.g., Celery + Redis + WebSocket streams) ensures users push queries to a background processor and instantly free the frontend proxy limit, eliminating HTTP timeouts.
3. **Frontend Edge Hosting**: Decoupling the Next.js UI from the backend docker daemon to an Edge provider like Vercel ensures instant global load speeds and isolates pure CPU inference load solely toward the backend API server.

## Verification Plan
1. Ensure the hardcoded `.env` files dynamically switch LLMs easily by dropping in `openai` or `openrouter` endpoints.
2. Manually input a highly complex scenario: *"Rivaroxaban dosing in severe afib for a patient currently on fluconazole presenting with subacute hepatic impairment."* 
3. Trace backend logs noting `"complex"` intent routing correctly to your agnostic `MODEL_TIER_COMPLEX` provider.
4. Push simulated parallel load testing (using apache benchmark) to fire 30 parallel requests against the `/api/v1/query` and verify no timeouts occur on `httpx.Limits`.
