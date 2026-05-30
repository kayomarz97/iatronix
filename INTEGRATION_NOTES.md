# INTEGRATION_NOTES.md — Verified API Facts for the Provider-Agnostic Refactor

> **Research date:** 2026-05-31 · **Method:** 7 parallel agents fetching **live official docs** (not model memory) via web search/fetch. Model knowledge cutoff is Jan 2026; APIs have drifted, so everything here is re-verified against current docs with source links + the doc's last-updated date where shown. Anything not confirmable from a live doc is marked **UNVERIFIED**.
> **Companions:** `AUDIT.md` (Phase 1), `REFACTOR_PLAN.md` (Phase 2).

---

## A. Plan-affecting flags (read first — these change scope)

| # | Flag | Impact |
|---|------|--------|
| **A1 🔴 URGENT** | **`claude-sonnet-4-20250514` (your `MODEL_SONNET`) is DEPRECATED and retires 2026-06-15** (~2 weeks). After that, Sonnet calls 404. | Registry default Sonnet → **`claude-sonnet-4-6`** (active, pinned snapshot). Do this in Phase 3 regardless of other work. |
| **A2 🔴** | **`text-embedding-004` was SHUT DOWN 2026-01-14.** `embedder.py:36` still uses it for the Gemini embedding path. | Registry embedding model for Google → **`gemini-embedding-001`** (text) / `gemini-embedding-2` (multimodal). Any vector index built on `-004` (768-dim) is orphaned → re-embed if VECTOR_SEARCH is ever enabled. Latent today (Gemini + vector search both off). |
| **A3** | **All existing pricing is stale.** Verified Haiku 4.5 = **$1 in / $5 out** (cache read $0.10) — not config.py's $0.25/$1.25 nor registry's $0.80/$4.00. | `providers.yaml` carries corrected pricing (§D tables). Delete the duplicate `cost_haiku_*`/`cost_sonnet_*` block in config.py (AUDIT §2 row 3). |
| **A4** | **Caching is 3 structurally different mechanisms** (inline / automatic-prefix / stateful-object). | The adapter cache interface needs `prepare_cache` + `apply_cache` + `read_cache_usage`, not just `apply_cache` (§C). |
| **A5** | **Cerebras caching is officially guaranteed only on `gpt-oss-120b`** (+ `zai-glm-4.7`); `llama-3.3-70b`/`qwen-*` are **not** listed as cache-enabled. Cerebras cache hits are **NOT cheaper** (full price, still count toward TPM) — latency only. | Don't promise cache savings for non-gpt-oss Cerebras models; registry `supports_caching` is per-model, not just per-provider. |
| **A6** | **Anthropic Haiku 4.5 minimum cacheable prompt = 4,096 tokens.** Your data_block cache breakpoints gate on `>1024`/`>4096` **chars** (≈256–1024 tokens) → often silently don't cache on Haiku. **1-hour TTL no longer needs a beta header** (`extended-cache-ttl-*` retired). | Adapter gates Anthropic breakpoints on the real per-model **token** floor; drop any beta-header code; fix the stale "1h TTL" docstring (it only sets 5m `ephemeral`). |
| **A7** | **LangGraph default `recursion_limit = 1000`** (not 25). Concurrent writes to one state key throw `InvalidUpdateError` without a reducer. | Phase 6 citation-chaser: explicit `depth` counter + conditional-edge bound + small `recursion_limit` backstop; accumulator keys use `Annotated[list, operator.add]`. |

---

## B. LangGraph (target framework for Phase 6)

**Versions (verified):** `langgraph` **1.2.2** (2026-05-26, Python ≥3.10) · `langchain-core >=1.4.0,<2` · `langgraph-checkpoint >=4.1.0`.
**Canonical imports:**
```python
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.types import Send, Command          # NOT in langgraph.graph
from langgraph.errors import GraphRecursionError
```

**Existing code is current.** `langgraph_search.py` uses only non-deprecated 1.2.2 primitives (`StateGraph`, `add_node/add_edge`, static START fan-out / END fan-in, `.compile()`, `await ainvoke`). **No migration needed** for the existing island; Phase 6 extends the same patterns.

