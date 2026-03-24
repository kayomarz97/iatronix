"""User profile expansion, R2 storage fields, search history table.

Revision ID: 003
Revises: 002
Create Date: 2026-03-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Expand users table ──────────────────────────────────────────────────
    op.add_column("users", sa.Column("username", sa.String(50), nullable=True))
    op.add_column("users", sa.Column("full_name", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("country", sa.String(100), nullable=True))
    op.add_column("users", sa.Column("position", sa.String(30), nullable=True))
    op.add_column("users", sa.Column("institute", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("specialty", sa.String(100), nullable=True))
    op.add_column("users", sa.Column("institution_type", sa.String(50), nullable=True))
    op.add_column(
        "users",
        sa.Column("tier", sa.String(20), nullable=False, server_default="free"),
    )
    op.add_column(
        "users",
        sa.Column("subscription_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "preferences",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "newsletter_consent",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "users",
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_email", "users", ["email"])

    # ── Add R2 storage fields to documents ──────────────────────────────────
    op.add_column("documents", sa.Column("r2_key", sa.String(500), nullable=True))
    op.add_column("documents", sa.Column("r2_url", sa.String(1000), nullable=True))
    op.add_column(
        "documents",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── Create search_history table ─────────────────────────────────────────
    op.create_table(
        "search_history",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("query_type", sa.String(30), nullable=True),
        sa.Column("response_summary", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_search_history_user_id", "search_history", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_search_history_user_id", table_name="search_history")
    op.drop_table("search_history")

    op.drop_column("documents", "expires_at")
    op.drop_column("documents", "r2_url")
    op.drop_column("documents", "r2_key")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    for col in [
        "last_login",
        "newsletter_consent",
        "preferences",
        "subscription_expires_at",
        "tier",
        "institution_type",
        "specialty",
        "institute",
        "position",
        "country",
        "full_name",
        "username",
    ]:
        op.drop_column("users", col)
