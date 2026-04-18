"""Add openai_api_key, gemini_api_key, anthropic_api_key to users

Revision ID: 007
Revises: 006
Create Date: 2026-04-17
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("openai_api_key", sa.String(), nullable=True))
    op.add_column("users", sa.Column("gemini_api_key", sa.String(), nullable=True))
    op.add_column("users", sa.Column("anthropic_api_key", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "anthropic_api_key")
    op.drop_column("users", "gemini_api_key")
    op.drop_column("users", "openai_api_key")
