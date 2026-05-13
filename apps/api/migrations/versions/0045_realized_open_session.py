"""realized_open_session column on session_card_audit — Phase D W118 (ADR-087).

Adds the missing `realized_open_session FLOAT` column so the
reconciler (`cli.reconcile_outcomes`) can persist `bars[0].open`
alongside the existing `realized_{close,high,low}_session` triplet.
Unlocks two downstream consumers :

1. **W115b real climatology rate** : `cli.run_brier_aggregator.
   _climatology_rate` currently returns 0.5 stand-in. Once
   `realized_open_session` is populated, climatology can compute
   the empirical historical `P(y=1)` per (asset, session_type) as
   `count(close > open) / count(*)` over the trailing 365 d. The
   Vovk-AA climatology expert becomes informative instead of a tie-
   breaker.

2. **W116b PBS attribution by direction** : aggregates can break out
   bull-bias vs bear-bias outcomes without re-querying Polygon bars.

The column is NULLable + has no DEFAULT — existing 158 rows stay
NULL ; new cards write it via the reconciler patch. The W115b
climatology query handles NULL rows by excluding them from the
historical denominator.

Revision ID: 0045
Revises: 0044
Create Date: 2026-05-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0045"
down_revision: str | None = "0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "session_card_audit",
        sa.Column("realized_open_session", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("session_card_audit", "realized_open_session")
