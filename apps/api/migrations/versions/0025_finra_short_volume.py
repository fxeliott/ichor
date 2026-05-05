"""finra_short_volume — daily off-exchange short volume per symbol.

Audit (2026-05-05) caught that the finra_short collector fetched
DailyShortVolumeRecord rows but threw them away (`run_collectors.py`
print "DEFERRED — needs dedicated table"). This migration ships the
table so the data lands in Postgres.

Schema fits the FINRA Reg SHO Daily endpoint shape :
  - per (symbol, trade_date) row
  - short volume, short_exempt volume, total volume, ratio

Revision ID: 0025
Revises: 0024
Create Date: 2026-05-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "finra_short_volume",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("trade_date", sa.Date, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("short_volume", sa.BigInteger, nullable=True),
        sa.Column("short_exempt_volume", sa.BigInteger, nullable=True),
        sa.Column("total_volume", sa.BigInteger, nullable=True),
        sa.Column("short_pct", sa.Float, nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", "trade_date"),
        sa.UniqueConstraint("symbol", "trade_date", name="uq_finra_symbol_date"),
    )
    op.create_index(
        "ix_finra_short_symbol_date",
        "finra_short_volume",
        ["symbol", sa.text("trade_date DESC")],
    )
    op.create_index(
        "ix_finra_short_trade_date",
        "finra_short_volume",
        [sa.text("trade_date DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_finra_short_trade_date", table_name="finra_short_volume")
    op.drop_index("ix_finra_short_symbol_date", table_name="finra_short_volume")
    op.drop_table("finra_short_volume")
