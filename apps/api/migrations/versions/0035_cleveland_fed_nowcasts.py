"""cleveland_fed_nowcasts table — daily inflation nowcast snapshots (W72).

Cleveland Fed publishes a daily nowcast of CPI / Core CPI / PCE / Core
PCE inflation across three horizons (MoM, QoQ SAAR, YoY). Updated
~10:00 ET (~16:00 Paris) every business day. Daily revisions of the
current and following month/quarter target.

TimescaleDB hypertable on revision_date, 365-day chunks.

Revision ID: 0035
Revises: 0034
Create Date: 2026-05-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cleveland_fed_nowcasts",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("revision_date", sa.Date(), primary_key=True, nullable=False),
        sa.Column("measure", sa.String(32), nullable=False),
        sa.Column("horizon", sa.String(8), nullable=False),
        sa.Column("target_period", sa.Date(), nullable=False),
        sa.Column("nowcast_value", sa.Float(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "measure",
            "horizon",
            "target_period",
            "revision_date",
            name="uq_cleveland_fed_nowcast_measure_horizon_target_revision",
        ),
    )
    op.create_index(
        "ix_cleveland_fed_nowcast_revision_date",
        "cleveland_fed_nowcasts",
        ["revision_date"],
    )
    op.create_index(
        "ix_cleveland_fed_nowcast_measure",
        "cleveland_fed_nowcasts",
        ["measure"],
    )
    # TimescaleDB hypertable.
    op.execute(
        "SELECT create_hypertable('cleveland_fed_nowcasts', 'revision_date', "
        "chunk_time_interval => INTERVAL '365 days', if_not_exists => TRUE);"
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cleveland_fed_nowcast_measure",
        table_name="cleveland_fed_nowcasts",
    )
    op.drop_index(
        "ix_cleveland_fed_nowcast_revision_date",
        table_name="cleveland_fed_nowcasts",
    )
    op.drop_table("cleveland_fed_nowcasts")
