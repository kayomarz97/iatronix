"""Vector similarity search via pgvector.

Searches document_chunks using cosine similarity on HNSW index.
Uses the user's BYOK LLM key for embeddings — no server-side embedding key required.
Visibility: verified documents visible to all, unverified only to uploader.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select

from app.config import settings
from app.db.session import async_session as async_session_factory
from app.models.document import Document, DocumentChunk
from app.services.embedder import embed_query

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    chunk_id: int
    document_id: int
    content: str
    similarity: float
    source_type: str
    title: str
    publisher: Optional[str]
    page_number: Optional[int]
    pmid: Optional[str]
    pmcid: Optional[str]
    section: Optional[str] = None


async def search(
    query: str,
    user_id: Optional[int] = None,
    top_k: Optional[int] = None,
    source_type: Optional[str] = None,
    user_key: Optional[str] = None,
    user_provider: Optional[str] = None,
    voyage_api_key: Optional[str] = None,
) -> list[SearchResult]:
    """Embed query and search pgvector for similar document chunks.

    Requires the user's BYOK key — skips gracefully for Anthropic/unsupported providers.
    Visibility rules:
    - Verified documents: visible to all users
    - Unverified PDFs: visible only to the user who uploaded them
    """
    if not settings.vector_search_enabled:
        return []

    if not user_key or not user_provider:
        return []

    top_k = top_k or settings.vector_top_k

    # Fast path: skip DB round-trip entirely when no document chunks exist.
    async with async_session_factory() as session:
        from sqlalchemy import func
        count_result = await session.execute(select(func.count()).select_from(DocumentChunk))
        if count_result.scalar() == 0:
            return []

    query_embedding = await embed_query(query, user_provider, user_key, voyage_api_key=voyage_api_key)
    if query_embedding is None:
        return []

    async with async_session_factory() as session:
        distance = DocumentChunk.embedding.cosine_distance(query_embedding)

        stmt = (
            select(
                DocumentChunk,
                Document,
                (1 - distance).label("similarity"),
            )
            .join(Document, DocumentChunk.document_id == Document.id)
            .where(1 - distance >= settings.vector_min_similarity)
        )

        if user_id is not None:
            stmt = stmt.where(Document.uploaded_by_user_id == user_id)
        else:
            stmt = stmt.where(Document.uploaded_by_user_id == -1)

        if source_type:
            stmt = stmt.where(Document.source_type == source_type)

        stmt = stmt.order_by(distance).limit(top_k)

        result = await session.execute(stmt)
        rows = result.all()

        return [
            SearchResult(
                chunk_id=chunk.id,
                document_id=doc.id,
                content=chunk.content,
                similarity=float(sim),
                source_type=doc.source_type,
                title=doc.title,
                publisher=doc.publisher,
                page_number=chunk.page_number,
                pmid=doc.pmid,
                pmcid=doc.pmcid,
                section=(chunk.metadata_ or {}).get("section"),
            )
            for chunk, doc, sim in rows
        ]
