"""Data-retention: archive old rows to GCS, THEN delete them.

Safety contract: a row is NEVER deleted unless its archive upload succeeded.
If archiving is enabled but the upload fails, the rows are left in place and the
next daily cycle retries them — so nothing is ever lost to a transient GCS error.
Archiving to a Google Cloud Storage bucket (same project as Cloud Run) authenticates
via the attached service account (ADC) — no keys to manage.

Enabled via ``gcs_archive_enabled`` + ``gcs_archive_bucket``. If archiving is
disabled, rows older than the cutoff are deleted directly (legacy behaviour).
"""

from __future__ import annotations

import asyncio
import gzip
import io
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import delete as sa_delete
from sqlalchemy import select

from app.config import settings

logger = logging.getLogger(__name__)


def _serialize(rows, exclude: tuple[str, ...]) -> list[dict]:
    """Turn ORM rows into JSON-safe dicts, dropping excluded columns."""
    out: list[dict] = []
    for r in rows:
        d: dict = {}
        for col in r.__table__.columns.keys():
            if col in exclude:
                continue
            v = getattr(r, col)
            if isinstance(v, datetime):
                v = v.isoformat()
            d[col] = v
        out.append(d)
    return out


def _upload_blocking(kind: str, data: bytes) -> str:
    """Blocking GCS upload (runs in a thread). Returns the object name."""
    from google.cloud import storage

    client = storage.Client()  # ADC — attached service account on Cloud Run
    bucket = client.bucket(settings.gcs_archive_bucket)
    stamp = datetime.now(timezone.utc).strftime("%Y/%m/%d/%H%M%S")
    name = f"{kind}/{stamp}-{len(data)}b.jsonl.gz"
    bucket.blob(name).upload_from_string(data, content_type="application/gzip")
    return name


async def _archive(kind: str, payload: list[dict]) -> bool:
    """Gzip the rows as JSONL and upload to GCS. True only on confirmed success."""
    try:
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
            for row in payload:
                gz.write((json.dumps(row, default=str) + "\n").encode("utf-8"))
        name = await asyncio.to_thread(_upload_blocking, kind, buf.getvalue())
        logger.info(
            "retention[%s]: archived %d rows -> gs://%s/%s",
            kind, len(payload), settings.gcs_archive_bucket, name,
        )
        return True
    except Exception:
        logger.exception("retention[%s]: GCS archive failed", kind)
        return False


async def archive_and_purge(
    session_factory,
    model,
    time_col,
    cutoff: datetime,
    kind: str,
    exclude: tuple[str, ...] = (),
) -> int:
    """Archive rows older than ``cutoff`` to GCS, then delete them by id.

    Returns the number of rows deleted (0 if none, or if archiving was required
    but failed — in which case the rows are preserved for the next cycle).
    """
    async with session_factory() as session:
        rows = (await session.execute(select(model).where(time_col < cutoff))).scalars().all()
        if not rows:
            return 0

        if settings.gcs_archive_enabled and settings.gcs_archive_bucket:
            if not await _archive(kind, _serialize(rows, exclude)):
                logger.warning(
                    "retention[%s]: archive failed — %d rows kept, will retry next cycle",
                    kind, len(rows),
                )
                return 0
        # Delete exactly the rows we archived (by id), not a fresh time filter,
        # so rows that arrived mid-cycle are never deleted un-archived.
        ids = [r.id for r in rows]
        await session.execute(sa_delete(model).where(model.id.in_(ids)))
        await session.commit()
        return len(ids)
