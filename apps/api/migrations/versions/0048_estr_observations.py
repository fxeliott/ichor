"""estr_observations table — ADR-090 P0 step-4 (€STR Euro Short-Term Rate).

Adds a daily €STR (Euro Short-Term Rate) observation table. Source :
ECB Data Portal SDMX flow
`EST/B.EU000A2X2A25.WT` (volume-weighted trimmed mean rate, daily,
free public, no auth ; PC unit = percent).

€STR is the front-end EUR funding rate published by the ECB each
business day at ~08:05 CEST after the trans-Euro short-term money
market session. It replaced EONIA in 2022 and is the canonical
euro-side risk-free rate used for OIS curves + benchmark spreads.

Together with the Bund 10Y (migration 0046), €STR gives the EUR
side of `_section_eur_specific` (Pass-2 data-pool render for
EUR_USD) the same daily-fresh coverage that the USD side enjoys
via DGS10/EFFR/SOFR.

Round-34 empirical validation (subagent #2 web research) :
- URL : https://data-api.ecb.europa.eu/service/data/EST/B.EU000A2X2A25.WT?startPeriod=YYYY-MM-DD
- Accept : application/vnd.sdmx.data+csv;version=1.0.0
- Delimiter : COMMA (NOT semicolon like Bundesbank — different per-provider)
- 2026-05-12 sample value : 1.929% (verified live)

Hypertable (TimescaleDB) with chunk_time_interval = 365 days. Daily
incremental ingestion ; backfill expected ~1700 rows from 2019-10-01
(€STR inception) onward.

CHECK constraint enforces realistic €STR range [-1.5, +10.0] percent.
Historical low : -0.62% (Q3 2021 ECB QE peak). Historical high : 4.0%
(Q4 2023 ECB hiking cycle peak). The -1.5..10 band is wide enough
to avoid spurious rejects on future regime shifts.

ADR refs : ADR-090 (Accepted r32b ratify) §"Step-4 backlog refinement
(round-32b)" — €STR verified LIVE.

Revision ID: 0048
Revises: 0047
Create Date: 2026-05-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "0048"
down_revision: str | None = "0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "estr_observations",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("observation_date", sa.Date(), primary_key=True, nullable=False),
        sa.Column("rate_pct", sa.Numeric(6, 4), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("observation_date", name="uq_estr_observation_date"),
        sa.CheckConstraint(
            "rate_pct BETWEEN -1.5 AND 10.0",
            name="ck_estr_rate_range",
        ),
    )
    op.create_index(
        "ix_estr_observation_date",
        "estr_observations",
        ["observation_date"],
    )
    # TimescaleDB hypertable — same pattern as 0046 Bund 10Y. 365-day
    # chunks keep aggregate queries fast (the table is small, expected
    # ~1700 rows over 5 years of €STR history + future).
    op.execute(
        "SELECT create_hypertable('estr_observations', 'observation_date', "
        "chunk_time_interval => INTERVAL '365 days', if_not_exists => TRUE);"
    )


def downgrade() -> None:
    op.drop_index("ix_estr_observation_date", table_name="estr_observations")
    op.drop_table("estr_observations")
