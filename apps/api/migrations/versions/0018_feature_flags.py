"""feature_flags — custom DB-backed feature flag store.

Phase 2 chose custom DB over PostHog feature flags (cf SPEC_V2_HARDENING.md
§3 — "feature flags custom DB Phase 2; PostHog if multi-tenant Phase 3").

Cached in-process via Redis 60s. Read path: `services/feature_flags.py`.

Schema:
- `key` is the flag identifier (e.g., 'rag_pass1_enabled').
- `enabled` = boolean master switch.
- `rollout_pct` = 0-100 gradual rollout (single-user Phase 2 = 0 or 100,
  but kept for Phase 3 multi-tenant).

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feature_flags",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "rollout_pct",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "rollout_pct BETWEEN 0 AND 100",
            name="ck_ff_rollout_pct",
        ),
    )
    # Trigger to auto-update updated_at on row modification.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION feature_flags_set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER feature_flags_updated_at
        BEFORE UPDATE ON feature_flags
        FOR EACH ROW
        EXECUTE FUNCTION feature_flags_set_updated_at();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS feature_flags_updated_at ON feature_flags;")
    op.execute("DROP FUNCTION IF EXISTS feature_flags_set_updated_at();")
    op.drop_table("feature_flags")
