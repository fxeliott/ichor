"""myfxbook_outlooks table — MyFXBook Community Outlook snapshots (W77).

Retail FX trader sentiment per pair (long_pct / short_pct + volumes).
Replaces the discontinued OANDA Open Position Ratios endpoint
(deprecated 2024). MyFXBook Community Outlook free API, 100 req/24h
limit, IP-bound session.

TimescaleDB hypertable on fetched_at, 30-day chunks (high cadence).

Revision ID: 0037
Revises: 0036
Create Date: 2026-05-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "myfxbook_outlooks",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("fetched_at", sa.DateTime(timezone=True), primary_key=True, nullable=False),
        sa.Column("pair", sa.String(16), nullable=False),
        sa.Column("long_pct", sa.Float(), nullable=False),
        sa.Column("short_pct", sa.Float(), nullable=False),
        sa.Column("long_volume", sa.Float(), nullable=True),
        sa.Column("short_volume", sa.Float(), nullable=True),
        sa.Column("avg_long_price", sa.Float(), nullable=True),
        sa.Column("avg_short_price", sa.Float(), nullable=True),
        sa.Column("long_positions", sa.Integer(), nullable=True),
        sa.Column("short_positions", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_myfxbook_outlooks_fetched_at",
        "myfxbook_outlooks",
        ["fetched_at"],
    )
    op.create_index(
        "ix_myfxbook_outlooks_pair_fetched_at",
        "myfxbook_outlooks",
        ["pair", "fetched_at"],
    )
    op.execute(
        "SELECT create_hypertable('myfxbook_outlooks', 'fetched_at', "
        "chunk_time_interval => INTERVAL '30 days', if_not_exists => TRUE);"
    )


def downgrade() -> None:
    op.drop_index(
        "ix_myfxbook_outlooks_pair_fetched_at",
        table_name="myfxbook_outlooks",
    )
    op.drop_index(
        "ix_myfxbook_outlooks_fetched_at",
        table_name="myfxbook_outlooks",
    )
    op.drop_table("myfxbook_outlooks")
