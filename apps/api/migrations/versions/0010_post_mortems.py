"""post_mortems — weekly Claude Opus 4.7 post-mortems (8-section template).

Persists the weekly post-mortem produced by `cron post_mortem_weekly.py`
every Sunday 18:00 Europe/Paris. Schema follows the 8 sections defined in
docs/SPEC_V2_AUTOEVO.md §4: header / top hits / top miss / drift detected /
narratives / calibration / suggestions / stats.

The actual markdown is stored on disk under `docs/post_mortem/{YYYY-Www}.md`
(committed to repo for git-traceable history). This table indexes the
metadata + structured-data sections so they can be queried/aggregated.

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "post_mortems",
        sa.Column("id", UUID(as_uuid=True), nullable=False, primary_key=True),
        sa.Column("iso_year", sa.Integer(), nullable=False),
        sa.Column("iso_week", sa.Integer(), nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("markdown_path", sa.Text(), nullable=False),
        sa.Column("top_hits", JSONB(), nullable=True),
        sa.Column("top_miss", JSONB(), nullable=True),
        sa.Column("drift_detected", JSONB(), nullable=True),
        sa.Column("narratives", JSONB(), nullable=True),
        sa.Column("calibration", JSONB(), nullable=True),
        sa.Column("suggestions", JSONB(), nullable=True),
        sa.Column("stats", JSONB(), nullable=True),
        sa.Column("actionable_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "actionable_count_resolved",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.UniqueConstraint("iso_year", "iso_week", name="uq_post_mortems_iso_week"),
        sa.CheckConstraint("iso_week BETWEEN 1 AND 53", name="ck_post_mortems_iso_week"),
        sa.CheckConstraint("iso_year >= 2025", name="ck_post_mortems_iso_year"),
    )
    op.create_index(
        "ix_post_mortems_generated_at",
        "post_mortems",
        [sa.text("generated_at DESC")],
    )


def downgrade() -> None:
    op.drop_table("post_mortems")
