import asyncio
import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from app.api.v1 import health, models, query
from app.api.v1 import auth_routes, documents, history as history_module
from app.api.v1 import version as version_module
from app.api.v1 import service_keys as service_keys_module
from app.config import settings
from app.middleware.firebase_auth import FirebaseAuthMiddleware
from app.middleware.payload_limit import PayloadLimitMiddleware
from app.middleware.rate_limit import PreAuthRateLimitMiddleware
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

    async def _purge_old_audit_logs():
        """Background task: delete query_audit rows older than 30 days."""
        from datetime import datetime, timezone, timedelta
        from sqlalchemy import delete as sa_delete
        from app.db.session import async_session as session_factory
        from app.models.query_audit import QueryAudit

        while True:
            await asyncio.sleep(86400)  # run once per day
            try:
                cutoff = datetime.now(timezone.utc) - timedelta(days=30)
                async with session_factory() as session:
                    await session.execute(
                        sa_delete(QueryAudit).where(QueryAudit.timestamp < cutoff)
                    )
                    await session.commit()
                    logger.info("Audit purge: removed rows older than 30 days")
            except Exception as exc:
                logger.error(f"Audit purge error: {exc}")

    asyncio.create_task(_purge_old_audit_logs())

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
)

# Middleware order: outermost first → Payload → PreAuth Rate Limit → API Key Auth
# (FastAPI adds in reverse order, so add innermost first)
app.add_middleware(FirebaseAuthMiddleware)
app.add_middleware(PreAuthRateLimitMiddleware)
app.add_middleware(PayloadLimitMiddleware)

# CORS
origins = [o.strip() for o in settings.allowed_origins.split(",")]
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
app.include_router(documents.router, prefix="/api/v1")
app.include_router(history_module.router, prefix="/api/v1")
app.include_router(version_module.router, prefix="/api/v1")
app.include_router(service_keys_module.router, prefix="/api/v1")
