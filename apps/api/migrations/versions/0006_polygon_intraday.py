"""polygon_intraday — 1-min OHLCV bars from Polygon.io Starter

Adds a single TimescaleDB hypertable for the 8 Phase-1 assets at
1-minute granularity. Chunk interval 7 days (high write volume :
~480 bars/asset/day × 8 assets = ~3.8k rows/day).

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "polygon_intraday",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("bar_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("asset", sa.String(16), nullable=False),
        sa.Column("ticker", sa.String(32), nullable=False),
        # Polygon-side ticker, e.g. "C:EURUSD" / "I:NDX" / "X:XAUUSD"
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.BigInteger()),
        sa.Column("vwap", sa.Float()),
        sa.Column("transactions", sa.Integer()),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", "bar_ts"),
        # TimescaleDB unique key must include the partition column.
        sa.UniqueConstraint("asset", "bar_ts", name="uq_polygon_asset_ts"),
    )
    op.create_index("ix_polygon_intraday_asset", "polygon_intraday", ["asset"])
    op.create_index("ix_polygon_intraday_bar_ts", "polygon_intraday", ["bar_ts"])
    op.execute(
        "SELECT create_hypertable('polygon_intraday', 'bar_ts', "
        "chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE);"
    )


def downgrade() -> None:
    op.drop_table("polygon_intraday")
