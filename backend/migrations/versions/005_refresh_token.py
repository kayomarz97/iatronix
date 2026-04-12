"""005 — add refresh token to users table

Revision ID: 005
Revises: 004
Create Date: 2026-03-31
"""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("refresh_token_hash", sa.String(255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "refresh_token_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_users_refresh_token_hash", "users", ["refresh_token_hash"]
    )


def downgrade() -> None:
    op.drop_index("ix_users_refresh_token_hash", table_name="users")
    op.drop_column("users", "refresh_token_expires_at")
    op.drop_column("users", "refresh_token_hash")
