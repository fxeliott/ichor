"""confluence_history — persisted snapshots of /v1/confluence per asset.

Allows time-series visualisation of how each asset's confluence score
+ dominant direction evolves day-by-day. Powers the sparkline UI on
the /confluence dashboard.

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "confluence_history",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("asset", sa.String(16), nullable=False),
        sa.Column("score_long", sa.Float(), nullable=False),
        sa.Column("score_short", sa.Float(), nullable=False),
        sa.Column("score_neutral", sa.Float(), nullable=False),
        sa.Column("dominant_direction", sa.String(8), nullable=False),
        sa.Column("confluence_count", sa.Integer(), nullable=False),
        sa.Column("n_drivers", sa.Integer(), nullable=False),
        sa.Column("drivers", JSONB(), nullable=True),
        # Stored as JSONB list of {factor, contribution, evidence, source}.
        sa.PrimaryKeyConstraint("id", "captured_at"),
        sa.UniqueConstraint("asset", "captured_at", name="uq_confluence_history_asset_ts"),
    )
    op.create_index("ix_confluence_history_asset", "confluence_history", ["asset"])
    op.create_index(
        "ix_confluence_history_captured_at",
        "confluence_history",
        ["captured_at"],
    )
    op.execute(
        "SELECT create_hypertable('confluence_history', 'captured_at', "
        "chunk_time_interval => INTERVAL '30 days', if_not_exists => TRUE);"
    )


def downgrade() -> None:
    op.drop_table("confluence_history")
