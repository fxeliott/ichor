"""fx_ticks — Polygon Forex WebSocket quote ticks (Phase 2 VPIN)

TimescaleDB hypertable storing per-quote-update bid/ask ticks streamed
from `wss://socket.polygon.io/forex` via the Massive Currencies $49 plan.
Mid-price = (bid + ask) / 2 is computed on insert for downstream VPIN.

Volume is **synthetic** in FX (each tick counts as 1 unit of activity)
because OTC FX has no consolidated trade tape. The collector
`polygon_fx_stream.py` writes one row per Q.* message.

Cardinality estimate : major pairs (EUR/USD, GBP/USD, USD/JPY, AUD/USD,
USD/CAD, XAU/USD) emit ~1-5 quotes/sec during liquid sessions. 6 pairs
× 3/sec average × 86400 s ≈ 1.5M rows/day. Chunk interval 1 day to
keep query plans tight ; compression after 7 days (TimescaleDB native).

ADR-022 boundary : these ticks feed VPIN microstructure features
(probabilities only) ; never order generation, never P&L.

Revision ID: 0020
Revises: 0019
Create Date: 2026-05-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fx_ticks",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("asset", sa.String(16), nullable=False),
        # Polygon ticker, e.g. "C:EUR/USD" or "C:XAU/USD"
        sa.Column("ticker", sa.String(32), nullable=False),
        sa.Column("bid", sa.Float(), nullable=False),
        sa.Column("ask", sa.Float(), nullable=False),
        sa.Column("mid", sa.Float(), nullable=False),
        sa.Column("bid_size", sa.Float(), nullable=True),
        sa.Column("ask_size", sa.Float(), nullable=True),
        sa.Column("exchange_id", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", "ts"),
    )
    op.create_index("ix_fx_ticks_asset_ts", "fx_ticks", ["asset", "ts"])
    op.create_index("ix_fx_ticks_ts", "fx_ticks", ["ts"])
    op.execute(
        "SELECT create_hypertable('fx_ticks', 'ts', "
        "chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);"
    )
    # Native TimescaleDB compression : columnar after 7 days. The high
    # write rate (~1.5M rows/day) makes uncompressed retention costly ;
    # compression typically reaches 20-50× on tick data.
    op.execute(
        "ALTER TABLE fx_ticks SET ("
        "  timescaledb.compress, "
        "  timescaledb.compress_segmentby = 'asset', "
        "  timescaledb.compress_orderby = 'ts DESC'"
        ");"
    )
    op.execute(
        "SELECT add_compression_policy('fx_ticks', INTERVAL '7 days', if_not_exists => TRUE);"
    )


def downgrade() -> None:
    op.execute("SELECT remove_compression_policy('fx_ticks', if_exists => TRUE);")
    op.drop_table("fx_ticks")
