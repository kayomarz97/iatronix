import asyncio
import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.config import settings
from app.schemas.query import QueryRequest, QueryResponse
from app.services.circuit_breaker import anthropic_breaker, openai_breaker
from app.services.rag_pipeline import process_query
from app.services.rag_pipeline_stream import stream_query
from app.services.stream_jobs import start_job, tail_job

logger = logging.getLogger(__name__)
router = APIRouter()

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


@router.post("/query/stream")
async def query_stream_endpoint(request: Request, body: QueryRequest):
    redis_client = getattr(request.app.state, "redis", None)
    user_key_id = getattr(request.state, "key_id", None)
    user = getattr(request.state, "user", None)

    if (
        user
        and not user.scopes.get("query", False)
        and user.role not in ("admin", "user")
    ):
        return JSONResponse(status_code=403, content={"detail": "Insufficient scope for query"})

    # ── Durable, resumable path ──────────────────────────────────────────────
    # The query runs in a detached background task that persists every event to a
    # Redis stream, so a client disconnect (mobile tab switch / screen off) never
    # cancels the computation. Disconnecting only cancels the *reader* (tail_job).
    # Requires Redis as the event-log source of truth; falls back to legacy otherwise.
    if settings.resumable_stream_enabled and redis_client is not None:
        if body.job_id:
            # Resume an in-flight (or just-finished) job — replay from the client's cursor.
            async def resume_gen():
                try:
                    async for chunk in tail_job(
                        redis_client, body.job_id, last_id=body.last_event_id or "0"
                    ):
                        yield chunk
                except asyncio.CancelledError:
                    logger.info("SSE resume tail cancelled — client disconnected (job continues)")

            return StreamingResponse(
                resume_gen(), media_type="text/event-stream", headers=_SSE_HEADERS
            )

        # Fresh query — launch the detached producer, hand the client its job_id, then tail.
        job_id = await start_job(body, redis_client, user_key_id, user)

        async def job_gen():
            yield f"event: job\ndata: {json.dumps({'job_id': job_id})}\n\n"
            try:
                async for chunk in tail_job(redis_client, job_id, last_id="0"):
                    yield chunk
            except asyncio.CancelledError:
                logger.info("SSE tail cancelled — client disconnected (job %s continues)", job_id)

        return StreamingResponse(
            job_gen(), media_type="text/event-stream", headers=_SSE_HEADERS
        )

    # ── Legacy connection-coupled path (unchanged behaviour) ─────────────────
    async def event_generator():
        try:
            async for chunk in stream_query(body, redis_client, user_key_id, user=user):
                yield chunk
        except asyncio.CancelledError:
            logger.info("SSE stream cancelled — client disconnected")
        except Exception:
            logger.exception("SSE stream error")
            yield f"event: error\ndata: {json.dumps({'detail': 'Internal server error'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.post("/query", response_model=QueryResponse)
async def query_endpoint(request: Request, body: QueryRequest):
    redis_client = getattr(request.app.state, "redis", None)
    user_key_id = getattr(request.state, "key_id", None)

    # Check scope
    user = getattr(request.state, "user", None)
    if (
        user
        and not user.scopes.get("query", False)
        and user.role not in ("admin", "user")
    ):
        return JSONResponse(
            status_code=403, content={"detail": "Insufficient scope for query"}
        )

    try:
        response = await asyncio.wait_for(
            process_query(body, redis_client, user_key_id, user=user),
            timeout=settings.pipeline_timeout_seconds,
        )
        headers = {
            "X-CB-Anthropic": anthropic_breaker.current_state,
            "X-CB-OpenAI": openai_breaker.current_state,
        }
        response_dict = response.model_dump()
        # X-Test-Mode: 1 gates debug emission — never surfaced in production requests
        if request.headers.get("X-Test-Mode") == "1":
            response_dict["debug"] = {
                "original_query": body.query,
                "neutralized_query": response.rewritten_query or body.query,
                # langgraph executes all three nodes on every API-fetch-enabled query
                "graph_nodes": ["fetch", "vector", "semantic_cache"],
            }
        return JSONResponse(content=response_dict, headers=headers)
    except asyncio.TimeoutError:
        logger.error("Pipeline timeout exceeded")
        return JSONResponse(
            status_code=504,
            content={
                "detail": "Request timed out. Try a simpler query or different model."
            },
        )
    except Exception:
        logger.error("Unexpected pipeline error", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )
