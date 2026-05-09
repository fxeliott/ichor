"""nfib_sbet_observations table — monthly NFIB SBET (W74).

NFIB Small Business Economic Trends report. Released ~2nd Tuesday of the
month for the prior month's survey. PDF-scraped headline + uncertainty.

TimescaleDB hypertable on report_month, 365-day chunks.

Revision ID: 0036
Revises: 0035
Create Date: 2026-05-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "nfib_sbet_observations",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("report_month", sa.Date(), primary_key=True, nullable=False),
        sa.Column("sboi", sa.Float(), nullable=False),
        sa.Column("uncertainty_index", sa.Float(), nullable=True),
        sa.Column("source_pdf_url", sa.String(512), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "report_month",
            name="uq_nfib_sbet_report_month",
        ),
    )
    op.create_index(
        "ix_nfib_sbet_report_month",
        "nfib_sbet_observations",
        ["report_month"],
    )
    op.execute(
        "SELECT create_hypertable('nfib_sbet_observations', 'report_month', "
        "chunk_time_interval => INTERVAL '365 days', if_not_exists => TRUE);"
    )


def downgrade() -> None:
    op.drop_index(
        "ix_nfib_sbet_report_month",
        table_name="nfib_sbet_observations",
    )
    op.drop_table("nfib_sbet_observations")
