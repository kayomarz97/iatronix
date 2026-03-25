"""004 — semantic query cache table

Revision ID: 004
Revises: 003
Create Date: 2026-03-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None

EMBEDDING_DIM = 384


def upgrade() -> None:
    op.create_table(
        "query_cache",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("query_text", sa.Text, nullable=False),
        sa.Column("query_type", sa.String(32), nullable=False),
        sa.Column("model_id", sa.String(128), nullable=False),
        sa.Column("query_embedding", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column("response_json", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_verified_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
    )

    # HNSW index for cosine similarity search
    op.execute(
        f"""
        CREATE INDEX ix_query_cache_embedding_hnsw
        ON query_cache
        USING hnsw (query_embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )
    op.create_index("ix_query_cache_query_type", "query_cache", ["query_type"])


def downgrade() -> None:
    op.drop_index("ix_query_cache_query_type", table_name="query_cache")
    op.drop_index("ix_query_cache_embedding_hnsw", table_name="query_cache")
    op.drop_table("query_cache")
