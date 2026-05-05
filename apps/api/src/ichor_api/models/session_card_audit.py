"""session_card_audit table — Claude-generated session verdicts with provenance.

Replaces the historical `predictions_audit` purpose, but kept distinct
so old data survives. Stores the full session-card output of the Claude
4-pass pipeline together with the inputs hash (for cache key + repro)
and any later realized-outcome columns used for Brier-score calibration
tracking per asset / session / regime.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SessionCardAudit(Base):
    """One Claude-generated session card verdict.

    Composite PK (id, generated_at) for TimescaleDB hypertable on
    `generated_at`. CHECK constraints on bias_direction, conviction_pct
    and session_type are enforced at the DB level (see migration 0005).
    """

    __tablename__ = "session_card_audit"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    session_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    asset: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    model_id: Mapped[str] = mapped_column(String(64), nullable=False)
    regime_quadrant: Mapped[str | None] = mapped_column(String(32))

    bias_direction: Mapped[str] = mapped_column(String(8), nullable=False)
    conviction_pct: Mapped[float] = mapped_column(Float, nullable=False)
    magnitude_pips_low: Mapped[float | None] = mapped_column(Float)
    magnitude_pips_high: Mapped[float | None] = mapped_column(Float)
    timing_window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timing_window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    mechanisms: Mapped[Any | None] = mapped_column(JSONB)
    invalidations: Mapped[Any | None] = mapped_column(JSONB)
    catalysts: Mapped[Any | None] = mapped_column(JSONB)
    correlations_snapshot: Mapped[Any | None] = mapped_column(JSONB)
    polymarket_overlay: Mapped[Any | None] = mapped_column(JSONB)

    source_pool_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    critic_verdict: Mapped[str | None] = mapped_column(String(32))
    critic_findings: Mapped[Any | None] = mapped_column(JSONB)
    claude_raw_response: Mapped[Any | None] = mapped_column(JSONB)
    claude_duration_ms: Mapped[int | None] = mapped_column(Integer)

    realized_close_session: Mapped[float | None] = mapped_column(Float)
    realized_high_session: Mapped[float | None] = mapped_column(Float)
    realized_low_session: Mapped[float | None] = mapped_column(Float)
    realized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    brier_contribution: Mapped[float | None] = mapped_column(Float)
