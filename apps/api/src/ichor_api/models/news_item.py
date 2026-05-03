"""news_items table — stores RSS-collected headlines for context assembly."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ARRAY, DateTime, Float, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class NewsItem(Base):
    """One headline pulled from a public RSS/Atom feed.

    Composite PK (id, fetched_at) is required by TimescaleDB hypertable
    partitioning on `fetched_at`.
    """

    __tablename__ = "news_items"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    guid_hash: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    raw_categories: Mapped[list[str] | None] = mapped_column(ARRAY(String(64)))

    # NLP enrichment, populated asynchronously by FinBERT-tone worker
    tone_label: Mapped[str | None] = mapped_column(String(16))
    tone_score: Mapped[float | None] = mapped_column(Float)
