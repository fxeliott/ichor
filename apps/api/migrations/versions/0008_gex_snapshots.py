"""gex_snapshots — FlashAlpha dealer GEX snapshots persisted per asset.

Persists the dealer-gamma snapshots that `collectors/flashalpha.py` already
fetches but currently throws away (cf SPEC.md §2.2 #9). Powers the
`data_pool` `gex` section consumed by Pass 2 (asset framework) on SPX/NDX
options-bearing instruments.

FlashAlpha free tier = 5 req/day. We capture 2 assets (SPX, NDX) with a
twice-daily cadence, which fits inside the quota. Hypertable on
`captured_at` with 30-day chunks (small volume).

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, NUMERIC, UUID

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gex_snapshots",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("asset", sa.String(16), nullable=False),
        # Aggregate dealer gamma exposure ($/point). Sign convention: positive
        # = long gamma (vol-suppressing), negative = short gamma (vol-amplifying).
        sa.Column("dealer_gex_total", NUMERIC(precision=20, scale=4), nullable=True),
        sa.Column("gamma_flip", NUMERIC(precision=14, scale=4), nullable=True),
        sa.Column("call_wall", NUMERIC(precision=14, scale=4), nullable=True),
        sa.Column("put_wall", NUMERIC(precision=14, scale=4), nullable=True),
        sa.Column("vol_trigger", NUMERIC(precision=14, scale=4), nullable=True),
        sa.Column("spot_at_capture", NUMERIC(precision=14, scale=4), nullable=True),
        sa.Column("source", sa.String(32), nullable=False, server_default="flashalpha"),
        sa.Column("raw", JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("id", "captured_at"),
    )
    op.create_index("ix_gex_snapshots_asset", "gex_snapshots", ["asset"])
    op.create_index(
        "ix_gex_snapshots_asset_captured",
        "gex_snapshots",
        ["asset", sa.text("captured_at DESC")],
    )
    op.execute(
        "SELECT create_hypertable('gex_snapshots', 'captured_at', "
        "chunk_time_interval => INTERVAL '30 days', if_not_exists => TRUE);"
    )


def downgrade() -> None:
    op.drop_table("gex_snapshots")
