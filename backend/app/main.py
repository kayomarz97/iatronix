import asyncio
import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from app.api.v1 import health, models, query
from app.api.v1 import providers as providers_module
from app.api.v1 import auth_routes, history as history_module
from app.api.v1 import version as version_module
from app.api.v1 import service_keys as service_keys_module
from app.api.v1 import waves as waves_module
from app.api.v1 import suggestions as suggestions_module
from app.api.v1 import openrouter_oauth as openrouter_oauth_module
from app.api.v1 import config_routes as config_routes_module
from app.config import settings
from app.middleware.firebase_auth import FirebaseAuthMiddleware
from app.middleware.payload_limit import PayloadLimitMiddleware
from app.middleware.rate_limit import PreAuthRateLimitMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.services.data_fetcher import init_http_client, shutdown_http_client
from app.services.rag_pipeline import init_log_queue, shutdown_log_queue

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Iatronix backend...")

    # Provider registry — fail fast if config/providers.yaml is missing/invalid.
    from app.services.provider_registry import get_registry, ProviderRegistryError
    try:
        _registry = get_registry()
        logger.info(
            "Provider registry OK: %d providers, enabled=%s",
            len(_registry.all_providers()),
            list(_registry.enabled_providers().keys()),
        )
    except ProviderRegistryError:
        logger.exception("Provider registry failed to load — refusing to start")
        raise

    # Fail fast if the BYOK encryption key is missing/invalid — never boot on a
    # random ephemeral key (would silently orphan every stored user API key).
    from app.services.byok import validate_encryption_key
    validate_encryption_key()

    await init_http_client()

    # Schema migrations (additive only — safe to run on existing tables)
    try:
        from app.db.session import engine
        from sqlalchemy import text

        async with engine.begin() as conn:
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS age INTEGER")
            )
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS gender VARCHAR(20)")
            )
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS openrouter_key VARCHAR")
            )
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS cerebras_api_key VARCHAR")
            )
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS xai_api_key VARCHAR")
            )
            # Backfill: migrate existing encrypted_llm_key to per-provider columns
            await conn.execute(text("""
                UPDATE users
                   SET cerebras_api_key = encrypted_llm_key
                 WHERE llm_provider = 'cerebras'
                   AND encrypted_llm_key IS NOT NULL
                   AND cerebras_api_key IS NULL
            """))
            await conn.execute(text("""
                UPDATE users
                   SET anthropic_api_key = encrypted_llm_key
                 WHERE llm_provider = 'anthropic'
                   AND encrypted_llm_key IS NOT NULL
                   AND anthropic_api_key IS NULL
            """))
        logger.info("Schema migration complete")
    except Exception as _e:
        logger.warning(f"Schema migration skipped: {_e}")

    # Sentry
    if settings.sentry_dsn:
        sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.1)

    # Redis
    try:
        app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        await app.state.redis.ping()
        logger.info("Redis connected")
    except Exception:
        logger.warning("Redis not available, running in degraded mode")
        app.state.redis = None

    # Log queue
    await init_log_queue()

    # NICE API key warning (UK/EU guidelines require API key for best results)
    if not settings.nice_api_key:
        logger.warning(
            "NICE_API_KEY not set — UK/EU clinical guidelines will have reduced coverage. "
            "Set NICE_API_KEY in .env to enable full guideline data."
        )

    # Expired document cleanup task
    async def _cleanup_expired_documents():
        """Background task: delete expired non-approved documents every N minutes."""
        from datetime import datetime, timezone
        from sqlalchemy import select
        from app.db.session import async_session as session_factory
        from app.models.document import Document
        from app.services import r2_storage as r2

        while True:
            await asyncio.sleep(settings.pdf_cleanup_interval_minutes * 60)
            try:
                async with session_factory() as session:
                    now = datetime.now(timezone.utc)
                    result = await session.execute(
                        select(Document).where(
                            Document.expires_at.isnot(None),
                            Document.expires_at <= now,
                        )
                    )
                    expired = result.scalars().all()
                    for doc in expired:
                        if doc.r2_key:
                            await r2.delete_pdf(doc.r2_key)
                        await session.delete(doc)
                    if expired:
                        await session.commit()
                        logger.info(
                            f"Cleanup: removed {len(expired)} expired documents"
                        )
            except Exception as exc:
                logger.error(f"Cleanup task error: {exc}")

    asyncio.create_task(_cleanup_expired_documents())

    async def _archive_and_purge_old_rows():
        """Background task (daily): archive old query_audit + query_cache rows to
        GCS, THEN delete them. A row is never deleted unless its archive succeeded
        (see app/services/retention.py)."""
        from datetime import datetime, timezone, timedelta
        from app.db.session import async_session as session_factory
        from app.models.query_audit import QueryAudit
        from app.models.query_cache import QueryCache
        from app.services import retention

        while True:
            await asyncio.sleep(86400)  # run once per day
            now = datetime.now(timezone.utc)
            try:
                n = await retention.archive_and_purge(
                    session_factory, QueryAudit, QueryAudit.timestamp,
                    now - timedelta(days=settings.audit_retention_days), "query_audit",
                )
                logger.info("Audit retention: archived+purged %d rows", n)
            except Exception as exc:
                logger.error(f"Audit retention error: {exc}")
            try:
                # query_embedding is a large, regenerable vector — exclude from the archive.
                n = await retention.archive_and_purge(
                    session_factory, QueryCache, QueryCache.created_at,
                    now - timedelta(days=settings.query_cache_retention_days), "query_cache",
                    exclude=("query_embedding",),
                )
                logger.info("Cache retention: archived+purged %d rows", n)
            except Exception as exc:
                logger.error(f"Cache retention error: {exc}")

    asyncio.create_task(_archive_and_purge_old_rows())

    yield

    # Shutdown
    await shutdown_http_client()
    await shutdown_log_queue()
    if app.state.redis:
        await app.state.redis.close()
    logger.info("Iatronix backend stopped")


