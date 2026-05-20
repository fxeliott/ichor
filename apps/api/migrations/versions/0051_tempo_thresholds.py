"""tempo_thresholds — Mission centrale Axis-7 auto-recalibration sink.

Per-asset absolute daily-range bp thresholds for the tempo_label classification
in `<TodaySessionPulse>` (ADR-099 §Impl(r125)). The r125 ship hardcoded these
in `apps/web2/lib/sessionPulse.ts` as `TEMPO_THRESHOLDS_BY_ASSET` from a one-shot
60-day SSH `psql` calibration. This table is the persistent store that the
r126 weekly cron writes to and that the frontend will consume in r127 via a
new `/v1/tempo-thresholds` endpoint (backend ships first this round, frontend
wire splits to r127).

**Why historical-trace shape** : one row per `(asset, computed_at)` (NOT a
single-row-per-asset upsert). Keeps the audit trail of threshold drift over
time — Mission centrale Axis-7 auto-improvement requires Eliot to *see* the
calibration evolve, not just consume the latest. This also enables future
work (per-pocket drift detector, threshold-vs-realized post-mortem) without
a schema change.

Schema invariants enforced at the DB layer (defense-in-depth, ADR-029 class
hardening — Postgres CHECK is the last-line guard against a bad service-layer
INSERT) :

  - `breakout_bp >= active_bp >= trending_bp >= range_bound_bp >= 0` —
    monotonic ordering matches `tempoLabelByAsset` derivation (a row that
    breaks the chain would mis-classify the live tempo bucket).
  - `sample_size >= 1` — never insert empty calibrations.
  - `window_days >= 7` — single-week window is the smallest defensible
    sample for a daily-range percentile.

NOT a TimescaleDB hypertable — small table (5 assets × weekly cron =
~260 rows/year). Regular Postgres + a `(asset, computed_at DESC)` index
covers the "latest per asset" query that the API endpoint needs.

ADR refs : ADR-099 §Impl(r126) — Mission centrale Axis-7 partial extension ;
sessionPulse.ts (friendly-fermi r125) §"auto-recalibration deferred to r126+".

Revision ID: 0051
Revises: 0050
Create Date: 2026-05-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "0051"
down_revision: str | None = "0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tempo_thresholds",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("asset", sa.String(16), nullable=False),
        sa.Column("breakout_bp", sa.Numeric(8, 2), nullable=False),
        sa.Column("active_bp", sa.Numeric(8, 2), nullable=False),
        sa.Column("trending_bp", sa.Numeric(8, 2), nullable=False),
        sa.Column("range_bound_bp", sa.Numeric(8, 2), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("window_days", sa.Integer(), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tempo_thresholds"),
        sa.UniqueConstraint("asset", "computed_at", name="uq_tempo_thresholds_asset_computed_at"),
        sa.CheckConstraint(
            "breakout_bp >= active_bp",
            name="ck_tempo_thresholds_monotonic_breakout",
        ),
        sa.CheckConstraint(
            "active_bp >= trending_bp",
            name="ck_tempo_thresholds_monotonic_active",
        ),
        sa.CheckConstraint(
            "trending_bp >= range_bound_bp",
            name="ck_tempo_thresholds_monotonic_trending",
        ),
        sa.CheckConstraint(
            "range_bound_bp >= 0",
            name="ck_tempo_thresholds_nonneg",
        ),
        sa.CheckConstraint(
            "sample_size >= 1",
            name="ck_tempo_thresholds_sample_positive",
        ),
        sa.CheckConstraint(
            "window_days >= 7",
            name="ck_tempo_thresholds_window_min",
        ),
    )
    # Compound desc index — supports the "latest per asset" query the API
    # endpoint runs on every request : `ORDER BY computed_at DESC LIMIT 1`
    # per asset. Postgres uses this index for DISTINCT ON queries too.
    op.create_index(
        "ix_tempo_thresholds_asset_computed_at_desc",
        "tempo_thresholds",
        ["asset", sa.text("computed_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tempo_thresholds_asset_computed_at_desc",
        table_name="tempo_thresholds",
    )
    op.drop_table("tempo_thresholds")
