"""cftc_tff_observations table — CFTC TFF weekly positioning (Phase II Layer 1).

The TFF report disaggregates open interest in financial futures into 4
trader classes (Dealer / AssetMgr / LevFunds / Other / Nonrept). Used
for macro-fund positioning intelligence on Ichor's 8-asset universe +
Treasury futures.

TimescaleDB hypertable on `report_date`, chunk_time_interval = 365 days
(weekly cadence, low cardinality, year-per-chunk is comfortable).

Revision ID: 0031
Revises: 0030
Create Date: 2026-05-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cftc_tff_observations",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("report_date", sa.Date(), primary_key=True, nullable=False),
        sa.Column("market_code", sa.String(16), nullable=False),
        sa.Column("market_name", sa.String(200), nullable=False),
        sa.Column("commodity_name", sa.String(64), nullable=False),
        sa.Column("open_interest", sa.BigInteger(), nullable=False),
        # 5 trader classes × {long, short}
        sa.Column("dealer_long", sa.BigInteger(), nullable=False),
        sa.Column("dealer_short", sa.BigInteger(), nullable=False),
        sa.Column("asset_mgr_long", sa.BigInteger(), nullable=False),
        sa.Column("asset_mgr_short", sa.BigInteger(), nullable=False),
        sa.Column("lev_money_long", sa.BigInteger(), nullable=False),
        sa.Column("lev_money_short", sa.BigInteger(), nullable=False),
        sa.Column("other_rept_long", sa.BigInteger(), nullable=False),
        sa.Column("other_rept_short", sa.BigInteger(), nullable=False),
        sa.Column("nonrept_long", sa.BigInteger(), nullable=False),
        sa.Column("nonrept_short", sa.BigInteger(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "report_date",
            "market_code",
            name="uq_cftc_tff_report_date_market_code",
        ),
    )
    op.create_index(
        "ix_cftc_tff_report_date",
        "cftc_tff_observations",
        ["report_date"],
    )
    op.create_index(
        "ix_cftc_tff_market_code",
        "cftc_tff_observations",
        ["market_code"],
    )
    # TimescaleDB hypertable on report_date, 365-day chunks (weekly cadence).
    op.execute(
        "SELECT create_hypertable('cftc_tff_observations', 'report_date', "
        "chunk_time_interval => INTERVAL '365 days', if_not_exists => TRUE);"
    )


def downgrade() -> None:
    op.drop_index("ix_cftc_tff_market_code", table_name="cftc_tff_observations")
    op.drop_index("ix_cftc_tff_report_date", table_name="cftc_tff_observations")
    op.drop_table("cftc_tff_observations")
