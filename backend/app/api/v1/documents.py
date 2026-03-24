"""Document upload, listing, and deletion endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_session as get_async_session
from app.models.document import Document

router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger(__name__)


class DocumentResponse(BaseModel):
    id: int
    title: str
    source_type: str
    file_name: Optional[str] = None
    page_count: Optional[int] = None
    verified: bool
    publisher: Optional[str] = None
    chunk_count: int = 0
    created_at: str
    expires_at: Optional[str] = None
    is_approved: bool = False
    notice: Optional[str] = None

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]
    total: int
    verified_count: int


class DeleteResponse(BaseModel):
    message: str


def _get_user(request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(401, "Authentication required")
    return user


@router.post("/upload", response_model=DocumentResponse)
async def upload_pdf(
    request: Request,
    file: UploadFile = File(...),
):
    """Upload a PDF document. Auto-verifies against known publishers."""
    user = _get_user(request)

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted")

    if file.size and file.size > settings.max_pdf_size_bytes:
        max_mb = settings.max_pdf_size_bytes // (1024 * 1024)
        raise HTTPException(400, f"File too large. Maximum size is {max_mb}MB")

    file_bytes = await file.read()
    if len(file_bytes) > settings.max_pdf_size_bytes:
        max_mb = settings.max_pdf_size_bytes // (1024 * 1024)
        raise HTTPException(400, f"File too large. Maximum size is {max_mb}MB")

    from app.services.ingestion import ingest_pdf

    try:
        doc = await ingest_pdf(
            file_name=file.filename,
            file_bytes=file_bytes,
            user_id=user.id,
        )
    except Exception as e:
        logger.error("PDF ingestion failed: %s", e)
        raise HTTPException(500, "Failed to process PDF")

    notice = (
        "This is an approved document and will be shared to improve the shared medical database."
        if doc.verified
        else f"This document will be deleted in {settings.pdf_non_approved_ttl_hours} hours."
    )
    return DocumentResponse(
        id=doc.id,
        title=doc.title,
        source_type=doc.source_type,
        file_name=doc.file_name,
        page_count=doc.page_count,
        verified=doc.verified,
        publisher=doc.publisher,
        chunk_count=getattr(doc, "_chunk_count", 0),
        created_at=doc.created_at.isoformat(),
        expires_at=doc.expires_at.isoformat() if doc.expires_at else None,
        is_approved=doc.verified,
        notice=notice,
    )


@router.post("/estimate-cost")
async def estimate_upload_cost(file: UploadFile = File(...)):
    """Returns cost/scope estimate for a PDF without storing it.
    Call this BEFORE the actual upload to show the user what will happen.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    file_bytes = await file.read()
    if len(file_bytes) > settings.max_pdf_size_bytes:
        max_mb = settings.max_pdf_size_bytes // (1024 * 1024)
        raise HTTPException(
            status_code=413, detail=f"File too large. Max size: {max_mb}MB"
        )

    from app.services.ingestion import get_pdf_text_preview
    from app.services.cost_estimator import estimate_pdf_ingestion

    text, page_count = await get_pdf_text_preview(file_bytes)
    estimate = estimate_pdf_ingestion(text)
    estimate["page_count"] = page_count
    estimate["file_size_bytes"] = len(file_bytes)
    estimate["expires_in_hours"] = settings.pdf_non_approved_ttl_hours
    estimate["expires_note"] = (
        f"Non-approved documents are automatically deleted after "
        f"{settings.pdf_non_approved_ttl_hours} hours. "
        "Verified medical publications are kept permanently and shared to improve the database."
    )
    return estimate


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    """List user's uploaded documents and verified document count."""
    user = _get_user(request)

    # User's own documents
    result = await session.execute(
        select(Document)
        .where(Document.uploaded_by_user_id == user.id)
        .order_by(Document.created_at.desc())
    )
    docs = result.scalars().all()

    # Count of all verified documents
    verified_result = await session.execute(
        select(func.count()).select_from(Document).where(Document.verified.is_(True))
    )
    verified_count = verified_result.scalar() or 0

    return DocumentListResponse(
        documents=[
            DocumentResponse(
                id=d.id,
                title=d.title,
                source_type=d.source_type,
                file_name=d.file_name,
                page_count=d.page_count,
                verified=d.verified,
                publisher=d.publisher,
                chunk_count=0,
                created_at=d.created_at.isoformat(),
            )
            for d in docs
        ],
        total=len(docs),
        verified_count=verified_count,
    )


@router.delete("/{doc_id}", response_model=DeleteResponse)
async def delete_document(
    doc_id: int,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    """Delete a document. Only the uploader can delete their documents."""
    user = _get_user(request)

    result = await session.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(404, "Document not found")

    if doc.uploaded_by_user_id != user.id:
        raise HTTPException(403, "You can only delete your own documents")

    await session.delete(doc)
    await session.commit()

    return DeleteResponse(message="Document deleted")
