"""cboe_skew_observations table — daily CBOE SKEW Index closes (Phase II Layer 1).

The SKEW index proxies the tail-risk component of S&P 500 returns
that VIX (ATM-only) misses. Used by DOLLAR_SMILE_BREAK detector
(broken-smile gate per Stephen Jen) and tail-regime classification.

TimescaleDB hypertable on `observation_date`, chunk_time_interval =
90 days (daily series, low cardinality, ample headroom).

Revision ID: 0030
Revises: 0029
Create Date: 2026-05-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cboe_skew_observations",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("observation_date", sa.Date(), primary_key=True, nullable=False),
        sa.Column("skew_value", sa.Float(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "observation_date",
            name="uq_cboe_skew_observation_date",
        ),
    )
    op.create_index(
        "ix_cboe_skew_observation_date",
        "cboe_skew_observations",
        ["observation_date"],
    )
    # TimescaleDB hypertable — partition on observation_date, 90-day chunks.
    op.execute(
        "SELECT create_hypertable('cboe_skew_observations', 'observation_date', "
        "chunk_time_interval => INTERVAL '90 days', if_not_exists => TRUE);"
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cboe_skew_observation_date",
        table_name="cboe_skew_observations",
    )
    op.drop_table("cboe_skew_observations")
