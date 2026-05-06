"""session_card_audit — extend session_type CHECK to allow ny_mid + ny_close.

Migration 0005 created the CHECK constraint
`ck_session_card_session_type_valid` with the values
`('pre_londres', 'pre_ny', 'event_driven')`. The systemd timers
registered later for `ny_mid` (17:00 Paris) and `ny_close` (22:00
Paris) silently rejected every batch since 2026-05-04 14:23 — the
CLI returned rc=2 with `unknown session_type` and the DB would
have rejected the row anyway via this CHECK.

ADR-021 §sessions doesn't enumerate the 5 windows explicitly but
the orchestrator + run_session_cards_batch.py treat all 5 as valid.
This migration aligns the DB invariant with the code contract.

Schema change :
  ALTER TABLE session_card_audit
    DROP CONSTRAINT ck_session_card_audit_ck_session_card_session_type_valid;
  ALTER TABLE session_card_audit
    ADD CONSTRAINT ck_session_card_audit_ck_session_card_session_type_valid
    CHECK (session_type IN ('pre_londres', 'pre_ny', 'ny_mid', 'ny_close', 'event_driven'));

Revision ID: 0027
Revises: 0026
Create Date: 2026-05-06
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Naming convention is `ck_%(table_name)s_%(constraint_name)s`, so the
# bare name here is the suffix Alembic prepends `ck_session_card_audit_`
# to. Pass the suffix only — Alembic handles the prefix.
_CONSTRAINT_NAME = "ck_session_card_session_type_valid"


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT_NAME, "session_card_audit", type_="check")
    op.create_check_constraint(
        _CONSTRAINT_NAME,
        "session_card_audit",
        "session_type IN ('pre_londres', 'pre_ny', 'ny_mid', 'ny_close', 'event_driven')",
    )


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT_NAME, "session_card_audit", type_="check")
    op.create_check_constraint(
        _CONSTRAINT_NAME,
        "session_card_audit",
        "session_type IN ('pre_londres', 'pre_ny', 'event_driven')",
    )
