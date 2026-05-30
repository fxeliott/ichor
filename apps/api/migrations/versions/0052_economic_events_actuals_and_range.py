"""economic_events — add forecast range + actual columns for surprise-vs-range classification.

Adds 3 nullable String(64) columns to `economic_events` :
  - `forecast_min` : lower bound of analyst forecast range (institutional consensus poll)
  - `forecast_max` : upper bound of analyst forecast range
  - `actual` : published value once the event has fired

Rationale (ADR-099 §Impl(r141)) :

Transcript-driven world-class insight (Macro Trader Accelerator audit r141) :
the institutional read on data surprises distinguishes the RANGE-bound case
(actual deviates from consensus but stays within analyst expectation envelope
-> no repricing) from the OUTSIDE-RANGE case (actual breaches the envelope ->
material repricing event). The forecast point estimate alone is insufficient
for this read -- Ichor needs the min/max of the analyst poll.

The `forecast` String(64) column added in migration 0019 stores the consensus
point. The 3 new columns extend that schema additively to support the
classifier `services/economic_event_surprise.py` shipped this round.

**Type discipline** : String(64) NOT Numeric -- consistency with existing
`forecast`/`previous` text storage convention. ForexFactory and most macro
providers publish values with embedded units ("3.2%", "$50K", "1.5M jobs",
"+5K"). The classifier service handles unit-stripping via
`parse_economic_value()` at read time. Numeric reconciliation lives downstream
in r142 (`cli/run_economic_event_actuals_reconcile.py`).

**Empty state honesty (doctrine #11 calibrated honesty)** : columns are nullable.
Until the r142 reconciler is wired to a free-tier provider (Investing.com /
FRED ALFRED / Trading Economics), they will be NULL. The classifier surfaces
`SurpriseClassification.state = "unavailable"` honestly when missing -- no
fabrication.

**Index** : partial covering index `(currency, scheduled_at DESC) WHERE actual
IS NOT NULL` accelerates the "recently-published surprises" query the
`<FreshDataBanner>` (r140) and `<MacroSurprisePanel>` (r136) consumers will
issue once r142+r143 land. Tiny rowcount cost -- only published events
indexed, not the full forward calendar.

**Zero-lock ADD COLUMN** : all 3 columns nullable + no server_default ->
Postgres 11+ adds the column metadata without rewriting existing rows. Safe
for the prod 4x/day ForexFactory upsert load.

ADR refs : ADR-099 §Impl(r141) -- Mission centrale Axis-5 deepen (forecast
range + actuals foundation). Transcript convergence : 8-market-drivers
framework vs ROADMAP 8-axes (north-star external validation).

Revision ID: 0052
Revises: 0051
Create Date: 2026-05-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0052"
down_revision: str | None = "0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "economic_events",
        sa.Column("forecast_min", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "economic_events",
        sa.Column("forecast_max", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "economic_events",
        sa.Column("actual", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_economic_events_published_recent",
        "economic_events",
        ["currency", sa.text("scheduled_at DESC")],
        postgresql_where=sa.text("actual IS NOT NULL"),
    )


def downgrade() -> None:
    # `postgresql_where=` intentionally omitted -- alembic looks up by name,
    # the predicate is ignored on drop. Style parity with siblings 0042/
    # 0044/0047 (code-reviewer r141 N1 fix).
    op.drop_index(
        "ix_economic_events_published_recent",
        table_name="economic_events",
    )
    op.drop_column("economic_events", "actual")
    op.drop_column("economic_events", "forecast_max")
    op.drop_column("economic_events", "forecast_min")
