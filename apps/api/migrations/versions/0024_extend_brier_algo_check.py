"""brier_optimizer_runs — extend algo CHECK with 'diagnostic_v1'.

Migration 0013 hard-coded `algo IN ('online_sgd', 'thompson_beta')`,
but the V1 nightly cron writes a non-SGD diagnostic row (aggregate
Brier monitoring before per-factor SGD ships). Extend the CHECK so
the optimizer can persist its run rows.

Revision ID: 0024
Revises: 0023
Create Date: 2026-05-05
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_CHECK = "algo IN ('online_sgd', 'thompson_beta')"
NEW_CHECK = "algo IN ('online_sgd', 'thompson_beta', 'diagnostic_v1')"


def upgrade() -> None:
    op.drop_constraint("ck_brier_optimizer_algo", "brier_optimizer_runs", type_="check")
    op.create_check_constraint(
        "ck_brier_optimizer_algo",
        "brier_optimizer_runs",
        NEW_CHECK,
    )


def downgrade() -> None:
    op.drop_constraint("ck_brier_optimizer_algo", "brier_optimizer_runs", type_="check")
    op.create_check_constraint(
        "ck_brier_optimizer_algo",
        "brier_optimizer_runs",
        OLD_CHECK,
    )
