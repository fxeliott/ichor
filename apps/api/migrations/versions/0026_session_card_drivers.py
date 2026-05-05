"""session_card_audit — add `drivers` JSONB column.

Per ADR-022 Brier-optimizer V2 prep : we need to store the per-factor
contribution snapshot at the moment a session card is generated, so
the optimizer can fit projected-SGD weights on a real (factor_signals,
outcomes) matrix instead of just running the V1 diagnostic on aggregate
brier_contribution.

The column is nullable — the brain pipeline doesn't populate it yet.
A follow-up wiring will pass confluence_engine.assess_confluence
drivers through SessionCard → to_audit_row. Existing rows stay NULL
(bridged via fallback in brier_optimizer V2).

Schema :
  drivers jsonb NULL  --  list[{factor: str, contribution: float, evidence: str}]

Revision ID: 0026
Revises: 0025
Create Date: 2026-05-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "session_card_audit",
        sa.Column("drivers", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("session_card_audit", "drivers")
