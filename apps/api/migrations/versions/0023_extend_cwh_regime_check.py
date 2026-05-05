"""confluence_weights_history — extend regime CHECK to Ichor quadrants.

Migration 0014 hard-coded `regime IN ('risk_on', 'risk_off', 'neutral')`,
but Ichor's actual regime taxonomy (cf services/risk_appetite +
routers/calibration.py:179) uses 4 quadrants : `haven_bid`,
`funding_stress`, `goldilocks`, `usd_complacency`, plus `all` for
the global baseline. The brier optimizer can't seed weights without
this fix.

Revision ID: 0023
Revises: 0022
Create Date: 2026-05-05
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_CHECK = "regime IN ('risk_on', 'risk_off', 'neutral')"
NEW_CHECK = (
    "regime IN ("
    # legacy (kept for backward compat)
    "'risk_on', 'risk_off', 'neutral', "
    # Ichor regime quadrants (services/risk_appetite + routers/calibration.py:179)
    "'haven_bid', 'funding_stress', 'goldilocks', 'usd_complacency', "
    # Global default for the optimizer's cold-start seeding
    "'all'"
    ")"
)


def upgrade() -> None:
    op.drop_constraint("ck_cwh_regime", "confluence_weights_history", type_="check")
    op.create_check_constraint(
        "ck_cwh_regime",
        "confluence_weights_history",
        NEW_CHECK,
    )


def downgrade() -> None:
    op.drop_constraint("ck_cwh_regime", "confluence_weights_history", type_="check")
    op.create_check_constraint(
        "ck_cwh_regime",
        "confluence_weights_history",
        OLD_CHECK,
    )
