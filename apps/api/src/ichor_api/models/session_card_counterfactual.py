"""session_card_counterfactuals table — persisted Pass 5 results.

Created by migration 0022. Sibling of session_card_audit, keyed by
(session_card_id, asked_at) so a single card can be probed multiple
times with different scrubbed_event scenarios.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SessionCardCounterfactual(Base):
    """One Pass 5 counterfactual result tied to a session card.

    Composite PK (id, asked_at) — composite required for any future
    TimescaleDB hypertable on asked_at (not yet but the shape is
    forward-compatible).
    """

    __tablename__ = "session_card_counterfactuals"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    asked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    session_card_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, index=True
    )
    asset: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    scrubbed_event: Mapped[str] = mapped_column(String(500), nullable=False)

    original_bias: Mapped[str] = mapped_column(String(8), nullable=False)
    original_conviction_pct: Mapped[float] = mapped_column(Float, nullable=False)

    counterfactual_bias: Mapped[str] = mapped_column(String(8), nullable=False)
    counterfactual_conviction_pct: Mapped[float] = mapped_column(Float, nullable=False)
    delta_narrative: Mapped[str | None] = mapped_column(Text)
    new_dominant_drivers: Mapped[Any | None] = mapped_column(JSONB)
    confidence_delta: Mapped[float] = mapped_column(Float, nullable=False)

    robustness_score: Mapped[float | None] = mapped_column(Float)
    """Higher = the original verdict was robust to the scrubbed event.
    Computed as 1 - abs(confidence_delta) clamped to [0, 1]."""

    model_used: Mapped[str | None] = mapped_column(String(64))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