**Primitives:**
- `add_conditional_edges(source, path_func, path_map=None)` — `path_func` returns a node name / list / `END`.
- **State reducers:** default = override (last write wins). To merge concurrent writes: `Annotated[list[X], operator.add]` or `add_messages`. ⚠ **Two parallel nodes writing the same key with no reducer → `InvalidUpdateError`** (it does not silently clobber). The existing graph dodges this by writing distinct keys (`fetched_data`/`vector_results`/`sem_result`).
- **Static fan-out:** multiple outgoing edges run all targets in one superstep. **Dynamic fan-out:** `Send("node", payload)` dispatches one parallel instance per item (map-reduce) — this is how per-citation chasing fans out.
- **Fan-in:** prefer reducer-based (`Annotated[list, add]` accumulator → successor reads it) over `defer=True` (known bugs #6005/#5182) unless asymmetric branch depth forces it.

**Bounded cyclic citation-chaser (Phase 5/6 — the recommended pattern):**
```python
class ChaseState(TypedDict):
    depth: int
    citations: Annotated[list, operator.add]   # concurrent writers REQUIRE a reducer
    evidence_score: float

def should_continue(state):
    if state["depth"] >= 5: return END           # hard depth cap (registry deep_search.max_depth)
    if state["evidence_score"] >= THRESHOLD: return END   # satisfied early → short-circuit
    return "chase_more"

builder.add_conditional_edges("evaluate", should_continue, {"chase_more": "chase", END: END})
builder.add_edge("chase", "evaluate")            # the cycle
# embed as a compiled subgraph via a wrapper fn (Case B) so it gets its OWN recursion_limit backstop:
chaser = builder.compile()
def run_chaser(parent_state): return {"evidence": chaser.invoke({...}, {"recursion_limit": 12})["citations"]}
```
- **Default recursion_limit is 1000** → never rely on it for semantic depth; counts *supersteps* not loop iterations. Use the explicit `depth` counter; keep a small `recursion_limit` as a backstop (`GraphRecursionError`).
- **Conditional short-circuits** (maps cleanly to AUDIT §7.3): cache-hit → `END`; evidence-below-threshold → loop node; `Command(update=…, goto=…)` fuses state-write + hop (keep separate from `defer`).
- **Async/stream:** `ainvoke`/`astream(inputs, stream_mode=[...], version="v2")`; 7 stream modes incl `"custom"` (deep-search progress events via `get_stream_writer()`/`writer` param). `subgraphs=True` streams nested graphs (`ns` namespace identifies source).
- **Timeouts:** no verified built-in per-node timeout in 1.2.2 → **keep the app-layer `asyncio.wait_for`** (as `fetch_node` already does). Preserves AUDIT §7.5 constants verbatim.
- ⚠ **Python <3.11 caveat:** async nodes can't use `get_stream_writer()` and must accept `writer: StreamWriter`; must pass `RunnableConfig` into async LLM calls. **Action: confirm backend Python is ≥3.11** (Dockerfile says 3.12 per AUDIT — OK).

Sources: docs.langchain.com/oss/python/langgraph/{graph-api, streaming, use-subgraphs, errors/GRAPH_RECURSION_LIMIT}; pypi langgraph 1.2.2.

---

## C. Unified caching design (answers: "everyone has different syntax — suggest a fix")

You're correct — there is **no common caching syntax**. The five active/near-term providers fall into **three structural classes**:

| Class | Providers | How caching is requested | What the adapter does |
|-------|-----------|--------------------------|------------------------|
| **1. Inline annotation** | **Anthropic**; OpenRouter *when routing an Anthropic model* | Mark content blocks with `cache_control:{"type":"ephemeral"[,"ttl":"1h"]}` | Inject breakpoints on the static prefix block(s), gated by the per-model **token** floor |
| **2. Automatic prefix** | **Cerebras**, **OpenAI**, **xAI Grok**, OpenRouter (Gemma/Llama), Gemini *implicit* | Nothing sent — server hashes the stable prefix | **No-op**; just keep the reusable prefix stable & first (a prompt-assembly invariant). Optionally set a routing hint header/param |
| **3. Stateful object** | **Gemini explicit** (`CachedContent`) | `client.caches.create(...)` → get `cache.name` → pass `cached_content=name` → `caches.delete` | A real **lifecycle**: create (if content ≥ floor), attach by handle, expire/clean up |

**Therefore the adapter cache contract is three methods, not one:**
```python
class ProviderAdapter(Protocol):
    # ... build_client / generate / embed / supports_caching / supports_vision / validate_key ...

    def prepare_cache(self, blocks: PromptBlocks, ttl: str | None) -> CacheHandle | None:
        # Anthropic/Cerebras/OpenAI/Grok/OpenRouter -> None (nothing to pre-create)
        # Gemini -> client.caches.create(...) IF token_count(blocks.cacheable) >= model.min_cache_tokens, else None

    def apply_cache(self, blocks: PromptBlocks, handle: CacheHandle | None) -> ProviderMessages:
        # Class 1 -> annotate static block(s) with cache_control (+ttl), gated on per-model token floor
        # Class 2 -> return blocks unchanged (assembly keeps static prefix first); optional routing hint
        # Class 3 (Gemini) -> set config.cached_content = handle.name

    def read_cache_usage(self, response) -> CacheUsage:   # normalize across providers
        # -> {cache_read_tokens, cache_write_tokens, uncached_input_tokens}

    def release_cache(self, handle: CacheHandle | None) -> None:
        # Gemini -> client.caches.delete(handle.name); others -> no-op
```

**Per-provider `read_cache_usage` normalization (exact field paths, verified):**
| Provider | cache_read | cache_write | notes |
|----------|-----------|-------------|-------|
| Anthropic | `usage.cache_read_input_tokens` | `usage.cache_creation_input_tokens` (+ `cache_creation.ephemeral_{5m,1h}_input_tokens` to prove TTL) | hit = read>0, write=0 |
| Cerebras | `usage.prompt_tokens_details.cached_tokens` | n/a | subset of prompt_tokens; **not cheaper** |
| OpenAI | `usage.prompt_tokens_details.cached_tokens` | n/a | auto ≥1024-token prefix |
| xAI Grok | `usage.prompt_tokens_details.cached_tokens` (Responses API: `usage.input_tokens_details.cached_tokens`) | n/a (no write field) | auto prefix |
| Gemini | `usageMetadata.cachedContentTokenCount` | (storage cost, not a token field) | `uncached = promptTokenCount − cachedContentTokenCount` — **don't double-count** |
| OpenRouter | `usage.prompt_tokens_details.cached_tokens` + `usage.cache_discount` | `usage.cache_write_tokens` (explicit-cache models only) | `usage:{include:true}` is **deprecated/no-op** |

**Invariant that must survive the refactor (AUDIT §6 + verified):** Class-2 caching depends entirely on a **byte-identical, leading static prefix**. The `_STATIC_*` constants and the static→data→dynamic ordering are load-bearing for Cerebras *and* now confirmed for OpenAI/Grok/Gemini-implicit. `apply_cache` for class 2 must never reorder or interpolate before the static prefix. **Gemini explicit caching is gated behind config** because it charges hourly storage even when idle — a created-but-unused cache is pure loss.

---

## D. Per-provider facts (for building the adapters)

### D1. Anthropic (active) — docs host moved to `platform.claude.com`
- **Client:** `langchain_anthropic.ChatAnthropic(model=…, api_key=…)`; base `https://api.anthropic.com`. Or middleware `AnthropicPromptCachingMiddleware(ttl='5m'|'1h')` (default `'5m'`).
- **cache_control:** `{"type":"ephemeral"}` (5m) or `{"type":"ephemeral","ttl":"1h"}` (1h, **no beta header**). System prompt must be an **array of content blocks** to attach a breakpoint. Order: tools → system → messages; static first. **Max 4 breakpoints**; lookback 20 blocks.
- **Min cache tokens:** Haiku 4.5 = **4,096**; Sonnet 4.6 = 1,024; Opus 4.8 = 1,024.
- **Model IDs:** `claude-haiku-4-5-20251001` ✅active · `claude-sonnet-4-6` ✅active (pinned) · `claude-sonnet-4-20250514` ⚠**retires 2026-06-15 → migrate to 4-6**.
- **Pricing $/MTok:** Haiku 4.5 $1 in / $5 out (5m-write $1.25, 1h-write $2, read $0.10) · Sonnet 4.6 $3/$15 (read $0.30) · Opus 4.8 $5/$25.
- **Vision:** Claude vision used by Waves (`spirometry_ai.py`) → register `claude-sonnet-4-6` as the `vision` role.

### D2. Cerebras (active) — OpenAI-compatible
- **Client:** OpenAI SDK / `ChatOpenAI(base_url="https://api.cerebras.ai/v1")`. ✅ unchanged. Auth Bearer.
- **Caching:** fully automatic prefix; `usage.prompt_tokens_details.cached_tokens`. Exact-prefix, 128-token blocks, min 128 tokens, TTL 5min guaranteed (≤1hr best-effort). Optional `prompt_cache_key` (≤1024 chars) routing hint. **Not cheaper; counts toward TPM.** Officially cache-enabled: **`gpt-oss-120b`**, `zai-glm-4.7` only.
- **Model IDs / pricing:** `gpt-oss-120b` — 131,072 ctx, **$0.35/$0.75**, 1M TPM / 1,000 RPM (paid). `llama-3.3-70b`, `qwen-3-235b-a22b-instruct-2507` exist but windows/pricing UNVERIFIED + not cache-listed → confirm via `GET https://api.cerebras.ai/v1/models`.
- ⚠ **Must NOT send** `frequency_penalty`/`presence_penalty`/`logit_bias` → 400. Non-standard knobs via `extra_body`/`model_kwargs`.

### D3. Google Gemini (ship enabled:false)
- **SDK:** first-party `google-genai` (`from google import genai; genai.Client(api_key=…)`); call `client.models.generate_content(model=, contents=, config=GenerateContentConfig(...))`. **BYOK: always pass `api_key=` explicitly** (never rely on env, or you leak one tenant's key). Base `https://generativelanguage.googleapis.com`, `v1beta`, header `x-goog-api-key`.
- **Caching (stateful):** `client.caches.create(model, config=CreateCachedContentConfig(system_instruction, contents, ttl="300s"))` → `cache.name` → `generate_content(config=GenerateContentConfig(cached_content=cache.name))`. Default TTL 1h, no bounds. Min tokens **1,024 (Flash) / 4,096 (Pro)** (NOT the old 32k). Implicit caching on by default for 2.5+/3.x (best-effort). Usage: `usageMetadata.cachedContentTokenCount`.
- **Model IDs / pricing:** `gemini-3.5-flash` (stable flagship, 1,048,576 ctx, **$1.50/$9.00**, cache-read $0.15) · `gemini-2.5-flash` ($0.30/$2.50) · `gemini-2.5-pro` (tiered at 200k: $1.25/$2.50 in). Don't hardcode `gemini-2.5-*` as "latest" — 3.x exists.
- **Embeddings:** **`gemini-embedding-001`** (text, 3072-dim, MRL 128–3072, `output_dimensionality`, `-001` needs manual L2 renorm if truncated) — `text-embedding-004` is **dead** (A2).

### D4. xAI Grok (ship enabled:false) — OpenAI-compatible
- **Client:** `OpenAI(api_key=…, base_url="https://api.x.ai/v1")`. Build on the **OpenAI path** (Anthropic-SDK compat UNVERIFIED).
- **Caching:** automatic prefix, **`apply_cache` = no-op**. Optional `x-grok-conv-id` header (Chat Completions) / `prompt_cache_key` (Responses API) to raise hit rate. Not 100% guaranteed (evictable). Usage `usage.prompt_tokens_details.cached_tokens` (no write field). Cached price ~$0.20/1M (third-party, UNVERIFIED).
- **Model IDs / pricing:** `grok-4.3` (flagship, 1M ctx, **$1.25/$2.50**) · `grok-build-0.1` (256k, $1/$2). `grok-4`/`grok-beta` stale. 10M TPM / 1.8K RPM default; 429 on exceed.

### D5. OpenAI (ship enabled:false) — automatic caching
- **Client:** `OpenAI(base_url="https://api.openai.com/v1")`. Caching automatic for ≥1024-token prefixes (128-token increments), `usage.prompt_tokens_details.cached_tokens`. **`apply_cache` = no-op.** Discount model-dependent (≈50% gpt-4o-class, up to 90% gpt-5.x) — don't hardcode 50%. Optional `prompt_cache_key`/`prompt_cache_retention` (`"24h"`). `gpt-4o-mini` still valid ($0.15/$0.60).

### D6. OpenRouter (ship enabled:false) — conditional passthrough
- **Client:** `OpenAI(base_url="https://openrouter.ai/api/v1")`. **`apply_cache` = conditional passthrough:** inject `cache_control` blocks **only** when the routed model is Anthropic/explicit-cache; for the app's current `google/gemma-4-31b-it` + `meta-llama/llama-3.3-70b-instruct:free`, it's a **no-op**. `usage:{include:true}` is **deprecated/no-op** — read `usage.cost`, `usage.cache_discount`, `usage.prompt_tokens_details.cached_tokens` (always present). OAuth PKCE flow already wired (AUDIT). Both app models 256k/131k ctx; neither supports explicit caching.

---

## E. Deep-search external APIs (Phase 5 citation-chasing menu)

**Budget:** depth ≤5, ~120s, branches parallel. Most APIs are unauthenticated-friendly but rate-limited; keys raise throughput (NCBI, OpenFDA, Semantic Scholar). NICE is licence-gated → exclude from the live loop.

| Source | Citation role | Key endpoint | Auth / limit |
|--------|--------------|--------------|--------------|
| **NIH iCite / NIH-OCC** ⭐ | **Best single call** — forward+backward in one response | `GET icite.od.nih.gov/api/pubs?pmids=…&fl=cited_by,references` (≤1000 PMIDs) | none |
| **NCBI E-utilities** | PubMed-deposited cited-by/refs | `elink.fcgi?dbfrom=pubmed&db=pubmed&id=PMID&linkname=pubmed_pubmed_citedin` / `…_refs`; `efetch db=pmc` fulltext | `NCBI_API_KEY` → 3→10 rps. ⚠ links **only cover PMC-deposited** articles (incomplete graph) |
| **Semantic Scholar** ⭐ | Cross-publisher graph (covers what PMC misses) | `/graph/v1/paper/{id}/citations` and `/references` (limit/batch ≤500) | `S2_API_KEY` mandatory at scale (anon = 5000/5min shared globally) |
| **Unpaywall** | DOI → OA fulltext PDF | `api.unpaywall.org/v2/{DOI}?email=…` → `best_oa_location.url_for_pdf` | email param; 100k/day |
| **ClinicalTrials.gov v2** | Trial evidence | `GET /api/v2/studies?query.cond=…` (pageToken; pageSize ≤1000) | none; v1 retired Jun 2024 |
| **OpenFDA** | Drug label/safety leaf | `api.fda.gov/drug/label.json?search=…` | `OPENFDA_API_KEY` → 240/min, 120k/day; `search_after` past ~25k |
| **RxNorm / DailyMed / MedlinePlus** | Drug normalize + consumer leaf | RxNav `/REST/rxcui.json`; DailyMed `/services/v2/spls`; MedlinePlus Connect (RXCUI OID `2.16.840.1.113883.6.88`) | none; MedlinePlus 100/min |
| **NICE** | UK guideline (licence-gated) | `api.nice.org.uk` header `API-Key` | **licence required → exclude from live loop**; fall back to public web fetch |

**Recommended fan-out within 120s:** seed PMID/DOI → **one iCite call** (full forward+backward depth 1) ∥ **one S2 citations+references** (cross-publisher) → dedupe DOIs → **batch Unpaywall** for fulltext → fetch top-N PDFs and recurse (depth++). Reserve `pubmed_pubmed_citedin/refs` for the PubMed-deepening branch. Provision in `.env`: `NCBI_API_KEY`, `OPENFDA_API_KEY`, `S2_API_KEY` (NICE only if licensed).

---

## F. `providers.yaml` corrections vs current code (consumed in Phase 3)

- **Sonnet default:** `claude-sonnet-4-6` (NOT `claude-sonnet-4-20250514` — retiring).
- **Pricing:** Haiku 4.5 `$1/$5` (read `$0.10`); Sonnet 4.6 `$3/$15`; gpt-oss-120b `$0.35/$0.75`; gemini-3.5-flash `$1.50/$9.00`; grok-4.3 `$1.25/$2.50`. (Replaces config.py `cost_*` AND `model_registry` numbers — both stale.)
- **Embedding models:** google→`gemini-embedding-001`; anthropic→`voyage-3`; openai→`text-embedding-3-small`.
- **`supports_caching` is per-model where needed** (Cerebras: only `gpt-oss-120b`/`zai-glm-4.7`).
- **`min_cache_tokens` per model** (Anthropic Haiku 4,096 / Sonnet 1,024; Gemini Flash 1,024 / Pro 4,096) — adapters gate breakpoints on this.
- **Cache class tag** per provider: `anthropic→inline`, `cerebras/openai/xai→auto_prefix`, `google→stateful`, `openrouter→conditional`.

---

## G. Verification ledger
- **VERIFIED live (2026-05-31):** all base URLs, client constructions, current model IDs + pricing for Anthropic/Cerebras/Gemini/Grok/OpenAI/OpenRouter, every caching mechanism + usage field path, Anthropic per-model cache minimums + TTL syntax (no beta header), Cerebras cache-model list + no-discount + 400-params, Gemini stateful cache lifecycle + `cachedContentTokenCount` + embedding-004 shutdown, Grok automatic caching + fields, LangGraph 1.2.2 primitives + recursion_limit=1000 + reducer requirement + Send + subgraph patterns, all deep-search endpoints + limits.
- **UNVERIFIED (flagged inline):** Cerebras non-gpt-oss windows/pricing; Grok cached-input price + TTL + min-prefix; LangChain `api_key` alias for Gemini; LangGraph per-node timeout knob; some deep-search numeric rate limits. Re-check these before enabling the affected adapter.

*End of INTEGRATION_NOTES.md — Phase 2.5 deliverable.*
