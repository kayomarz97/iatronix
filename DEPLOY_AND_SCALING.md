# Deploy (dev) & Scaling — for humans and agents

> **Dev only.** Never rebuild prod (`docker-compose.prod.yml`) without explicit
> owner instruction. Dev = `med.debkay.com` (ports 3201 / 8201).

## Deploy to dev

```bash
cd /root/projects/med-ai-project
git checkout dev

# 1. Rebuild + start ONLY the dev stack (confirm the filename from the repo)
docker compose -f docker-compose.dev.yml up -d --build

# 2. Run additive migrations (also auto-run in the backend lifespan)
docker compose -f docker-compose.dev.yml exec iatronix-dev-backend alembic upgrade head
```

## Health-check (must all pass before declaring success)

```bash
# Backend liveness
curl -s http://127.0.0.1:8201/api/v1/health        # {"status":"healthy",...}

# Provider registry is serving the active set (Cerebras + Claude ONLY)
curl -s http://127.0.0.1:8201/api/v1/providers | jq '.providers | keys'
#   => ["anthropic","cerebras"]
curl -s http://127.0.0.1:8201/api/v1/config/llm | jq '.default_provider'   # "cerebras"

# Frontend loads + Lessons page renders and is linked from About
curl -sI http://127.0.0.1:3201/ | head -1          # 200
curl -sI http://127.0.0.1:3201/lessons | head -1   # 200

# Container-only test suites (couldn't run in the local dev env)
docker compose -f docker-compose.dev.yml exec iatronix-dev-backend \
  python -m pytest backend/tests -q
```

## Logs

```bash
docker compose -f docker-compose.dev.yml logs -f iatronix-dev-backend
docker compose -f docker-compose.dev.yml logs -f iatronix-dev-frontend
```

## Rollback (to the Phase 0 checkpoint)

```bash
# Pre-push (local only): hard reset
git reset --hard ea457b9          # tag: pre-refactor-20260530

# Post-push (shared dev branch): safe revert, no force-push
git revert ea457b9..HEAD

# then rebuild dev as above
```

## Post-deploy flags to flip ON once verified

Both default OFF so the rebuild is behaviour-neutral; enable in `.env.dev` then restart:

- `DEEP_SEARCH_ENABLED=true` — parallel citation-chasing for thin retrieval.
- `KEYSTORE_FIRESTORE_ENABLED=true` (+ Firestore creds) — dual-write BYOK keys to Firestore.

## Scaling (horizontal)

The backend is **stateless** — no in-process session/request state; everything
shared lives in Postgres + Redis. The only local-disk request state (PDF
ingestion) was removed. So it scales horizontally by adding replicas:

- **Workers per replica:** `GUNICORN_WORKERS` (env / `docker-compose.dev.yml`
  `environment:`). Tune to ~2x vCPU.
- **Replicas:** `docker compose -f docker-compose.dev.yml up -d --scale iatronix-dev-backend=N`
  (put nginx in front to load-balance), or `deploy.replicas: N` under an
  orchestrator. The provider registry, KeyStore, caches, and breakers are all
  process-safe and read shared state, so N replicas behave identically.
- **Registry config** is baked into the image (`COPY config/ config/`); every
  replica ships identical `providers.yaml`. To hot-reload instead, mount it and
  set `PROVIDERS_CONFIG_PATH`.
