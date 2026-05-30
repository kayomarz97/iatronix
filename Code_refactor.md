# /goal — Iatronix: provider-agnostic refactor, deep-grounded answers, LangGraph, polish & deploy to dev

You are working on the `iatronix` repo (Next.js frontend + FastAPI backend, Postgres/pgvector + Redis, Docker Compose, Cloudflare). Read this whole brief before doing anything. **Do Phase 0–2 first, then STOP and wait for my approval before any destructive change (deleting code, removing toggles, changing pipeline behavior).**

---

## Non-negotiable constraints (never violate)

1. **BYOK stays absolute.** No server-side LLM keys, no fallback to a server key, no local LLMs. Keys stay encrypted per-user (Fernet) exactly as now.
2. **Medical safety > everything.** Fail-closed behavior must be preserved or made *stricter*, never looser. No confident output from ungrounded data. (See Phase 5 for how this reconciles with "never degrade.")
3. **Dev only.** All deploy/rebuild steps target the **dev** stack (`docker-compose.dev.yml`) — never touch prod (`docker-compose.prod.yml`). Read the actual dev compose file for the correct ports/service names; do not assume them.
4. **Do not change timing/backoff/delays unless you can prove a specific bug.** The per-source 20s timeouts, retries, inter-call spacing, and rate-limit handling are intentional. If you think one is wrong, write down *why* in the plan and ask — do not silently change it. Default action: document the rationale in a comment, leave the value alone.
5. **Never commit secrets.** Only `.env.example` is touched/committed. Real `.env` stays gitignored.
6. **No sycophancy, ever.** Generated answers state facts found in retrieved sources. No flattery, no hedging filler, no "as an expert I'd say." If a fact isn't in a fetched source, it doesn't go in the answer.
7. **Read the official docs before writing any integration code** (see Phase 2.5). Do not write adapters or the LangGraph graph from memory — APIs drift.

---

## Phase 0 — Checkpoint (do this first, report back)

1. Confirm you're on the `dev` branch (`git branch --show-current`). If not, switch to it.
2. Commit any uncommitted work-in-progress with a clear message so nothing is lost.
3. Create a restore point and **report the exact commit SHA + revert command** to me:
   - `git tag -a pre-refactor-$(date +%Y%m%d) -m "checkpoint before provider-agnostic refactor"`
   - Print: the short SHA, and the literal command I can run to get back here:
     `git reset --hard <SHA>` (full reset) **and** `git revert <SHA>..HEAD` (safe revert that keeps history).
4. Tell me which one you recommend and why.

> Deliverable of Phase 0: "Checkpoint = `<SHA>`. To roll back: `<command>`."

---

## Phase 1 — Audit (no edits yet)

Do a **structured audit**, not a literal line-by-line dump into context. Produce a short `AUDIT.md` in the repo with:

1. **File map** of `backend/` and `frontend/` — every source file, one line each on what it does.
2. **Provider/model touch-points** — every place a provider or model name is hardcoded (grep for `anthropic`, `openai`, `openrouter`, `cerebras`, `google`, `gemini`, `grok`, `xai`, `claude`, `haiku`, `sonnet`, `gpt`, model IDs, etc.) in both backend and frontend. This is the list that has to collapse to one config file.
3. **Env toggle inventory** — every variable in `.env.example`; for each, grep the codebase and mark `USED` / `UNUSED` / `UNCLEAR`. Don't delete yet — just classify.
4. **Redundant/dead code candidates** — duplicated logic, unreachable code, leftover experiment files. List with file + line + why. Don't delete yet.
5. **Prompt-caching touch-points** — where each provider's caching is currently implemented (note: Cerebras caching is already working — preserve it).
6. **Pipeline orchestration** — how the 7-stage pipeline is currently wired (sequential calls, asyncio.gather, etc.), so we know what LangGraph will replace, including where DegradedResponse is currently triggered.
7. **Git-history learnings** — run `git log --oneline` and skim notable commits; collect recurring themes, reversals, and hard-won fixes for the docs phase.

