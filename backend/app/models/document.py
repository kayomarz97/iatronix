from datetime import datetime
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import settings
from app.models.base import Base, TimestampMixin


class Document(TimestampMixin, Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pdf"
    )  # pdf, pmc, statpearls, pubmed
    file_name: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    pdf_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    page_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pmid: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    pmcid: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    uploaded_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    verified: Mapped[bool] = mapped_column(
        Boolean, server_default="false", nullable=False
    )
    publisher: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)

    # Cloudflare R2 storage
    r2_key: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    r2_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Auto-deletion: non-approved docs expire after N hours
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index(
            "ix_documents_pmid",
            "pmid",
            unique=True,
            postgresql_where="pmid IS NOT NULL",
        ),
        Index(
            "ix_documents_pmcid",
            "pmcid",
            unique=True,
            postgresql_where="pmcid IS NOT NULL",
        ),
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    embedding: Mapped[Optional[list]] = mapped_column(
        Vector(settings.embedding_dim), nullable=True
    )
    metadata_: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped["Document"] = relationship(back_populates="chunks")
