"""nyfed_mct_observations table — NY Fed Multivariate Core Trend (W71).

NY Fed MCT replaces the discontinued FRED UIGFULL series. Dynamic-factor
trend inflation across 17 PCE sectors, monthly cadence, ~1st business
day of the month following the BEA PCE release (~10:00 ET).

TimescaleDB hypertable on observation_month, 365-day chunks.

Revision ID: 0034
Revises: 0033
Create Date: 2026-05-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "nyfed_mct_observations",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("observation_month", sa.Date(), primary_key=True, nullable=False),
        sa.Column("mct_trend_pct", sa.Float(), nullable=False),
        sa.Column("headline_pce_yoy", sa.Float(), nullable=True),
        sa.Column("core_pce_yoy", sa.Float(), nullable=True),
        sa.Column("goods_pct", sa.Float(), nullable=True),
        sa.Column("services_ex_housing_pct", sa.Float(), nullable=True),
        sa.Column("housing_pct", sa.Float(), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "observation_month",
            name="uq_nyfed_mct_observation_month",
        ),
    )
    op.create_index(
        "ix_nyfed_mct_observation_month",
        "nyfed_mct_observations",
        ["observation_month"],
    )
    # TimescaleDB hypertable — partition on observation_month, 365-day chunks.
    op.execute(
        "SELECT create_hypertable('nyfed_mct_observations', 'observation_month', "
        "chunk_time_interval => INTERVAL '365 days', if_not_exists => TRUE);"
    )


def downgrade() -> None:
    op.drop_index(
        "ix_nyfed_mct_observation_month",
        table_name="nyfed_mct_observations",
    )
    op.drop_table("nyfed_mct_observations")
