import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import auth, health, models, query
from app.config import settings
from app.middleware.api_key_auth import ApiKeyAuthMiddleware
from app.middleware.payload_limit import PayloadLimitMiddleware
from app.middleware.rate_limit import PreAuthRateLimitMiddleware
from app.services.drug_linker import load_drug_dictionary
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

    # Sentry
    if settings.sentry_dsn:
        sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.1)

    # Redis
    try:
        app.state.redis = aioredis.from_url(
            settings.redis_url, decode_responses=True
        )
        await app.state.redis.ping()
        logger.info("Redis connected")
    except Exception:
        logger.warning("Redis not available, running in degraded mode")
        app.state.redis = None

    # Drug dictionary
    load_drug_dictionary()

    # Log queue
    await init_log_queue()

    yield

    # Shutdown
    await shutdown_log_queue()
    if app.state.redis:
        await app.state.redis.close()
    logger.info("Iatronix backend stopped")


app = FastAPI(
    title="Iatronix Medical RAG API",
    version="0.1.0",
    lifespan=lifespan,
)

# Middleware order: outermost first → Payload → PreAuth Rate Limit → API Key Auth
# (FastAPI adds in reverse order, so add innermost first)
app.add_middleware(ApiKeyAuthMiddleware)
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
app.include_router(auth.router, prefix="/api/v1")
app.include_router(models.router, prefix="/api/v1")
app.include_router(query.router, prefix="/api/v1")
