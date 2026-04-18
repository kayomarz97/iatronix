"""Unified semantic retriever combining pgvector similarity search and PubMed full-text."""
import logging
from dataclasses import dataclass
from typing import Optional

from app.services.embedder import embedder
from app.services.vector_search import search as vector_search

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    text: str
    source: str
    score: float
    chunk_type: str  # "vector" or "pubmed"


async def retrieve(
    query: str,
    user_id: Optional[int] = None,
    top_k: int = 5,
    include_pubmed: bool = True,
) -> list[RetrievedChunk]:
    """Retrieve relevant chunks from all available sources.

    1. pgvector similarity search over user-uploaded document chunks.
    2. PubMed full-text abstracts fetched via data_fetcher (if include_pubmed=True).
    Deduplicates by text prefix and ranks by score descending.
    """
    chunks: list[RetrievedChunk] = []

    # --- pgvector ---
    try:
        vector_results = await vector_search(query, user_id=user_id, top_k=top_k)
        for vr in vector_results:
            chunks.append(RetrievedChunk(
                text=vr.get("text", ""),
                source=vr.get("source", "document"),
                score=float(vr.get("similarity", 0.0)),
                chunk_type="vector",
            ))
    except Exception:
        logger.warning("pgvector search failed", exc_info=True)

    # --- PubMed full-text ---
    if include_pubmed:
        try:
            from app.services.data_fetcher import fetch_data_for_query, FetchedData
            fetched: FetchedData = await fetch_data_for_query(query, query_type="general")
            if fetched and fetched.pubmed_abstracts:
                for abstract in fetched.pubmed_abstracts[:top_k]:
                    title = abstract.get("title", "")
                    text_body = abstract.get("abstract", "") or abstract.get("text", "")
                    combined = f"{title}\n{text_body}".strip()
                    if combined:
                        chunks.append(RetrievedChunk(
                            text=combined,
                            source=abstract.get("source", "PubMed"),
                            score=0.7,  # PubMed relevance treated as mid-tier
                            chunk_type="pubmed",
                        ))
        except Exception:
            logger.warning("PubMed retrieval failed", exc_info=True)

    # Deduplicate by first 100 chars of text
    seen: set[str] = set()
    deduped: list[RetrievedChunk] = []
    for c in chunks:
        key = c.text[:100]
        if key not in seen:
            seen.add(key)
            deduped.append(c)

    deduped.sort(key=lambda c: c.score, reverse=True)
    return deduped
