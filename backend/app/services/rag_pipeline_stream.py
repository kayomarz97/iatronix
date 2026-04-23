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

    async def run() -> None:
        try:
            # Emit stage events at pipeline checkpoints via a side-channel:
            # We can't easily hook into every stage, so we emit "generating" just before
            # process_query starts (the caller emits classifying/fetching beforehand).
            result = await process_query(
                request,
                redis_client=redis_client,
                user_key_id=user_key_id,
                user=user,
                token_callback=token_callback,
            )
            await queue.put(("done", result))
        except Exception as exc:
            logger.exception("stream_query error")
            await queue.put(("error", str(exc)))
        finally:
            await queue.put(_SENTINEL)

    yield f"event: stage\ndata: {json.dumps({'stage': 'classifying'})}\n\n"

    pipeline_task = asyncio.create_task(run())

    # After a short delay, emit the fetching stage (the pipeline spends the first
    # 1-2s on classification/rewrite before the LangGraph data fetch).
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
            elif kind == "done":
                yield f"event: done\ndata: {json.dumps({'result': payload.model_dump()})}\n\n"
                break
            elif kind == "error":
                yield f"event: error\ndata: {json.dumps({'detail': payload})}\n\n"
                break
    finally:
        pipeline_task.cancel()
        try:
            await pipeline_task
        except (asyncio.CancelledError, Exception):
            pass
