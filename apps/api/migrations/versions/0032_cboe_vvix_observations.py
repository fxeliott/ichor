"""cboe_vvix_observations table — daily CBOE VVIX (vol of VIX) closes (Phase II Layer 1).

VVIX measures the expected 30-day volatility of the VIX itself —
i.e., how violently the implied-vol surface is being repriced. Reads
~85 in calm regimes, >100 elevated, >140 historic vol-surface blowup
territory (e.g. Feb 2018 inversion).

Used alongside SKEW (wave 24) to characterize the full vol-surface
state — SKEW = OOM tail bid, VVIX = ATM-of-vol bid. Both can spike
together (genuine surface stress) or diverge (pure tail vs pure vol-
of-vol turbulence).

TimescaleDB hypertable on `observation_date`, chunk_time_interval =
90 days (mirror cboe_skew_observations).

Revision ID: 0032
Revises: 0031
Create Date: 2026-05-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cboe_vvix_observations",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("observation_date", sa.Date(), primary_key=True, nullable=False),
        sa.Column("vvix_value", sa.Float(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "observation_date",
            name="uq_cboe_vvix_observation_date",
        ),
    )
    op.create_index(
        "ix_cboe_vvix_observation_date",
        "cboe_vvix_observations",
        ["observation_date"],
    )
    # TimescaleDB hypertable — partition on observation_date, 90-day chunks.
    op.execute(
        "SELECT create_hypertable('cboe_vvix_observations', 'observation_date', "
        "chunk_time_interval => INTERVAL '90 days', if_not_exists => TRUE);"
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cboe_vvix_observation_date",
        table_name="cboe_vvix_observations",
    )
    op.drop_table("cboe_vvix_observations")