app = FastAPI(
    title="Iatronix Medical RAG API",
    version="0.1.0",
    lifespan=lifespan,
    default_response_class=ORJSONResponse,
    # Do not expose the API surface publicly unless explicitly enabled (dev only).
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
)

# Middleware order: outermost first → SecurityHeaders → Payload → PreAuth Rate Limit → API Key Auth
# (FastAPI adds in reverse order, so add innermost first)
app.add_middleware(FirebaseAuthMiddleware)
app.add_middleware(PreAuthRateLimitMiddleware)
app.add_middleware(PayloadLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

# CORS
origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
# Credentialed CORS with a wildcard origin is unsafe: Starlette would reflect any
# Origin back with Access-Control-Allow-Credentials: true. Refuse rather than
# silently allow every website to make authenticated cross-origin calls.
if "*" in origins:
    raise RuntimeError(
        "ALLOWED_ORIGINS must be explicit origin(s), not '*', because "
        "allow_credentials=True. Set ALLOWED_ORIGINS to your exact domain(s)."
    )
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(health.router, prefix="/api/v1")
app.include_router(auth_routes.router, prefix="/api/v1")
app.include_router(models.router, prefix="/api/v1")
app.include_router(query.router, prefix="/api/v1")
app.include_router(history_module.router, prefix="/api/v1")
app.include_router(version_module.router, prefix="/api/v1")
app.include_router(service_keys_module.router, prefix="/api/v1")
app.include_router(waves_module.router, prefix="/api/v1")
app.include_router(suggestions_module.router, prefix="/api/v1")
app.include_router(openrouter_oauth_module.router, prefix="/api/v1")
app.include_router(config_routes_module.router, prefix="/api/v1")
app.include_router(providers_module.router, prefix="/api/v1")