> Deliverable of Phase 1: `AUDIT.md`. Then continue to Phase 2 without stopping.

---

## Phase 2 — Plan, then STOP

Write `REFACTOR_PLAN.md` covering everything below as concrete, ordered steps with the files each step touches. **Each functional change = its own commit** so any single change is independently revertable.

Then **stop and wait for my explicit approval.** Surface these decisions for me to confirm (don't guess):

- **D1 — Available providers:** build adapters for **Anthropic (Claude), Cerebras, Google (Gemini), and xAI (Grok)** — plus keep OpenAI/OpenRouter adapters if already present. All wired to work **both frontend and backend**, all behind a registry `enabled` flag so I can activate any of them anytime with no code change. **Enabled now: Cerebras + Claude.** Google, Grok (and OpenAI/OpenRouter) ship as `enabled: false`.
- **D2 — Prompt caching:** Cerebras prompt caching is confirmed working in production — keep its current implementation intact, just move it behind the adapter interface. For Google and Grok, read their docs (Phase 2.5) and implement their native caching; if a provider has none, it's a documented no-op.
- **D3 — Deep-grounded answers (replaces old fallback):** remove the training-data generation fallback. New behavior in Phase 5 — confirm the depth/time ceiling there.
- **D4 — "Redundant code" definition:** confirm you may delete only the items in the `AUDIT.md` dead-code list, and nothing that's merely "unused-looking" but reachable.

---

## Phase 2.5 — Documentation review (before writing ANY adapter or graph code)

Fetch and read the **current official docs** for each thing you're about to integrate, and capture the exact API shapes, parameter names, model IDs, and caching mechanisms in `INTEGRATION_NOTES.md`. Do not code adapters or the graph from memory. At minimum:

- **LangGraph** — `StateGraph`, nodes, conditional edges, parallel/fan-out execution, state reducers. (langchain-ai.github.io/langgraph)
- **Anthropic** — Messages API + `cache_control` prompt caching. (docs.anthropic.com)
- **Cerebras** — inference API + prompt caching (match what already works in the app). (inference-docs.cerebras.ai)
- **Google Gemini** — API + context caching. (ai.google.dev)
- **xAI Grok** — API + any caching support. (docs.x.ai)
- Any other external API you touch (PubMed/NCBI, OpenFDA, RxNorm, DailyMed, MedlinePlus, NICE, Unpaywall, embeddings providers).

> Deliverable: `INTEGRATION_NOTES.md` with verified, dated API facts and source links. If a doc contradicts an assumption in the plan, flag it before coding.

---

## Phase 3 — Provider-/model-agnostic architecture (after approval)

Goal: **changing or adding a model/provider requires editing exactly one file.**

1. Create a **single source-of-truth registry** at repo root, e.g. `config/providers.yaml`. Each entry: provider id, display name, `enabled` flag, models list, default model per query type, embedding model, `supports_caching` flag, API base URL, env var name for *non-secret* settings.
2. **Backend** loads this registry on startup. All provider/model selection in the pipeline (classifier routing, formatter model choice, embeddings) reads from it — **zero hardcoded provider/model strings** anywhere else. Refactor each provider into an **adapter** implementing a common interface (`generate`, `embed`, `apply_cache`, `supports_caching`). Adding a provider = new adapter + one registry entry.
3. **Backend exposes** `GET /api/providers` returning only `enabled` providers/models (never secrets).
4. **Frontend renders providers/models dynamically** from `/api/providers`. **No provider or model name is hardcoded in the frontend** — key-entry UI and model picker are generated from the API response. This is what makes "edit one file → both FE and BE update" true.
5. Registry state: **Cerebras + Claude `enabled: true`**; Google, Grok, OpenAI, OpenRouter `enabled: false` (per D1) — fully wired so flipping the flag activates them on both FE and BE with no other edit.
6. Add adapters: **Cerebras** (preserve existing working caching), **Google (Gemini)**, **xAI (Grok)** — built from the verified `INTEGRATION_NOTES.md`, not memory.

> Acceptance: grep proves no hardcoded provider/model strings outside the registry + adapter files. Flipping `enabled` on any provider in the registry changes both the API response and the UI with no other edits.

---

## Phase 4 — Provider-agnostic prompt caching

1. Caching lives behind the adapter interface: each adapter implements its own strategy (Anthropic `cache_control`; Cerebras as it currently works; Google context caching; Grok per docs; no-op where unsupported).
2. The pipeline calls a single `adapter.apply_cache(...)` — it must not know which provider it's talking to.
3. Caching must keep working when the active provider changes, and degrade to no-op (not error) for providers without support.

> Acceptance: switching the enabled provider does not break caching; Cerebras and Anthropic both show reduced input cost on repeat calls; an unsupported provider runs cleanly with caching off.

---

## Phase 5 — Deep-grounded answers (no sycophancy, no training-data opinion, citation-chasing)

1. Rewrite the formatter system prompt so output is **strictly grounded in fetched sources**, cites source indices, and contains **no flattery, no hedging filler, no model-knowledge claims**. Every clinical claim traces to a fetched source or it is omitted.
2. **Replace the old timeout fallback with deep grounded retrieval.** When the first retrieval pass is thin, do NOT return a quick degraded response. Instead:
   - If at least one relevant article is found, **follow its citations** (and the references those cite) and/or run authoritative-domain web searches (FDA, PubMed/PMC, NICE, MedlinePlus, DailyMed, RxNorm, etc.), pulling more grounded detail and assembling an answer with links.
   - The varied searches run as **parallel agents** — each independent search branch chases citations concurrently, so the depth is reached without serializing the wall-clock time.
   - Repeat until a grounded answer is built **or** the chasing budget is exhausted.
   - **Bounded:** citation-chasing depth ≤ **5** per search branch, branches run **in parallel**, and the total deep-search budget ≈ **120s**, all **configurable in the registry**.
3. **Honest terminal state (medical-safety requirement):** if the parallel branches + web search genuinely find nothing adequate within the budget, the system must say so truthfully — shown as a clear **"No evidence found"** result, not a confident answer assembled from inadequate sources. This should be rare, but it must remain possible. **Never fabricate to avoid it.**
4. **Frontend deep-search indicator:** when citation-chasing/deep search engages, **stream progress to the UI** so the user knows why it's slower than a normal search — e.g. "Standard sources thin — following citations from [source]…", "Searching NICE / PubMed for primary evidence…". Show the stage, not a generic spinner.
5. Keep/strengthen the five hallucination guards (evidence grounding, fail-closed gate, citation validation, structural LOE/COR assignment, query-focused retrieval). LOE III "expert opinion" must come from a *cited source*, never the model's own voice.
6. Add a lightweight check/eval that fails if an answer contains uncited claims or sycophantic phrasing.

---

## Phase 6 — LangGraph for speed

1. Refactor the 7-stage pipeline orchestration into a **LangGraph `StateGraph`** (built per the verified `INTEGRATION_NOTES.md`), preserving every existing stage's semantics.
2. **Parallelize** independent work (the multi-source data fetch in stage 4) as concurrent nodes; use **conditional edges** for the short-circuits (semantic-cache hit → return; evidence below threshold → deep-search loop, not instant degrade; sparse → second pass). Model the citation-chasing from Phase 5 as **parallel bounded cyclic sub-graphs** (one branch per varied search, depth ≤ 5, fanned out concurrently).
3. **Preserve all existing timeouts/backoff** (constraint #4) — port them as-is into the graph nodes.
4. Measure: record before/after latency on a few representative queries; put the numbers in the journal.

> Acceptance: same inputs → same grounded outputs (modulo speed), measurable latency improvement on parallelizable queries, no timing values changed.

---

## Phase 7 — Cleanup & scalability

1. Delete only the approved dead/redundant code from `AUDIT.md` (D4). One clearly-described commit.
2. Remove only the `UNUSED` env toggles from `.env.example` and code (approved in Phase 1). Keep `UNCLEAR` ones and ask.
3. **Scalability:** keep backend stateless (no in-process session state), confirm horizontal-scaling readiness (shared Redis/Postgres, no local-disk request state), make worker/replica counts configurable in the dev compose file, and document how to scale in one place.

---

## Phase 8 — Tests

1. Run the existing test suite; report pass/fail.
2. Add minimal tests for changed paths: registry loading, `/api/providers` output, adapter interface conformance (all four providers), prompt caching per adapter, the parallel citation-chasing (builds an answer + the "No evidence found" terminal state + respects the depth-5/120s bounds), and LangGraph graph wiring.
3. Don't mark done until tests pass. If a test was already failing, say so — don't weaken it to pass.

---

## Phase 9 — Docs (update existing, don't duplicate)

1. **README.md** — update providers to Cerebras + Claude active (Google/Grok available), fix local-run ports to match the dev compose, keep + expand "Lessons learnt."
2. **`ENGINEERING_JOURNAL.md`** (new, full article) — the detailed narrative: for each data source / design choice, *why* it was used, what I learned, every learning made while building it, plus the themes pulled from git history in Phase 1. This is the source of truth for the public "Lessons Learnt" article.
3. **Frontend "Lessons Learnt" article** — add a route (e.g. `/lessons`) that renders the full `ENGINEERING_JOURNAL.md` content as a proper article (headings, readable layout). **Add a link to it from the "About" section** on the frontend. It must be the complete article, not a teaser.
4. **AGENT_ARCHITECTURE.md** + **AGENT_INTEGRATION_GUIDE.md** — update so any AI agent can read the repo and understand the registry as the single config surface, the adapter interface, the LangGraph pipeline (incl. the citation-chasing sub-graph), and the evidence-only contract.
5. **Deploy commands** — a clear section for humans *and* agents: exact dev build/up, health-check, logs, and rollback to the Phase 0 checkpoint.

---

## Phase 10 — Ship to dev

1. Push the `dev` branch.
2. Rebuild **dev** containers only (`docker compose -f docker-compose.dev.yml up -d --build` — confirm filename/flags from the repo first).
3. **Health-check:** hit backend health/docs, load the frontend, confirm `/api/providers` returns Cerebras + Claude only, and verify the Lessons Learnt page renders and is linked from About.
4. If rebuild or health-check fails, **stop and report** with the Phase 0 rollback command — don't patch around it blindly.
5. Final report: checkpoint SHA, what changed per phase, test results, latency before/after, and the live dev URL/port.

---

## Definition of done

- One registry file controls all providers/models for both FE and BE; Cerebras + Claude active; Google + Grok (+ OpenAI/OpenRouter) wired and one-flag-away.
- No hardcoded provider/model strings outside the registry/adapters.
- Caching is provider-agnostic; Cerebras caching preserved and working.
- No sycophancy; every claim cited; parallel deep citation-chasing (depth 5, ~120s) replaces the training-data fallback; honest "No evidence found" state preserved as rare last resort; deep-search progress shown in the UI.
- Pipeline runs on LangGraph with parallel fetch + parallel bounded citation-chasing; no timing values changed.
- Dead code + unused toggles removed (approved set only); app is horizontally scalable.
- Tests pass; README + full Lessons Learnt journal/article + agent docs + deploy commands done; Lessons Learnt linked from About.
- All integrations built from verified docs (`INTEGRATION_NOTES.md`), not memory.
- Dev stack rebuilt, healthy, and serving.