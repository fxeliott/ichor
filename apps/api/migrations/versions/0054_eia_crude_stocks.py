"""eia_crude_stocks table — ADR-107 (EIA weekly petroleum crude stocks).

Adds a weekly US petroleum-stock observation table feeding the
theme_classifier ``supply_demand`` driver (Eliot Fathom transcript
étape 1 — the 8th and final driver, after ``price_action_flow`` r189).

Source : EIA OpenData v2 ``petroleum/stoc/wstk`` (free w/ registration,
no anonymous tier ; https://www.eia.gov/opendata/). Weekly series from
the EIA Weekly Petroleum Status Report (released Wed 10:30 ET) :
  - WCESTUS1 : crude oil ending stocks (kbbl)
  - WCRSTUS1 : commercial crude inventories (kbbl)
  - WTTSTUS1 : total petroleum products supplied (kbbl)

Composite PK ``(series_id, observation_date)`` — EIA publishes several
weekly series, one row per (series, week). ``observation_date`` is part
of the PK because TimescaleDB requires the partition column in any
unique index. CHECK clamps ``value`` to ``>= 0`` (a negative inventory
is a parse error). Hypertable (TimescaleDB) with 365-day chunks ; the
table is small (~52 rows/series/year).

The ``supply_demand`` driver reads ``WCESTUS1`` over a rolling 365-day
window (~52 weekly obs → ~51 weekly Δ, clears the shared
``_MIN_PERCENTILE_HISTORY = 30`` Cohen-1988 floor) and flags the driver
when the most-recent absolute weekly change sits at/above the 80th
percentile (self-calibrating ; mirror r189 price_action_flow).

ADR refs : ADR-107 (EIA supply_demand theme driver). ADR-009 Voie D :
pure HTTPS GET against EIA, zero LLM surface. ADR-017 : descriptive
physical-balance context, never a trade signal.

Revision ID: 0054
Revises: 0053
Create Date: 2026-05-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "0054"
down_revision: str | None = "0053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "eia_crude_stocks",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("series_id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("observation_date", sa.Date(), primary_key=True, nullable=False),
        sa.Column("value", sa.Numeric(14, 2), nullable=True),
        sa.Column("unit", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "value IS NULL OR value >= 0",
            name="ck_eia_crude_value_nonneg",
        ),
    )
    op.create_index(
        "ix_eia_crude_observation_date",
        "eia_crude_stocks",
        ["observation_date"],
    )
    # TimescaleDB hypertable — same pattern as 0048 €STR / 0046 Bund.
    # 365-day chunks ; the table is small (~52 rows/series/year).
    op.execute(
        "SELECT create_hypertable('eia_crude_stocks', 'observation_date', "
        "chunk_time_interval => INTERVAL '365 days', if_not_exists => TRUE);"
    )


def downgrade() -> None:
    op.drop_index("ix_eia_crude_observation_date", table_name="eia_crude_stocks")
    op.drop_table("eia_crude_stocks")
