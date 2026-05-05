"""post_mortems table — weekly Claude Opus 4.7 post-mortems (8-section template).

Mirrors the schema created in migration 0010. The actual markdown is on disk
under `docs/post_mortem/{YYYY-Www}.md`; this row indexes the structured-data
sections (top hits, top miss, drift, narratives, calibration, suggestions,
stats) for fast querying.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PostMortem(Base):
    __tablename__ = "post_mortems"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    iso_year: Mapped[int] = mapped_column(Integer, nullable=False)
    iso_week: Mapped[int] = mapped_column(Integer, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    markdown_path: Mapped[str] = mapped_column(Text, nullable=False)

    top_hits: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    top_miss: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    drift_detected: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    narratives: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    calibration: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    suggestions: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    stats: Mapped[Any | None] = mapped_column(JSONB, nullable=True)

    actionable_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actionable_count_resolved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
