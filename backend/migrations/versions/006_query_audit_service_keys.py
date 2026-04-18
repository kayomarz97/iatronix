"""Add query_audit and service_keys tables

Revision ID: 006
Revises: e325edba0af9
Create Date: 2026-04-17

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006"
down_revision: Union[str, None] = "e325edba0af9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "query_audit",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("query", sa.String(), nullable=False),
        sa.Column("retrieved_passages", postgresql.JSONB(), nullable=True),
        sa.Column("llm_output", postgresql.JSONB(), nullable=True),
        sa.Column("verification_passed", sa.Boolean(), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_query_audit_user_id", "query_audit", ["user_id"])
    op.create_index("ix_query_audit_timestamp", "query_audit", ["timestamp"])

    op.create_table(
        "service_keys",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("service_name", sa.String(50), nullable=False),
        sa.Column("encrypted_key", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_service_keys_user_id", "service_keys", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_service_keys_user_id", table_name="service_keys")
    op.drop_table("service_keys")
    op.drop_index("ix_query_audit_timestamp", table_name="query_audit")
    op.drop_index("ix_query_audit_user_id", table_name="query_audit")
    op.drop_table("query_audit")
