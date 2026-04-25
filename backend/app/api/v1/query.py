import asyncio
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.config import settings
from app.schemas.query import QueryRequest, QueryResponse
from app.services.circuit_breaker import anthropic_breaker, openai_breaker
from app.services.rag_pipeline import process_query
from app.services.rag_pipeline_stream import stream_query

logger = logging.getLogger(__name__)
router = APIRouter()


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

    async def event_generator():
        try:
            async for chunk in stream_query(body, redis_client, user_key_id, user=user):
                yield chunk
        except asyncio.CancelledError:
            logger.info("SSE stream cancelled — client disconnected")
        except Exception:
            logger.exception("SSE stream error")
            import json
            yield f"event: error\ndata: {json.dumps({'detail': 'Internal server error'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
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
        return JSONResponse(content=response.model_dump(), headers=headers)
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
