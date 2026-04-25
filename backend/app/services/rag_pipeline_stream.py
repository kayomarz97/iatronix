"""SSE streaming wrapper around process_query.

Yields server-sent event strings:
  event: stage\\ndata: {"stage": "classifying"|"fetching"|"generating"}\\n\\n
  event: token\\ndata: {"text": "..."}\\n\\n
  event: done\\ndata: {"result": {...QueryResponse...}}\\n\\n
  event: error\\ndata: {"detail": "..."}\\n\\n
"""
from __future__ import annotations

import asyncio
import json
import logging

from app.services.rag_pipeline import process_query

logger = logging.getLogger(__name__)

_SENTINEL = object()


async def stream_query(
    request,
    redis_client=None,
    user_key_id: str | None = None,
    user=None,
):
    """Async generator that runs process_query and yields SSE-formatted strings."""
    queue: asyncio.Queue = asyncio.Queue()

    async def token_callback(text: str) -> None:
        await queue.put(("token", text))

    async def structured_callback(event_type: str, data: object) -> None:
        await queue.put((event_type, data))

    async def run() -> None:
        try:
            result = await process_query(
                request,
                redis_client=redis_client,
                user_key_id=user_key_id,
                user=user,
                token_callback=token_callback,
                structured_callback=structured_callback,
            )
            await queue.put(("done", result))
        except Exception as exc:
            logger.exception("stream_query error")
            err_str = str(exc)
            is_rate_limit = "429" in err_str or "rate_limit" in err_str.lower() or "overloaded" in err_str.lower()
            err_payload = {
                "detail": "Service temporarily busy. Your partial results are preserved." if is_rate_limit else err_str,
                "error_type": "rate_limit" if is_rate_limit else "pipeline_error",
            }
            await queue.put(("error", err_payload))
        finally:
            await queue.put(_SENTINEL)

    yield f"event: stage\ndata: {json.dumps({'stage': 'classifying'})}\n\n"

    pipeline_task = asyncio.create_task(run())

    async def _emit_fetching():
        await asyncio.sleep(1.2)
        await queue.put(("stage", "fetching"))

    asyncio.create_task(_emit_fetching())

    try:
        while True:
            item = await queue.get()
            if item is _SENTINEL:
                break

            kind, payload = item
            if kind == "stage":
                yield f"event: stage\ndata: {json.dumps({'stage': payload})}\n\n"
            elif kind == "token":
                yield f"event: token\ndata: {json.dumps({'text': payload})}\n\n"
            elif kind == "bluf":
                yield f"event: bluf\ndata: {json.dumps(payload)}\n\n"
            elif kind == "fetch_articles":
                yield f"event: fetch_articles\ndata: {json.dumps(payload)}\n\n"
            elif kind == "section_complete":
                yield f"event: section_complete\ndata: {json.dumps(payload)}\n\n"
            elif kind == "done":
                yield f"event: done\ndata: {json.dumps({'result': payload.model_dump()})}\n\n"
                break
            elif kind == "error":
                yield f"event: error\ndata: {json.dumps(payload)}\n\n"
                break
    finally:
        pipeline_task.cancel()
        try:
            await asyncio.shield(asyncio.gather(pipeline_task, return_exceptions=True))
        except (asyncio.CancelledError, Exception):
            pass
