"""
QueryCache — stores LLM response embeddings for semantic similarity lookup.

Each entry holds a query's embedding vector so future queries can find
semantically equivalent cached responses (cosine similarity >= threshold)
without re-running the full pipeline.
"""

from datetime import datetime
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.models.base import CacheBase


class QueryCache(CacheBase):
    __tablename__ = "query_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    query_type: Mapped[str] = mapped_column(String(32), nullable=False)
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    query_embedding: Mapped[Optional[object]] = mapped_column(
        Vector(settings.embedding_dim), nullable=True
    )
    response_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=True
    )

    __table_args__ = (
        # HNSW index for fast approximate nearest-neighbour on cosine distance
        Index(
            "ix_query_cache_embedding_hnsw",
            "query_embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"query_embedding": "vector_cosine_ops"},
        ),
        Index("ix_query_cache_query_type", "query_type"),
    )
