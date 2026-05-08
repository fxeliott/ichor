"""treasury_tic_holdings table — monthly Major Foreign Holders (Phase II Layer 1).

Treasury TIC system: monthly country-level holdings of US Treasury
securities. Lag ~6 weeks (data for month M-1 published ~3rd week M+1).

Used for foreign demand intelligence: country-level decomposition of
the marginal Treasury price-setter — Japan vs China vs UK divergence
drives DXY + long-end yield repricing.

TimescaleDB hypertable on observation_month, 365-day chunks (low
cardinality, monthly cadence).

Revision ID: 0033
Revises: 0032
Create Date: 2026-05-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "treasury_tic_holdings",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("observation_month", sa.Date(), primary_key=True, nullable=False),
        sa.Column("country", sa.String(64), nullable=False),
        sa.Column("holdings_bn_usd", sa.Float(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "country",
            "observation_month",
            name="uq_treasury_tic_country_month",
        ),
    )
    op.create_index(
        "ix_treasury_tic_observation_month",
        "treasury_tic_holdings",
        ["observation_month"],
    )
    op.create_index(
        "ix_treasury_tic_country",
        "treasury_tic_holdings",
        ["country"],
    )
    # TimescaleDB hypertable — partition on observation_month, 365-day chunks.
    op.execute(
        "SELECT create_hypertable('treasury_tic_holdings', 'observation_month', "
        "chunk_time_interval => INTERVAL '365 days', if_not_exists => TRUE);"
    )


def downgrade() -> None:
    op.drop_index(
        "ix_treasury_tic_country",
        table_name="treasury_tic_holdings",
    )
    op.drop_index(
        "ix_treasury_tic_observation_month",
        table_name="treasury_tic_holdings",
    )
    op.drop_table("treasury_tic_holdings")
