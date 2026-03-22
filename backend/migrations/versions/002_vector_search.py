"""Vector search: 384-dim chunks, PDF verification, BYOK user fields

Revision ID: 002
Revises: 001
Create Date: 2026-03-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Rework documents table ---
    # Drop old embedding column (was Vector(1536), never used in production)
    op.drop_column("documents", "embedding")
    op.drop_column("documents", "content")
    op.drop_column("documents", "source")

    # Add new columns
    op.add_column(
        "documents",
        sa.Column("source_type", sa.String(20), nullable=False, server_default="pdf"),
    )
    op.add_column(
        "documents", sa.Column("file_name", sa.String(512), nullable=True)
    )
    op.add_column(
        "documents", sa.Column("pdf_size_bytes", sa.Integer(), nullable=True)
    )
    op.add_column(
        "documents", sa.Column("page_count", sa.Integer(), nullable=True)
    )
    op.add_column(
        "documents", sa.Column("pmid", sa.String(20), nullable=True)
    )
    op.add_column(
        "documents", sa.Column("pmcid", sa.String(20), nullable=True)
    )
    op.add_column(
        "documents",
        sa.Column("uploaded_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("verified", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "documents", sa.Column("publisher", sa.String(255), nullable=True)
    )

    # Unique partial indexes for deduplication
    op.create_index(
        "ix_documents_pmid",
        "documents",
        ["pmid"],
        unique=True,
        postgresql_where=sa.text("pmid IS NOT NULL"),
    )
    op.create_index(
        "ix_documents_pmcid",
        "documents",
        ["pmcid"],
        unique=True,
        postgresql_where=sa.text("pmcid IS NOT NULL"),
    )

    # --- Create document_chunks table ---
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Integer(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("embedding", Vector(384), nullable=True),
        sa.Column("metadata_", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_chunks_document_id", "document_chunks", ["document_id"])

    # HNSW index for cosine similarity search
    op.execute(
        "CREATE INDEX ix_chunks_embedding ON document_chunks "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )

    # --- Add BYOK fields to users ---
    op.add_column(
        "users", sa.Column("encrypted_llm_key", sa.Text(), nullable=True)
    )
    op.add_column(
        "users", sa.Column("llm_provider", sa.String(20), nullable=True)
    )
    op.add_column(
        "users", sa.Column("password_hash", sa.String(255), nullable=True)
    )


def downgrade() -> None:
    # Users
    op.drop_column("users", "password_hash")
    op.drop_column("users", "llm_provider")
    op.drop_column("users", "encrypted_llm_key")

    # Document chunks
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding")
    op.drop_table("document_chunks")

    # Documents - restore original columns
    op.drop_index("ix_documents_pmcid", "documents")
    op.drop_index("ix_documents_pmid", "documents")
    op.drop_column("documents", "publisher")
    op.drop_column("documents", "verified")
    op.drop_column("documents", "uploaded_by_user_id")
    op.drop_column("documents", "pmcid")
    op.drop_column("documents", "pmid")
    op.drop_column("documents", "page_count")
    op.drop_column("documents", "pdf_size_bytes")
    op.drop_column("documents", "file_name")
    op.drop_column("documents", "source_type")
    op.add_column("documents", sa.Column("source", sa.String(255), nullable=True))
    op.add_column("documents", sa.Column("content", sa.Text(), nullable=False, server_default=""))
    op.add_column("documents", sa.Column("embedding", Vector(1536), nullable=True))
