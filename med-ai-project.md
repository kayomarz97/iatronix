---
type: project
tags: [language/python, language/typescript, status/active, domain/medical-ai]
github: iatronix
related: ["[[RAGnosis]]", "[[transbench]]", "[[TransBench-demo]]", "[[Medical-Waves]]", "[[autoresearch-iatronix]]"]
---
# Iatronix (med-ai-project)

## What it is
Iatronix is an evidence-based medical reference engine for clinicians: you ask a clinical question and it retrieves live data from 10+ authoritative medical APIs in parallel, ranks it by evidence quality, then uses your own LLM key to format a structured, citable answer — with a Level of Evidence (LOE) and Class of Recommendation (COR) attached to every claim. Its guiding principle is that the LLM is an editor of retrieved evidence, never the source of facts, so no LLM token is spent until real citable evidence exists. Live at med.kayomarz.com.

Technically it is a Python 3.11 + FastAPI backend (RAG/agentic pipeline built with LangGraph + DSPy) paired with a Next.js 15 / React 19 frontend, deployed on Google Cloud Run with Postgres/pgvector, Redis, and Firebase auth. This is the `kayomarz97/iatronix` repo — the canonical Iatronix backend + frontend.

## What it entails
- `backend/app/` — FastAPI app. `main.py` entry, `config.py` (single source of truth for all feature flags + limits), `api/v1/` (route handlers incl. `query.py`).
- `backend/app/services/` — the engine (~50 modules): `rag_pipeline.py` (~4.6k-line orchestrator, `process_query()`), `rag_pipeline_stream.py` + `stream_jobs.py` (SSE + resumable streaming), `data_fetcher.py` (parallel medical-API fetch, NCBI throttling), `ranking.py` (evidence scoring/floors), `article_registry.py` (`[REF_N]` tokens, real citation URLs), `prompt_engine.py`, `grounding_gate.py`, `evidence_floor.py`, `stance_neutralizer.py`, `byok.py` (Fernet-encrypted key storage), `llm_factory.py`/`provider_registry.py`/`model_registry.py`, `semantic_cache.py`/`cache.py`, `spirometry_ai.py` (Waves), `deep_search.py`, `citation_graph.py`.
- `backend/config/providers.yaml` — one file driving backend routing AND the frontend key/model picker (BYOK: Cerebras default + Anthropic Claude).
- `backend/app/models/` — SQLAlchemy models (user, service_key, query_audit/cache/log, search_history, document).
- `frontend/src/` — Next.js app (`app/`, `components/` incl. `AdaptiveResultRenderer.tsx`, `hooks/`, `lib/`); Firebase client SDK.
- Ops: `docker-compose.{dev,prod}.yml`, `nginx/`, `.github/workflows/deploy.yml` (push-to-`main` CI/CD via Workload Identity Federation), retention archival to GCS.
- Deep docs: `README.md`, `.claude/INDEX.md`, `AGENT_ARCHITECTURE.md`, `AGENT_INTEGRATION_GUIDE.md`.

## How it works
Query → `api/v1/query.py` → `rag_pipeline.process_query()` classifies into one of 6 types, extracts entities, and neutralizes loaded phrasing → scope check → `data_fetcher.py` fetches in parallel from PubMed, StatPearls, FDA/DailyMed, NICE, ClinicalTrials.gov, etc. (zero LLM tokens here) → `ranking.py` scores for quality + aboutness with an evidence floor → `article_registry.py` mints immutable article-level `[REF_N]` citations → `prompt_engine.py` builds one BLUF prompt + one prompt per section (parallel) → LLM writes JSON citing `[REF_N]` → pipeline resolves tokens back to real articles and `grounding_gate.py` demotes/drops any ungrounded claim. Streaming uses the same event source, optionally persisted to Redis to survive disconnects. Risky behavior sits behind feature flags (default False in `config.py`).

## Change impact / blast radius
- **Upstream (this depends on):** 10+ external medical APIs (NCBI/PubMed, StatPearls, FDA, NICE, ClinicalTrials, iCite); user-supplied LLM provider keys (Cerebras, Anthropic Claude); Postgres+pgvector, Redis, Firebase auth, Google Cloud Run/Storage.
- **Downstream (depends on this):** [[transbench]] / [[TransBench-demo]] reuse the Iatronix backend read-only (external coupling; no in-repo reference found). The Waves spirometry feature (`spirometry_ai.py`) may relate to [[Medical-Waves]]. [[autoresearch-iatronix]] reads this codebase to generate improvement suggestions.
- **Parallel / shared (can break if touched):** `providers.yaml` is shared by backend routing and the frontend picker — a change breaks both at once. `config.py` feature flags gate almost every behavior. `prompt_engine.py`'s static system prefix is byte-identical on purpose for prompt caching.
- **⚠️ Danger zones (touch with care):** `rag_pipeline.py` (huge orchestrator + citation post-processing chain); `data_fetcher.py` NCBI throttling (never add un-throttled NCBI calls — logged in the mistakes ledger); `grounding_gate.py` (small but high-leverage); bumping `prompt_version` to bust stale caches; the `.env*` files hold real secrets; pushing to `main` triggers production CI/CD deploy.

## Related projects
- [[RAGnosis]] — the clinical benchmark harness used to measure this backend's faithfulness/hallucination rate.
- [[transbench]] / [[TransBench-demo]] — reportedly reuse this Iatronix backend read-only.
- [[Medical-Waves]] — likely tied to the in-app "Waves" spirometry/ECG analysis feature.
- [[autoresearch-iatronix]] — autoresearch loop that reviews this codebase.

Note: `.git` remote is `github.com/kayomarz97/iatronix.git`; last commit 2026-08-03 (active).
