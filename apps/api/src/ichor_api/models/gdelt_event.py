"""gdelt_events table — translingual news from GDELT 2.0 Doc API."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class GdeltEvent(Base):
    """One article surfaced by a GDELT 2.0 Doc API query.

    Composite PK (id, seendate) for TimescaleDB hypertable on `seendate`.
    Unique on (url, query_label) so the same URL can be tagged by several
    keyword buckets without colliding.
    """

    __tablename__ = "gdelt_events"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    seendate: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    query_label: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(128), index=True)
    language: Mapped[str | None] = mapped_column(String(32))
    sourcecountry: Mapped[str | None] = mapped_column(String(32))
    tone: Mapped[float] = mapped_column(Float, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(1024))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
