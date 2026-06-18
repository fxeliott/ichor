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

from sqlalchemy import DateTime, Float, Integer, String, Text
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
    # Type is Text() (NOT String(16)) to match migration 0039:72-79
    # `sa.Column("realized_scenario_bucket", sa.Text(), nullable=True)`
    # — DB is the source of truth ; the label whitelist is enforced by the
    # CHECK constraint, not a varchar length (the String(16) was ORM-only
    # drift that produced a spurious alembic-autogenerate diff).
    realized_scenario_bucket: Mapped[str | None] = mapped_column(Text())

    # r62 (migration 0049) — ADR-083 D3 KeyLevel snapshot at orchestrator
    # finalization. Shape : list[{asset, level, kind, side, source, note}]
    # — mirror of /v1/key-levels response items. Empty list `[]` is the
    # canonical "all bands NORMAL" state (distinct from NULL = "not
    # computed"). NOT NULL with server_default `'[]'::jsonb` per
    # migration 0049 so existing rows backfill cleanly. Closes the
    # ADR-083 D3 -> D4 architectural bridge : Pass-2 prompt enrichment
    # + D4 frontend replay read this snapshot rather than recomputing.
    key_levels: Mapped[Any] = mapped_column(JSONB, nullable=False)

    # r95 (migration 0050) — ADR-104 (ADR-099 §T3.2) FRED-liveness
    # degraded-input manifest (the ADR-103 runtime
    # `DataPool.degraded_inputs`) frozen at card generation. Shape :
    # list[{series_id, status: "stale"|"absent", latest_date, age_days,
    # max_age_days, impacted}] — mirror of the `DegradedInputOut`
    # schemas.py SSOT. DELIBERATELY NULLABLE with NO server_default
    # (diverges on purpose from key_levels/scenarios NOT NULL DEFAULT
    # '[]') : NULL = "liveness not tracked at this card's generation"
    # (every pre-0050 card — honest "unknown", NOT "all fresh") ;
    # [] = "tracked, all anchors fresh" ; [...] = "degraded". A '[]'
    # backfill would be the exact silent-skip dishonesty ADR-103 kills.
    degraded_inputs: Mapped[Any | None] = mapped_column(JSONB, nullable=True)

    # S04 (migration 0055, « kill the 50/50 ») — synthesis-layer reads frozen
    # at card generation so the apex SessionVerdict conviction fusion
    # (services.conviction_fusion.fuse_conviction) is REPRODUCIBLE at read-time
    # (/v1/verdict is polled every 60 s — recomputing the 12-factor confluence
    # / theme / cross-asset dollar live per poll would be heavy AND drift the
    # apex under the user). Each is DELIBERATELY NULLABLE with NO server_default
    # (mirror of degraded_inputs above) : NULL = "synthesis not captured at this
    # card's generation" (every pre-0055 card + any card whose best-effort
    # capture failed) → the fuser degrades to the bucket-only conviction with
    # the graded dead-zone still applied. Never a fabricated neutral default.
    confluence_snapshot: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    """confluence_engine read at generation. Shape :
    {"dominant_direction": "long"|"short"|"neutral", "score_long": float,
    "score_short": float, "confluence_count": int}. Feeds fuse_conviction
    ``confluence_lean``."""

    theme_snapshot: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    """Dominant market-theme read at generation (GLOBAL, not per-asset).
    Shape : {"present": bool, "top_theme": str|null, "strength": float|null}.
    Feeds fuse_conviction ``theme_present`` (non-directional — ADR-017)."""

    dollar_snapshot: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    """cross_asset_dollar_coherence read at generation. Shape :
    {"consensus": "usd_up"|"usd_down"|"mixed"|"neutral",
    "consensus_strength": float}. Feeds fuse_conviction ``dollar_consensus``
    + ``dollar_strength``."""

    # S06 Chantier C (migration 0056) — the Chantier-C ``DimensionVote`` layers
    # (COT positioning today ; rates / volume / geopolitics next) frozen at card
    # generation as ``services.dimension_vote.votes_to_snapshot(votes)``. Same
    # write-time-snapshot rationale as the 0055 synthesis snapshots above
    # (reproducible apex under the 60 s /v1/verdict poll + the Chantier-A
    # benchmark replay). DELIBERATELY NULLABLE with NO server_default (mirror of
    # confluence/theme/dollar above) : NULL = "votes not captured at this card's
    # generation" (every pre-0056 card + any card generated with the
    # ``cot_dimension_vote_enabled`` flag OFF + any best-effort capture failure)
    # → ``votes_from_snapshot(None)`` == ``()`` → the fuser is byte-identical to
    # the legacy path (C-2a ``votes=()``). A '[]'::jsonb backfill would falsely
    # assert "votes computed, all abstained". Shape : list of
    # {"provenance", "direction_hint", "strength", "freshness", "honest_absence",
    # "directional"} (ADR-120 contract).
    dimension_votes: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    """Chantier-C DimensionVote snapshot list. Feeds fuse_conviction ``votes``
    (gated by feature flag ``cot_dimension_vote_enabled``)."""
