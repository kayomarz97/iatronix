"""Vector similarity search via pgvector.

Searches document_chunks using cosine similarity on HNSW index.
Visibility: verified documents visible to all, unverified only to uploader.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import or_, select

from app.config import settings
from app.db.session import async_session as async_session_factory
from app.models.document import Document, DocumentChunk
from app.services.embedder import Embedder

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
) -> list[SearchResult]:
    """Embed query and search pgvector for similar document chunks.

    Visibility rules:
    - Verified documents: visible to all users
    - Unverified PDFs: visible only to the user who uploaded them
    """
    if not settings.vector_search_enabled:
        return []

    top_k = top_k or settings.vector_top_k
    embedder = Embedder.get_instance()

    query_embedding = await asyncio.to_thread(embedder.embed_text, query)

    async with async_session_factory() as session:
        # Cosine distance: lower = more similar. Similarity = 1 - distance.
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

        # Visibility filter
        if user_id is not None:
            stmt = stmt.where(
                or_(
                    Document.verified == True,  # noqa: E712
                    Document.uploaded_by_user_id == user_id,
                )
            )
        else:
            stmt = stmt.where(Document.verified == True)  # noqa: E712

        # Optional source type filter
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
