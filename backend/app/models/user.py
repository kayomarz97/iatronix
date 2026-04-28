import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class UserRole(str, enum.Enum):
    admin = "admin"
    user = "user"
    readonly = "readonly"


class UserPosition(str, enum.Enum):
    medical_student = "medical_student"
    intern = "intern"
    junior_resident = "junior_resident"
    senior_resident = "senior_resident"
    fellow = "fellow"
    consultant = "consultant"
    researcher = "researcher"
    nursing_staff = "nursing_staff"
    pharmacist = "pharmacist"
    allied_health = "allied_health"
    other = "other"


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    firebase_uid: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole), default=UserRole.user, nullable=False
    )
    scopes: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # BYOK: user's own LLM API key (Fernet-encrypted at rest)
    encrypted_llm_key: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    llm_provider: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # Specific API keys (per-provider, independent)
    openai_api_key: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    gemini_api_key: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    anthropic_api_key: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    openrouter_key: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    cerebras_api_key: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Profile (for personalisation and future monetisation analytics)
    username: Mapped[Optional[str]] = mapped_column(
        String(50), unique=True, nullable=True
    )
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    position: Mapped[Optional[str]] = mapped_column(
        String(30), nullable=True
    )  # UserPosition enum values
    institute: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    specialty: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    institution_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    age: Mapped[Optional[int]] = mapped_column(nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Subscription tier (free/premium/enterprise) — for future paywall
    tier: Mapped[str] = mapped_column(String(20), default="free", nullable=False)
    subscription_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # User preferences: answer style, preferred sources, dark mode, etc. (JSONB for flexibility)
    preferences: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Refresh token (hashed) for token rotation
    refresh_token_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    refresh_token_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Analytics / monetisation metadata
    newsletter_consent: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    last_login: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_users_firebase_uid", "firebase_uid", unique=True),
        Index("ix_users_email", "email"),
        Index("ix_users_username", "username"),
    )