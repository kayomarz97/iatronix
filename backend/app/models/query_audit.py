import datetime
from typing import Optional

from sqlalchemy import String, Integer, Boolean, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

class QueryAudit(Base):
    __tablename__ = "query_audit"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    query: Mapped[str] = mapped_column(String, nullable=False)
    retrieved_passages: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    llm_output: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    verification_passed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc), index=True)
