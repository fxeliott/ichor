"""market_data — daily OHLCV TimescaleDB hypertable

Stores bars from any source (stooq, yfinance, oanda…) keyed by
`(asset, bar_date, source)` so we can keep multiple-source-of-truth rows
side-by-side and pick a preferred source at read time.

Hypertable on `bar_date` with 90-day chunks — daily data is small, large
chunks are fine and reduce planning overhead.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "market_data",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("bar_date", sa.Date(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("asset", sa.String(16), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float()),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", "bar_date"),
        # Per-source-of-truth uniqueness, so re-runs are idempotent.
        sa.UniqueConstraint(
            "asset",
            "bar_date",
            "source",
            name="uq_market_data_asset_date_source",
        ),
        sa.CheckConstraint(
            "high >= low AND high >= open AND high >= close AND low <= open AND low <= close",
            name="ck_market_data_ohlc_consistent",
        ),
    )
    op.create_index("ix_market_data_asset", "market_data", ["asset"])
    op.create_index("ix_market_data_bar_date", "market_data", ["bar_date"])
    op.create_index("ix_market_data_source", "market_data", ["source"])

    op.execute(
        "SELECT create_hypertable('market_data', 'bar_date', "
        "chunk_time_interval => INTERVAL '90 days', if_not_exists => TRUE);"
    )


def downgrade() -> None:
    op.drop_table("market_data")
