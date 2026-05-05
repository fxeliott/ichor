"""audit_log — append-only audit trail for sensitive actions.

Every state-changing API endpoint and admin operation writes one row here.
Retention policy: 365 days (purged nightly by `cron audit_log_purge.py`).

Schema source: docs/SPEC_V2_HARDENING.md §1 / §7.

NOT a Timescale hypertable on purpose — volume is low (< 100k rows/year for
single-user) and we frequently query by `actor` (non-time predicate). A
plain BTREE on `(ts DESC)` + `(actor, ts DESC)` is sufficient.

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("resource", sa.Text(), nullable=True),
        sa.Column("request_id", UUID(as_uuid=True), nullable=True),
        sa.Column("ip", INET(), nullable=True),
        # Note: column is named `meta` (not `metadata`) because `metadata`
        # is reserved on SQLAlchemy ORM `Base` instances. Using `meta`
        # avoids a future ORM mapping clash.
        sa.Column("meta", JSONB(), nullable=True),
    )
    op.create_index("ix_audit_log_ts", "audit_log", [sa.text("ts DESC")])
    op.create_index(
        "ix_audit_log_actor_ts",
        "audit_log",
        ["actor", sa.text("ts DESC")],
    )
    op.create_index(
        "ix_audit_log_action_ts",
        "audit_log",
        ["action", sa.text("ts DESC")],
    )


def downgrade() -> None:
    op.drop_table("audit_log")
