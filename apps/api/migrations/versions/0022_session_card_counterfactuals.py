"""session_card_counterfactuals — persisted Pass 5 counterfactuals.

Per ADR-017 §Pass 5 + post-mortem audit (2026-05-05) :
the POST /v1/sessions/{id}/counterfactual endpoint executed Pass 5
but threw away the result. This migration creates the sibling table
to persist each run so the post-mortem can compute robustness
deltas (counterfactual_conviction vs original_conviction) over time.

Composite key (card_id, asked_at) — same card can have multiple
counterfactuals (different scrubbed_events).

Revision ID: 0022
Revises: 0021
Create Date: 2026-05-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "session_card_counterfactuals",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("asked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_card_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("asset", sa.String(16), nullable=False, index=True),
        sa.Column("scrubbed_event", sa.String(500), nullable=False),
        # Original card snapshot
        sa.Column("original_bias", sa.String(8), nullable=False),
        sa.Column("original_conviction_pct", sa.Float, nullable=False),
        # Pass 5 result
        sa.Column("counterfactual_bias", sa.String(8), nullable=False),
        sa.Column("counterfactual_conviction_pct", sa.Float, nullable=False),
        sa.Column("delta_narrative", sa.Text, nullable=True),
        sa.Column("new_dominant_drivers", JSONB, nullable=True),
        sa.Column("confidence_delta", sa.Float, nullable=False),
        # Robustness derived (computed at insert time for fast reads)
        sa.Column("robustness_score", sa.Float, nullable=True),
        # Provenance
        sa.Column("model_used", sa.String(64), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.PrimaryKeyConstraint("id", "asked_at"),
    )
    op.create_index(
        "ix_counterfactuals_card_asked",
        "session_card_counterfactuals",
        ["session_card_id", sa.text("asked_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_counterfactuals_card_asked", table_name="session_card_counterfactuals")
    op.drop_table("session_card_counterfactuals")
