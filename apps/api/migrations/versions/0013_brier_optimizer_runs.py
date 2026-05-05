"""brier_optimizer_runs — log of Brier→weights optimizer iterations.

Each row = one optimizer run (typically nightly 02:00 Europe/Paris). Stores
the proposed weights, the Brier delta vs current production weights, and
whether the proposal was adopted at the holdout window end.

Algo follows docs/SPEC_V2_AUTOEVO.md §2:
- Online SGD projected (Flaxman/Zinkevich), regret O(√n)
- LR 0.05, momentum 0.9
- Projection: clamp [0.05, 0.5] then renormalize sum=1
- A/B holdout 21 days minimum (MDE Brier delta = 0.02, σ ≈ 0.15, n ≈ 450)

Schema source: SPEC_V2_AUTOEVO.md §6 (table `brier_optimizer_runs`).

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ALGO_CHECK = "algo IN ('online_sgd', 'thompson_beta')"


def upgrade() -> None:
    op.create_table(
        "brier_optimizer_runs",
        sa.Column("id", UUID(as_uuid=True), nullable=False, primary_key=True),
        sa.Column(
            "ran_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("algo", sa.String(32), nullable=False),
        sa.Column("lr", sa.Numeric(precision=5, scale=3), nullable=True),
        sa.Column("n_obs", sa.Integer(), nullable=True),
        sa.Column("brier_before", sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column("brier_after", sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column("delta", sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column("weights_proposed", JSONB(), nullable=False),
        sa.Column(
            "adopted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("adoption_decision_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("holdout_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("holdout_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint(ALGO_CHECK, name="ck_brier_optimizer_algo"),
    )
    op.create_index(
        "ix_brier_optimizer_runs_ran_at",
        "brier_optimizer_runs",
        [sa.text("ran_at DESC")],
    )
    op.create_index(
        "ix_brier_optimizer_runs_adopted",
        "brier_optimizer_runs",
        ["adopted", sa.text("ran_at DESC")],
    )


def downgrade() -> None:
    op.drop_table("brier_optimizer_runs")
