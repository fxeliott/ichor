"""bund_10y_observations table — ADR-090 P0 step-1 (EUR_USD data-pool extension).

Adds a daily Bund 10Y yield observation table. Source : Bundesbank
SDMX flow `BBSIS/D.I.ZAR.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A`
(daily, free, public, no auth ; PROZENT unit = %).

This replaces the monthly `FRED:IRLTLT01DEM156N` (30-day staleness in
intraday Pass-2) as the canonical EUR-side rate signal for the
`_section_eur_specific` data-pool render. Round-27 ADR-090 §GAP-A.

Hypertable (TimescaleDB) with chunk_time_interval = 365 days. Daily
incremental ingestion ; backfill expected ~1300 rows over 5 years.

CHECK constraint enforces realistic Bund 10Y yield range [-2.0, +10.0]
percent. Historical extremes : -0.85% (Q3 2020) to +9.5% (1981). The
range is wide enough to avoid spurious rejects on regime shifts.

Round-29 ADR-090 implementation (P0 step-1).

Revision ID: 0046
Revises: 0045
Create Date: 2026-05-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "0046"
down_revision: str | None = "0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bund_10y_observations",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("observation_date", sa.Date(), primary_key=True, nullable=False),
        sa.Column("yield_pct", sa.Numeric(6, 4), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("observation_date", name="uq_bund_10y_observation_date"),
        sa.CheckConstraint(
            "yield_pct BETWEEN -2.0 AND 10.0",
            name="ck_bund_10y_yield_range",
        ),
    )
    op.create_index(
        "ix_bund_10y_observation_date",
        "bund_10y_observations",
        ["observation_date"],
    )
    # TimescaleDB hypertable conversion (idempotent if_not_exists=>TRUE
    # safety against re-runs on partial-migration recovery).
    op.execute(
        "SELECT create_hypertable('bund_10y_observations', 'observation_date', "
        "chunk_time_interval => INTERVAL '365 days', if_not_exists => TRUE);"
    )


def downgrade() -> None:
    op.drop_index("ix_bund_10y_observation_date", table_name="bund_10y_observations")
    op.drop_table("bund_10y_observations")
