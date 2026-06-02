"""Durable, resumable streaming jobs (RESUMABLE_STREAM_ENABLED).

Problem this solves
-------------------
The legacy SSE path ties the query computation to the HTTP connection: when a
mobile browser backgrounds the tab (tab switch / screen off) the connection is
torn down, FastAPI closes the generator, and the pipeline task is cancelled —
the answer is lost and there is nothing to resume.

Design
------
* ``start_job`` launches ``iter_query_events`` inside a **detached** asyncio task
  (kept in a module-level set so it is neither GC'd nor cancelled when the
  request connection closes). Every event is appended to a **Redis Stream**
  ``job:{id}`` (XADD) — the single source of truth.
* ``tail_job`` is a pure reader: it XREADs the stream from a cursor (``"0"`` for a
  fresh attach, or the client's ``Last-Event-ID`` on resume), blocking for new
  entries, until it sees the terminal ``done``/``error`` event.

Why a Redis Stream: native blocking tail (``XREAD BLOCK``), native resumable
cursor (the entry id == our SSE ``id:``), bounded memory (``MAXLEN``), and it
works across all Gunicorn workers — a reconnect that lands on a different worker
tails the same stream. The producer task lives on the worker that received the
initial POST; if that worker is recycled mid-flight the job ends (the documented
upgrade path for full durability is an external task worker, e.g. ARQ/Celery —
not required to fix the reported client-disconnect bug).
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, AsyncIterator

import orjson

from app.config import settings
from app.services.rag_pipeline_stream import iter_query_events

logger = logging.getLogger(__name__)

# Strong refs to detached producer tasks so they survive request completion and
# are not garbage-collected mid-flight.
_RUNNING: set[asyncio.Task] = set()

_STREAM_MAXLEN = 10000  # safety bound on entries per job (token streams are the only high-volume case)


def _skey(job_id: str) -> str:
    return f"job:{job_id}"


async def _persist(redis, job_id: str, kind: str, payload: Any) -> None:
    """Append one event to the job's Redis stream."""
    if kind == "done":
        # payload is a QueryResponse model — serialize to the same shape the client expects.
        data = {"result": payload.model_dump()}
    else:
        data = payload
    await redis.xadd(
        _skey(job_id),
        {"event": kind, "data": orjson.dumps(data).decode()},
        maxlen=_STREAM_MAXLEN,
        approximate=True,
    )


async def _run_producer(job_id: str, request, redis, user_key_id, user) -> None:
    """Detached task: drive the pipeline to completion, persisting every event."""
    emitted_terminal = False

    async def _drive() -> None:
        nonlocal emitted_terminal
        async for kind, payload in iter_query_events(
            request, redis_client=redis, user_key_id=user_key_id, user=user
        ):
            await _persist(redis, job_id, kind, payload)
            if kind in ("done", "error"):
                emitted_terminal = True

    try:
        await asyncio.wait_for(_drive(), timeout=settings.stream_job_max_runtime_seconds)
    except asyncio.TimeoutError:
        logger.warning("stream job %s exceeded max runtime", job_id)
        if not emitted_terminal:
            await _persist(
                redis, job_id, "error",
                {"detail": "Request timed out. Try a simpler query or a different model.",
                 "error_type": "timeout"},
            )
    except Exception:  # noqa: BLE001
        logger.exception("stream job %s producer error", job_id)
        if not emitted_terminal:
            try:
                await _persist(
                    redis, job_id, "error",
                    {"detail": "Internal server error", "error_type": "pipeline_error"},
                )
            except Exception:  # noqa: BLE001
                pass
    finally:
        # Keep the finished stream replayable for late reconnects, then let it expire.
        try:
            await redis.expire(_skey(job_id), settings.stream_job_ttl_seconds)
        except Exception:  # noqa: BLE001
            pass


async def start_job(request, redis, user_key_id=None, user=None) -> str:
    """Create a job, launch its detached producer, and return the job id."""
    job_id = uuid.uuid4().hex
    task = asyncio.create_task(_run_producer(job_id, request, redis, user_key_id, user))
    _RUNNING.add(task)
    task.add_done_callback(_RUNNING.discard)
    logger.info("stream job %s started (detached producer)", job_id)
    return job_id


def _sse(event_id: str, kind: str, data: Any) -> str:
    """Format an SSE block. ``id:`` carries the resumable cursor (Redis stream entry id)."""
    return f"id: {event_id}\nevent: {kind}\ndata: {orjson.dumps(data).decode()}\n\n"


def _normalize_xread(resp: Any) -> list[tuple[str, dict]]:
    """Flatten an XREAD response into [(entry_id, fields), ...] (decode_responses=True)."""
    out: list[tuple[str, dict]] = []
    if not resp:
        return out
    for _stream_name, entries in resp:
        for entry_id, fields in entries:
            out.append((entry_id, fields))
    return out


async def tail_job(redis, job_id: str, last_id: str = "0") -> AsyncIterator[str]:
    """Yield SSE strings for a job from ``last_id``, blocking until the terminal event.

    last_id="0"  → fresh attach (replay everything, then live-tail).
    last_id=<id> → resume (replay only events after the client's last-seen id).
    """
    skey = _skey(job_id)
    cursor = last_id or "0"

    # Unknown/expired job on a fresh attach → tell the client to search again.
    if cursor == "0" and not await redis.exists(skey):
        yield _sse("0", "error",
                   {"detail": "This search session expired. Please search again.",
                    "error_type": "expired"})
        return

    block_ms = 1000
    idle_ms = 0
    idle_cap_ms = max(1, settings.stream_job_idle_grace_seconds) * 1000

    while True:
        try:
            resp = await redis.xread({skey: cursor}, count=200, block=block_ms)
        except Exception:  # noqa: BLE001 — transient Redis hiccup; brief pause then retry
            await asyncio.sleep(0.25)
            continue

        entries = _normalize_xread(resp)
        if entries:
            idle_ms = 0
            for entry_id, fields in entries:
                cursor = entry_id
                kind = fields.get("event", "")
                try:
                    data = orjson.loads(fields.get("data", "{}"))
                except Exception:  # noqa: BLE001
                    data = {}
                yield _sse(entry_id, kind, data)
                if kind in ("done", "error"):
                    return
            continue

        # Empty read. Decide whether to keep waiting or stop.
        if not await redis.exists(skey):
            # Stream vanished (TTL expired) before we saw a terminal event.
            yield _sse(cursor, "error",
                       {"detail": "This search session expired. Please search again.",
                        "error_type": "expired"})
            return

        # If the job already finished and we're caught up to its last entry, stop cleanly.
        try:
            tail = await redis.xrevrange(skey, count=1)
        except Exception:  # noqa: BLE001
            tail = None
        if tail:
            last_entry_id, last_fields = tail[0]
            if last_fields.get("event") in ("done", "error") and cursor == last_entry_id:
                return

        idle_ms += block_ms
        # Never received a single event within the grace window → producer is dead/gone.
        if cursor == (last_id or "0") and idle_ms >= idle_cap_ms:
            yield _sse(cursor, "error",
                       {"detail": "No response received. Please search again.",
                        "error_type": "timeout"})
            return
