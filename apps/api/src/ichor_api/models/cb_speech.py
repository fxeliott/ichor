"""cb_speeches table — central bank speeches (BIS aggregator + per-CB feeds)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class CbSpeech(Base):
    """One central bank speech surfaced via BIS or a per-CB RSS feed.

    Composite PK (id, published_at) for TimescaleDB hypertable.
    Unique on `url` (a single speech is published once).
    """

    __tablename__ = "cb_speeches"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    central_bank: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    speaker: Mapped[str | None] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_feed: Mapped[str] = mapped_column(String(64), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
