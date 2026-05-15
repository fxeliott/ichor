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

    drivers: Mapped[Any | None] = mapped_column(JSONB)
    """Per-factor contribution snapshot from confluence_engine at the
    moment this card was generated. Shape : list[{factor: str,
    contribution: float, evidence: str}]. Added migration 0026 to
    feed brier_optimizer V2 — populated by the brain pipeline once
    SessionCard.drivers is wired ; NULL for legacy rows."""

    realized_close_session: Mapped[float | None] = mapped_column(Float)
    realized_high_session: Mapped[float | None] = mapped_column(Float)
    realized_low_session: Mapped[float | None] = mapped_column(Float)
    # W118 (migration 0045) — open price at session start (bars[0].open).
    # Unlocks the W115b Vovk climatology expert's real empirical y=1
    # rate computation. NULL on legacy rows ; W115b query handles by
    # excluding them from the historical denominator.
    realized_open_session: Mapped[float | None] = mapped_column(Float)
    realized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    brier_contribution: Mapped[float | None] = mapped_column(Float)

    # W105a — Pass-6 scenario_decompose 7-bucket emission (ADR-085).
    # Shape : list[{label, p, magnitude_pips: [low, high], mechanism}]
    # — 7 entries exactly, sum(p) == 1.0, all p in [0, 0.95]. Defaults
    # to empty list for legacy rows. NOT NULL with server_default per
    # migration 0039 so existing rows backfill cleanly.
    scenarios: Mapped[Any] = mapped_column(JSONB, nullable=False)

    # W105g/W108 reconciler — one of the 7 canonical bucket labels
    # (or NULL while the session window is still open). CHECK
    # constraint enforced at DB level (migration 0039) ; the writer
    # uses `services/scenarios.bucket_for_zscore` to derive the label.
    realized_scenario_bucket: Mapped[str | None] = mapped_column(String(16))

    # r62 (migration 0049) — ADR-083 D3 KeyLevel snapshot at orchestrator
    # finalization. Shape : list[{asset, level, kind, side, source, note}]
    # — mirror of /v1/key-levels response items. Empty list `[]` is the
    # canonical "all bands NORMAL" state (distinct from NULL = "not
    # computed"). NOT NULL with server_default `'[]'::jsonb` per
    # migration 0049 so existing rows backfill cleanly. Closes the
    # ADR-083 D3 -> D4 architectural bridge : Pass-2 prompt enrichment
    # + D4 frontend replay read this snapshot rather than recomputing.
    key_levels: Mapped[Any] = mapped_column(JSONB, nullable=False)
