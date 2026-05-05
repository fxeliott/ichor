"""prompt_evals — eval results for each prompt version on the dev set.

DSPy meta-prompt tuner runs a candidate prompt against the eval devset
(50-100 Eliot-labelled cards) and persists the resulting metrics. A
candidate is promoted to active only if it beats the baseline on ALL
metrics and >2pts on ≥1 metric (cf SPEC_V2_AUTOEVO.md §3).

Auto-rollback at J+7 if Brier delta > +0.01 sustained.

Schema source: docs/SPEC_V2_AUTOEVO.md §3 + §6 (table `prompt_evals`).

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prompt_evals",
        sa.Column("id", UUID(as_uuid=True), nullable=False, primary_key=True),
        sa.Column(
            "prompt_version_id",
            UUID(as_uuid=True),
            sa.ForeignKey("prompt_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("devset_id", sa.String(64), nullable=False),
        sa.Column("approval_rate", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("faithfulness", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("brier_proj", sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column("ece", sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column(
            "hallucination_rate",
            sa.Numeric(precision=4, scale=3),
            nullable=True,
        ),
        sa.Column(
            "ran_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("metrics_extra", JSONB(), nullable=True),
        sa.CheckConstraint(
            "approval_rate IS NULL OR (approval_rate BETWEEN 0 AND 1)",
            name="ck_pe_approval_rate",
        ),
        sa.CheckConstraint(
            "faithfulness IS NULL OR (faithfulness BETWEEN 0 AND 1)",
            name="ck_pe_faithfulness",
        ),
        sa.CheckConstraint(
            "hallucination_rate IS NULL OR (hallucination_rate BETWEEN 0 AND 1)",
            name="ck_pe_hallucination_rate",
        ),
    )
    op.create_index(
        "ix_pe_version_ran",
        "prompt_evals",
        ["prompt_version_id", sa.text("ran_at DESC")],
    )
    op.create_index(
        "ix_pe_devset_ran",
        "prompt_evals",
        ["devset_id", sa.text("ran_at DESC")],
    )


def downgrade() -> None:
    op.drop_table("prompt_evals")
