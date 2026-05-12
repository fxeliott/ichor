"""pass3_addenda — Phase D W116 (ADR-087) post-mortem addendum store.

Stores short directional reminders that the W116 PBS evaluator decides
should be injected into the next Pass-3 prompt for a regime. Schema
details + rate-limit policy in `migrations/0044_pass3_addenda.py`.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Float, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Pass3Addendum(Base):
    """One Pass-3 prompt addendum scored by the W116 PBS evaluator."""

    __tablename__ = "pass3_addenda"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'expired', 'superseded', 'rejected')",
            name="ck_pass3_addenda_status",
        ),
        CheckConstraint(
            "importance >= 0.0",
            name="ck_pass3_addenda_importance_nonneg",
        ),
        CheckConstraint(
            "char_length(content) >= 8 AND char_length(content) <= 4096",
            name="ck_pass3_addenda_content_size",
        ),
        CheckConstraint(
            "expires_at > created_at",
            name="ck_pass3_addenda_expires_after_created",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    regime: Mapped[str] = mapped_column(String(64), nullable=False)
    asset: Mapped[str | None] = mapped_column(String(16), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    source_card_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    superseded_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
