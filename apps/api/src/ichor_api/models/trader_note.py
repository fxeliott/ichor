"""trader_notes table — Eliot's private journal (Phase B.5d v2).

Created by migration 0029. Out of ADR-017 boundary surface.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class TraderNote(Base):
    """One trader journal entry.

    `asset` is nullable because some notes are pure macro reflections,
    not tied to a specific instrument.

    `body` is plain text or markdown — the API never renders it server-
    side; the web client is responsible for safe rendering.
    """

    __tablename__ = "trader_notes"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    asset: Mapped[str | None] = mapped_column(String(16), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
