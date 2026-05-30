# REFACTOR_PLAN.md — Iatronix Provider-Agnostic Refactor

> **Plan location:** `/root/projects/med-ai-project/REFACTOR_PLAN.md`
> **Companion:** `/root/projects/med-ai-project/AUDIT.md` (Phase 1 findings, line-referenced)
> **Branch:** `dev` only · **Checkpoint:** `ea457b9` (tag `pre-refactor-20260530`)
> **Commit discipline:** *each functional change = its own commit* (independently revertable). No squashing across phases.
> **Status:** **AWAITING APPROVAL.** Nothing destructive runs until D1–D4 + E1–E4 are confirmed (see §0).

---

## 0. Decisions — RESOLVED (approved 2026-05-31)

### Formal decisions (D1–D4)

- **D1 — Providers & enabled set. ✅ APPROVED (all-6, two-active).** Build & fully wire all six adapters (**Anthropic, Cerebras, Google/Gemini, xAI/Grok, OpenAI, OpenRouter**). Registry `enabled`: **Cerebras + Anthropic = true**; the other four = `false`. Within each *active* provider the user can **choose the model** (model picker driven by `/api/providers`). Flipping one `enabled` flag later activates a provider on FE + BE with no other edit.
- **D2 — Caching. ✅ APPROVED.** Preserve Cerebras prefix auto-cache **byte-for-byte** (AUDIT §6); move Anthropic `cache_control` behind the adapter and consolidate its 3 duplicated paths; Google/Grok caching implemented from the Phase 2.5 docs; **no-op (not error)** where unsupported. *(Per-provider caching syntax differs — the verified syntaxes land in `INTEGRATION_NOTES.md`; `adapter.apply_cache()` hides the differences.)*
- **D3 — Deep-grounded answers. ✅ APPROVED (depth 5 / ~120 s / parallel).** Remove the training-data generate fallback (already dead — AUDIT §7.4). Replace the thin-retrieval terminal with **parallel citation-chasing**: depth **≤ 5** per branch, branches **parallel**, total budget **≈ 120 s**, all **registry-configurable**; honest **"No evidence found"** only when genuinely nothing is found. ⚠ *Design note: the 120 s deep-search budget collides with `pipeline_timeout_seconds=120` / `proxy_timeout_seconds=130` (AUDIT §7.5). Per constraint #4 I will document the rationale and flag before changing any timing — likely the deep-search path gets its own longer request timeout while normal queries keep 120 s.*
- **D4 — Dead-code scope. ✅ APPROVED.** Delete **only** the `reachable=false` items in AUDIT §5a; keep everything `reachable=true` (§5b).

### Audit-surfaced decisions (E1–E4)

