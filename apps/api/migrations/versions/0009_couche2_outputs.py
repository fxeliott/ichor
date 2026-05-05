"""couche2_outputs — output of the 4 Couche-2 agents (CB-NLP, News-NLP, Sentiment, Positioning).

Stores the JSON payload each Couche-2 agent emits per run, plus provenance
(model used, input window, sources consumed, cost). Consumed by `data_pool`
sections that feed Pass 1 (regime) and Pass 2 (asset framework).

Cadence (cf SPEC.md §3.2):
  - CB-NLP, News-NLP : every 4h (Sonnet 4.6)
  - Sentiment, Positioning : every 6h (Haiku 4.5)

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AGENT_KIND_CHECK = "agent_kind IN ('cb_nlp', 'news_nlp', 'sentiment', 'positioning')"


def upgrade() -> None:
    op.create_table(
        "couche2_outputs",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("ran_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("agent_kind", sa.String(32), nullable=False),
        sa.Column("model_used", sa.String(64), nullable=False),
        sa.Column("input_window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("input_window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("input_sources", JSONB(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("token_input", sa.Integer(), nullable=True),
        sa.Column("token_output", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", "ran_at"),
        sa.CheckConstraint(AGENT_KIND_CHECK, name="ck_couche2_agent_kind"),
    )
    op.create_index(
        "ix_couche2_outputs_agent_ran",
        "couche2_outputs",
        ["agent_kind", sa.text("ran_at DESC")],
    )
    op.execute(
        "SELECT create_hypertable('couche2_outputs', 'ran_at', "
        "chunk_time_interval => INTERVAL '30 days', if_not_exists => TRUE);"
    )


def downgrade() -> None:
    op.drop_table("couche2_outputs")
