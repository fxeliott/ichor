"""couche2_outputs — extend agent_kind CHECK to allow 'macro'.

The MacroAgent (`packages/agents/.../agents/macro.py`) was already
exported in the agents package but blocked from `couche2_outputs` by
migration 0009's CHECK constraint listing only the 4 original agents.
This migration replaces the constraint with a 5-value list. No data
move — existing rows already satisfy the looser constraint.

Revision ID: 0021
Revises: 0020
Create Date: 2026-05-05
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_CHECK = "agent_kind IN ('cb_nlp', 'news_nlp', 'sentiment', 'positioning')"
NEW_CHECK = "agent_kind IN ('cb_nlp', 'news_nlp', 'sentiment', 'positioning', 'macro')"


def upgrade() -> None:
    op.drop_constraint("ck_couche2_agent_kind", "couche2_outputs", type_="check")
    op.create_check_constraint(
        "ck_couche2_agent_kind",
        "couche2_outputs",
        NEW_CHECK,
    )


def downgrade() -> None:
    op.drop_constraint("ck_couche2_agent_kind", "couche2_outputs", type_="check")
    op.create_check_constraint(
        "ck_couche2_agent_kind",
        "couche2_outputs",
        OLD_CHECK,
    )