- **E1 — Two pre-existing defects. ✅ FIX ALL (Phase 2.6).** (a) `ingestion.py:24` imports a non-existent `Embedder` → fix the import. (b) `test_dspy_comparison.py:22` holds **an internal Iatronix app key** (`iatx.iwn5urz42y58.…`, *not* a paid LLM key — it authenticates as one test user to the app's own `/query`). Fix = read it from `os.getenv("IATRONIX_TEST_API_KEY")` **and revoke key-id `iwn5urz42y58` in the DB** (kills the leaked secret; no third-party billing exposure).
- **E2 — `FAIL_CLOSED_EVIDENCE_ONLY` default mismatch. ✅ APPROVED.** Set the `config.py:150` code default to `True` to match `.env.example`/docs; document that the **Evidence Floor** is now the active grounding gate (the flag's own branch is dead until/unless generate-mode returns).
- **E3 — Waves vision path. ✅ APPROVED.** Model `spirometry_ai.py` as a `vision` role in the registry and route it through the Anthropic adapter; regression-test the Waves flow before/after (it's on the "must never break" list).
- **E4 — BYOK key storage. ✅ APPROVED — storage-agnostic dual-write.** Keep the Postgres Fernet columns **and** add a **Firestore (Admin SDK, server-side only, deny-all client rules, still Fernet-encrypted)** backend, both behind a new **`KeyStore` abstraction**. Pipeline reads/writes go through `keystore.*`, never a raw column. Dual-write to both stores; a config flag picks the **primary** (Postgres ⇄ Firestore) so migration is a flag flip with zero backfill. The allowed-provider set derives from the registry (no hardcoded allowlists). Firebase Admin SDK is already a dependency (auth), so Firestore access is incremental.

> All gate decisions resolved. Phase 2.5 (docs) is in progress; Phase 2.6 onward proceeds per the plan below.

---

## 1. Target architecture (what "edit one file" will mean)

**Single source of truth:** `config/providers.yaml` (new, repo root). Shape:

```yaml
version: 1
default_provider: cerebras
deep_search: { max_depth: 5, branch_parallelism: 6, total_budget_seconds: 120, per_branch_timeout_seconds: 20 }
providers:
  cerebras:
    display: "Cerebras"
    enabled: true
    client_kind: openai_compatible          # drives create_llm() client class
    base_url: https://api.cerebras.ai/v1
    key_column: cerebras_api_key             # existing DB column (E4)
    key_prefix: "csk-"
    validation: { probe_model: gpt-oss-120b }
    supports_caching: true
    cache_strategy: prefix_auto              # static->data->dynamic ordering (AUDIT §6)
    supports_vision: false
    embedding_model: null
    default_model: gpt-oss-120b
    models:
      - { id: gpt-oss-120b, display: "GPT-OSS 120B", input: 0.35, output: 0.75, tier: 2, roles: [generate, classify, bluf, section] }
      - { id: llama-3.3-70b, display: "Llama 3.3 70B", input: 0.85, output: 1.20, tier: 2, roles: [] }
  anthropic:
    display: "Anthropic (Claude)"
    enabled: true
    client_kind: anthropic
    base_url: https://api.anthropic.com
    key_column: anthropic_api_key
    key_prefix: "sk-ant-"
    validation: { probe_model: claude-haiku-4-5-20251001, api_version: "2023-06-01" }
    supports_caching: true
    cache_strategy: cache_control
    supports_vision: true
    embedding_model: voyage-3                # via voyage_api_key
    default_model: claude-haiku-4-5-20251001
    models:
      - { id: claude-haiku-4-5-20251001, display: "Claude Haiku 4.5", input: 0.80, output: 4.00, cache_write: 1.00, cache_read: 0.08, tier: 1, roles: [classify, generate] }
      - { id: claude-sonnet-4-20250514, display: "Claude Sonnet 4", input: 3.00, output: 15.00, tier: 2, roles: [sonnet_fallback] }
      - { id: claude-sonnet-4-6, display: "Claude Sonnet 4.6", input: 3.00, output: 15.00, tier: 2, roles: [vision] }
  google:    { enabled: false, client_kind: google_genai, base_url: https://generativelanguage.googleapis.com, ... }
  xai:       { enabled: false, client_kind: openai_compatible, base_url: https://api.x.ai/v1, ... }
  openai:    { enabled: false, client_kind: openai_compatible, base_url: https://api.openai.com/v1, ... }
  openrouter:{ enabled: false, client_kind: openai_compatible, base_url: https://openrouter.ai/api/v1, oauth: {...}, ... }
```

**Adapter interface** (`backend/app/services/providers/base.py`):
```python
class ProviderAdapter(Protocol):
    id: str
    def build_client(self, model_id, api_key, max_tokens, **kw): ...      # replaces create_llm branch
    async def generate(self, blocks, model_id, api_key, **kw) -> LLMResult # uses apply_cache internally
    async def embed(self, texts, model_id, api_key) -> list[list[float]]
    def apply_cache(self, blocks: PromptBlocks) -> ProviderMessages        # prefix_auto | cache_control | no-op
    def supports_caching(self) -> bool
    def supports_vision(self) -> bool
    async def validate_key(self, api_key) -> bool
```
One adapter file per provider under `backend/app/services/providers/`. Adding a provider = new adapter + one YAML entry.

**Loader** (`backend/app/services/provider_registry.py`): parses YAML once at startup; exposes `enabled_providers()`, `provider_meta(id)`, `model_meta(id)`, `pricing(id)`, `default_model(provider|role)`, `allowed_providers()`. **Replaces** `model_registry._REGISTRY`, the `config.py` role fields + duplicate `cost_*` block, and `schemas/models.AVAILABLE_MODELS`.

---

## 2. Phase-by-phase commit plan

> Phases 0–1 are **done** (checkpoint + `AUDIT.md`). Phase 2 is **this document**. Phases 2.5 → 10 run **after approval**.

### Phase 2.5 — Documentation review → `INTEGRATION_NOTES.md` (no code yet)
- **Commit `docs: INTEGRATION_NOTES — verified API facts for adapters + LangGraph`.**
- Fetch & date official docs (per brief §2.5): LangGraph (`StateGraph`, conditional edges, fan-out, reducers, cyclic subgraphs), Anthropic Messages + `cache_control`, Cerebras inference + prefix caching, Google Gemini API + context caching, xAI Grok API + caching, and the external data APIs touched by deep-search (PubMed/NCBI, OpenFDA, RxNorm, DailyMed, MedlinePlus, NICE, Unpaywall).
- **Files:** `INTEGRATION_NOTES.md` (new). **Flag** any doc that contradicts this plan before coding.

### Phase 2.6 — Pre-flight fixes (E1/E2, only if approved)
- **Commit `fix: ingestion Embedder import (ImportError)`** — `backend/app/services/ingestion.py`.
- **Commit `chore: remove committed test key + add to gitignore`** — `backend/tests/test_dspy_comparison.py` (+ user rotates key out-of-band).
- **Commit `fix: reconcile FAIL_CLOSED_EVIDENCE_ONLY default to True`** — `backend/app/config.py:150` (+ note in docs that Evidence Floor is the active grounding gate).

### Phase 3 — Provider/model-agnostic registry + adapters
Each step = its own commit:
1. **`feat: provider registry — config/providers.yaml + loader`** — add `config/providers.yaml`, `backend/app/services/provider_registry.py`; load in `backend/app/main.py` lifespan. No call sites changed yet.
2. **`refactor: adapter interface + Cerebras/Anthropic adapters`** — `backend/app/services/providers/{base,cerebras,anthropic}.py`; port `llm_factory.create_llm` + `get_provider` logic to read the registry (provider metadata, not id-prefix guessing). **Preserve `gpt-oss` routing semantics.**
3. **`refactor: route classifier/router/pipeline model selection through registry`** — `source_router.py`, `rag_pipeline.py` (`_default/_normalize_model_for_provider`, `_model_tier`, key-column map), `dspy_lm.py`, `cost_estimator.py`, `byok.py`, `embedder.py` — replace `provider == "..."` string branches with registry lookups (`role`/`tier`/`pricing`/`cache_strategy`).
4. **`refactor: spirometry vision via registry vision role`** (E3) — `spirometry_ai.py` reads `vision` role from registry; routed via Anthropic adapter. Waves regression-tested.
5. **`feat: GET /api/providers (enabled-only, no secrets)`** — `backend/app/api/v1/config_routes.py` (or new route); returns enabled providers/models from registry. Deprecate/redirect `/config/llm` + `/models` to it.
6. **`refactor: collapse provider allowlists to registry`** — `schemas/auth.py` Literals, `auth_routes.py` allowlist, `circuit_breaker.py` breaker set → derive from registry (no hardcoded allowlists).
6b. **`feat: KeyStore abstraction + Postgres & Firestore backends`** (E4) — new `backend/app/services/keystore/{base,postgres,firestore}.py`; `base.py` defines `KeyStore` (`get/set/delete(user, provider)`, Fernet in/out); Postgres backend wraps the existing columns; Firestore backend uses the **Admin SDK** (server-side, deny-all client security rules) with the same Fernet encryption. Dual-write both; `KEYSTORE_PRIMARY` config flag selects read primary (default `postgres`). Route **all** key reads/writes through it: `rag_pipeline.py` (key resolution), `auth_routes.py`, `byok.py`, `openrouter_oauth.py`, `waves.py`. No raw `users.*_api_key` access outside the Postgres backend.
7. **`feat: Google + xAI adapters (enabled:false)`** — `backend/app/services/providers/{google,xai}.py` + `openai`/`openrouter` adapters folded in; built from `INTEGRATION_NOTES.md`.
8. **`refactor: frontend renders providers/models from /api/providers`** — `frontend/src/lib/modelRegistry.ts`, `components/providers/QueryProvider.tsx`, `lib/constants.ts`, `app/settings/page.tsx`, `app/register/page.tsx`, `app/about/page.tsx` — remove hardcoded provider/model strings; generate key-entry UI **and the per-provider model picker** (D1) from the API response.
- **Acceptance:** `grep -ri` for provider/model strings finds them **only** in `config/providers.yaml` + `backend/app/services/providers/` + adapter tests. Flipping `enabled` changes both `/api/providers` and the UI with no other edit.

### Phase 4 — Provider-agnostic caching
- **`refactor: caching behind adapter.apply_cache`** — move Cerebras prefix ordering + Anthropic `cache_control` (consolidate the 3 paths from AUDIT §6) into adapters; pipeline calls one `adapter.apply_cache(blocks)`. Google/Grok caching per docs; no-op elsewhere. **Files:** `prompt_engine.py` (block assembly), `rag_pipeline.py` (`_call_llm_simple`), adapter files.
- **Acceptance:** switching enabled provider doesn't break caching; Cerebras `cached_tokens` + Anthropic `cache_read` still observed; unsupported provider runs with caching off.

### Phase 5 — Deep-grounded answers (parallel citation-chasing)
1. **`feat: deep-search engine — parallel bounded citation-chasing`** — new `backend/app/services/deep_search.py`: per-branch citation following (depth ≤5), authoritative-domain web search (FDA/PubMed-PMC/NICE/MedlinePlus/DailyMed/RxNorm), branches in parallel, budget ~120 s — all from registry `deep_search`. Replaces the Evidence-Floor terminal-only behavior (extends `evidence_floor.py` / `_expand_retrieval_if_needed`).
2. **`feat: strict-grounded, anti-sycophancy formatter prompt`** — `prompt_engine.py` (extend `ANTI_SYCOPHANCY_RULES`, evidence-only contract; LOE III from cited source only).
3. **`feat: deep-search SSE progress events`** — `rag_pipeline_stream.py` + `frontend` (`lib/api.ts`, `QueryProvider.tsx`, `query/page.tsx`): stream stage messages ("Standard sources thin — following citations from [source]…").
4. **`test: uncited-claim + sycophancy eval`** — `backend/tests/` lightweight check that fails on uncited claims / sycophantic phrasing.
- **Honest terminal:** "No evidence found" preserved as the rare last resort (never fabricate).

### Phase 6 — LangGraph orchestration
- **`refactor: process_query as LangGraph StateGraph`** — new `backend/app/services/pipeline_graph.py`; port every stage from AUDIT §7 with **identical semantics + timeouts**; conditional edges for the short-circuits; **parallel fetch** (extend existing `run_search_graph`) and **citation-chasing as parallel bounded cyclic subgraphs** (depth ≤5). Preserve Stage-7 load-bearing order. Record before/after latency in the journal.
- **Acceptance:** same inputs → same grounded outputs (modulo speed); measurable latency win on parallelizable queries; **no timing values changed** (constraint #4).

### Phase 7 — Cleanup & scalability
- **`chore: delete approved dead code`** — only AUDIT §5a items (frontend layer + Mermaid chain + `scripts/log_*.txt` + `mermaid` dep). One commit.
- **`chore: env hygiene`** — remove `IATRONIX_API_KEY`; add the missing-from-example vars (AUDIT §4); keep `UNCLEAR`/infra vars.
- **`chore: scalability`** — confirm stateless backend (shared Redis/Postgres, no local-disk request state); make worker/replica counts configurable in `docker-compose.dev.yml`; document scaling in one place.

### Phase 8 — Tests
- **`test: registry + adapters + caching + deep-search + graph`** — registry load, `/api/providers` output, adapter conformance (all providers), per-adapter caching, parallel citation-chasing (builds answer + "No evidence" terminal + respects depth-5/120 s), LangGraph wiring. Run full suite; report pass/fail honestly (don't weaken failing tests).

### Phase 9 — Docs (update, don't duplicate)
- **`docs: README + ENGINEERING_JOURNAL + agent docs + deploy`** — `README.md` (providers, dev ports, Lessons Learnt), new `ENGINEERING_JOURNAL.md` (full narrative from AUDIT §8), **`AGENT_ARCHITECTURE.md` + `AGENT_INTEGRATION_GUIDE.md`** updated to registry-as-single-surface + adapter + LangGraph + evidence-only contract (also fix the stale `backend/waves/` references). Frontend **`/lessons`** route rendering the full journal + link from About.

### Phase 10 — Ship to dev
- Push `dev`; rebuild **dev only** (`docker compose -f docker-compose.dev.yml up -d --build` — confirm flags from repo); health-check backend `/health` + `/api/providers` (Cerebras + Claude only) + Lessons page; on failure **stop & report** with rollback `git reset --hard ea457b9` (pre-push) / `git revert ea457b9..HEAD` (post-push). Final report: SHA, per-phase changes, tests, latency before/after, live dev URL.

---

## 3. Constraints honored (cross-check vs brief)
BYOK absolute (no server keys) · medical safety preserved/stricter (Evidence Floor + deep-search + honest no-evidence) · **dev only** · **no timing/backoff changes** (AUDIT §7.5 catalogued, ported verbatim) · no secrets committed (E1 fixes a violation) · no sycophancy (Phase 5) · **docs read before integration code** (Phase 2.5).

## 4. Rollback
Any phase: `git reset --hard ea457b9` (local/unpushed) or `git revert ea457b9..HEAD` (after push). Each functional change is its own commit, so any single step is revertable in isolation.

---

*End of REFACTOR_PLAN.md. Awaiting D1–D4 + E1–E4 before Phase 2.5.*
