"""prompt_versions — versioned system prompts per pass+scope.

Each row = one prompt body for a specific (pass_index, scope) combination.
DSPy MIPROv2 / BootstrapFewShot meta-prompt tuner can append new versions
(source = 'meta_prompt_tuner_auto'); manual edits also append rows
(source = 'manual'). Self-FK `parent_id` traces the lineage.

Schema source: docs/SPEC_V2_AUTOEVO.md §3 + §6 (table `prompt_versions`).

The "active" version per (pass_index, scope) lives in a feature flag or
config row, not here — this table is append-only history.

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SOURCE_CHECK = "source IN ('manual', 'meta_prompt_tuner_auto', 'imported')"


def upgrade() -> None:
    op.create_table(
        "prompt_versions",
        sa.Column("id", UUID(as_uuid=True), nullable=False, primary_key=True),
        sa.Column("pass_index", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "parent_id",
            UUID(as_uuid=True),
            sa.ForeignKey("prompt_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.CheckConstraint("pass_index BETWEEN 1 AND 6", name="ck_pv_pass_index"),
        sa.CheckConstraint(SOURCE_CHECK, name="ck_pv_source"),
    )
    op.create_index(
        "ix_pv_scope_pass_created",
        "prompt_versions",
        ["scope", "pass_index", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_table("prompt_versions")
