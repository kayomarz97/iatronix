import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class UserRole(str, enum.Enum):
    admin = "admin"
    user = "user"
    readonly = "readonly"


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    key_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole), default=UserRole.user, nullable=False
    )
    scopes: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # BYOK: user's own LLM API key (encrypted at rest)
    encrypted_llm_key: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )
    llm_provider: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )  # 'anthropic' or 'openai'

    # Login auth
    password_hash: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )

    __table_args__ = (Index("ix_users_key_id", "key_id", unique=True),)
