"""Cloudflare R2 storage (S3-compatible API via boto3)."""

import asyncio
import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

_s3_client = None


def _get_client():
    global _s3_client
    if _s3_client is not None:
        return _s3_client
    if not all(
        [
            settings.r2_account_id,
            settings.r2_access_key_id,
            settings.r2_secret_access_key,
        ]
    ):
        return None
    try:
        import boto3
        from botocore.config import Config

        _s3_client = boto3.client(
            "s3",
            endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            config=Config(region_name="auto", retries={"max_attempts": 2}),
        )
    except ImportError:
        logger.warning(
            "boto3 not installed — R2 storage unavailable. Run: pip install boto3"
        )
        return None
    return _s3_client


def _r2_configured() -> bool:
    return bool(settings.r2_account_id and settings.r2_access_key_id)


def _upload_sync(
    file_bytes: bytes,
    key: str,
    content_type: str = "application/pdf",
    metadata: dict = None,
) -> str:
    client = _get_client()
    if not client:
        raise RuntimeError(
            "Cloudflare R2 not configured. "
            "Set R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY in .env"
        )
    extra: dict = {"ContentType": content_type}
    if metadata:
        extra["Metadata"] = {k: str(v) for k, v in metadata.items()}
    client.put_object(Bucket=settings.r2_bucket_name, Key=key, Body=file_bytes, **extra)
    if settings.r2_public_url:
        return f"{settings.r2_public_url.rstrip('/')}/{key}"
    return f"r2://{settings.r2_bucket_name}/{key}"


def _delete_sync(key: str) -> bool:
    client = _get_client()
    if not client:
        return False
    try:
        client.delete_object(Bucket=settings.r2_bucket_name, Key=key)
        return True
    except Exception as e:
        logger.error(f"R2 delete failed for key={key}: {e}")
        return False


def is_configured() -> bool:
    return _r2_configured()


async def upload_pdf(
    file_bytes: bytes, file_key: str, metadata: Optional[dict] = None
) -> str:
    """Upload PDF to R2. Returns public URL. Raises RuntimeError if not configured."""
    return await asyncio.to_thread(
        _upload_sync, file_bytes, file_key, "application/pdf", metadata or {}
    )


async def delete_pdf(file_key: str) -> bool:
    """Delete a PDF from R2. Returns True on success."""
    return await asyncio.to_thread(_delete_sync, file_key)
