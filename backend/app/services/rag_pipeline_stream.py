"""SSE streaming wrapper around process_query.

`iter_query_events()` is the single source of truth for the event sequence a query
produces. It yields ``(kind, payload)`` tuples:

  ("stage",            {"stage": "classifying"|"fetching"|"generating"})
  ("token",            {"text": "..."})
  ("bluf",             {...})
  ("fetch_articles",   {"titles": [...]})
  ("section_complete", {...})
  ("model_info",       {...})
  ("done",             QueryResponse)          # model, not yet serialized
  ("error",            {"detail": "...", "error_type": "..."})

Two consumers share it:
  * ``stream_query`` — legacy connection-coupled path: formats tuples into SSE
    strings and is cancelled with the request when the client disconnects
    (unchanged behaviour, used when RESUMABLE_STREAM_ENABLED is false).
  * ``app.services.stream_jobs`` — durable path: persists every tuple to a Redis
    stream from a detached background task, so the query survives a client
    disconnect (mobile tab switch / screen off) and can be resumed on reconnect.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator

from app.services.rag_pipeline import process_query

logger = logging.getLogger(__name__)

_SENTINEL = object()


async def iter_query_events(
    request,
    redis_client=None,
    user_key_id: str | None = None,
    user=None,
) -> AsyncIterator[tuple[str, Any]]:
    """Run process_query and yield ``(kind, payload)`` events in order.

    Cancellation semantics are owned by the *caller*. When the legacy formatter
    consumes this and the client disconnects, closing this generator cancels the
    in-flight pipeline (back-compatible). When the durable job runner consumes it
    detached from any request, the pipeline runs to completion regardless.
    """
    queue: asyncio.Queue = asyncio.Queue()

    async def token_callback(text: str) -> None:
        await queue.put(("token", {"text": text}))

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
        except Exception as exc:  # noqa: BLE001 — surfaced as an SSE error event
            logger.exception("iter_query_events pipeline error")
            err_str = str(exc)
            is_rate_limit = (
                "429" in err_str
                or "rate_limit" in err_str.lower()
                or "overloaded" in err_str.lower()
            )
            err_payload = {
                "detail": "Service temporarily busy. Your partial results are preserved."
                if is_rate_limit
                else err_str,
                "error_type": "rate_limit" if is_rate_limit else "pipeline_error",
            }
            await queue.put(("error", err_payload))
        finally:
            await queue.put(_SENTINEL)

    yield ("stage", {"stage": "classifying"})

    pipeline_task = asyncio.create_task(run())

    async def _emit_fetching() -> None:
        await asyncio.sleep(1.2)
        await queue.put(("stage", {"stage": "fetching"}))

    fetching_task = asyncio.create_task(_emit_fetching())

    try:
        while True:
            item = await queue.get()
            if item is _SENTINEL:
                break
            kind, payload = item
            yield (kind, payload)
            if kind in ("done", "error"):
                break
    finally:
        # Cancelling an already-finished task is a harmless no-op; this only has an
        # effect when the *consumer* stops early (legacy path: client disconnected).
        pipeline_task.cancel()
        fetching_task.cancel()
        try:
            await asyncio.gather(pipeline_task, fetching_task, return_exceptions=True)
        except Exception:  # noqa: BLE001
            pass


def format_sse(kind: str, payload: Any) -> str:
    """Format one ``(kind, payload)`` event as an SSE block (no id line)."""
    if kind == "done":
        data = {"result": payload.model_dump()}
    else:
        data = payload
    return f"event: {kind}\ndata: {json.dumps(data)}\n\n"


async def stream_query(
    request,
    redis_client=None,
    user_key_id: str | None = None,
    user=None,
):
    """Legacy SSE generator — formats events as strings, coupled to the request.

    Used when RESUMABLE_STREAM_ENABLED is false. Behaviour is identical to the
    pre-refactor implementation: if the client disconnects, this generator is
    closed and the underlying pipeline task is cancelled.
    """
    async for kind, payload in iter_query_events(
        request, redis_client=redis_client, user_key_id=user_key_id, user=user
    ):
        yield format_sse(kind, payload)
