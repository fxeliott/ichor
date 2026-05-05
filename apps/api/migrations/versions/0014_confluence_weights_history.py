"""confluence_weights_history — versioned snapshots of confluence engine weights.

Each row = one weights snapshot for a (asset, regime) pair (asset NULL = global
default). The `is_active = TRUE` row per (asset, regime) pair is the live
production weights consumed by `services/confluence_engine.py`.

Schema source: docs/SPEC_V2_AUTOEVO.md §6 (table `confluence_weights_history`).

Has FK on `brier_optimizer_runs(id)` to trace which optimizer iteration
produced each snapshot. Manual edits also allowed (`optimizer_run_id` NULL +
notes column).

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REGIME_CHECK = "regime IN ('risk_on', 'risk_off', 'neutral')"


def upgrade() -> None:
    op.create_table(
        "confluence_weights_history",
        sa.Column("id", UUID(as_uuid=True), nullable=False, primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("asset", sa.String(16), nullable=True),
        sa.Column("regime", sa.String(16), nullable=False),
        sa.Column("weights", JSONB(), nullable=False),
        sa.Column("brier_30d", sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column("ece_30d", sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column(
            "optimizer_run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("brier_optimizer_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint(REGIME_CHECK, name="ck_cwh_regime"),
    )
    op.create_index(
        "ix_cwh_asset_regime_created",
        "confluence_weights_history",
        ["asset", "regime", sa.text("created_at DESC")],
    )
    # FK lookup index — required for ON DELETE SET NULL cascade to avoid
    # seq scans on `brier_optimizer_runs` row deletion.
    op.create_index(
        "ix_cwh_optimizer_run",
        "confluence_weights_history",
        ["optimizer_run_id"],
    )
    # Partial unique index: enforce ≤ 1 active row per (asset, regime).
    op.execute(
        "CREATE UNIQUE INDEX uq_cwh_active_per_pair "
        "ON confluence_weights_history (COALESCE(asset, ''), regime) "
        "WHERE is_active = TRUE;"
    )


def downgrade() -> None:
    op.drop_table("confluence_weights_history")
