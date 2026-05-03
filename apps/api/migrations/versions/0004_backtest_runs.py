"""backtest_runs — persisted history of backtest executions

Each row is one `BacktestResult` from packages/backtest. Stores config
+ metrics + first/last fold + folder of folds in JSONB so the UI can
render an equity curve summary without re-running the backtest.

PAPER ONLY by ADR-016 — `paper_only=True` enforced in code; the column
is here for audit completeness.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-03
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "backtest_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("model_id", sa.String(128), nullable=False),
        sa.Column("asset", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("config", JSONB(), nullable=False),
        sa.Column("metrics", JSONB(), nullable=False),
        sa.Column("n_folds", sa.Integer(), nullable=False),
        sa.Column("n_signals", sa.Integer(), nullable=False),
        sa.Column("n_trades", sa.Integer(), nullable=False),
        # equity_curve_summary: compressed equity curve as JSONB list of
        # {date, equity} sampled at ~100 points for UI rendering without
        # dumping 2000+ rows.
        sa.Column("equity_curve_summary", JSONB()),
        sa.Column("notes", JSONB()),
        sa.Column("paper_only", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.CheckConstraint("paper_only = true", name="ck_backtest_runs_paper_only"),
    )
    op.create_index("ix_backtest_runs_model_id", "backtest_runs", ["model_id"])
    op.create_index("ix_backtest_runs_asset", "backtest_runs", ["asset"])
    op.create_index("ix_backtest_runs_finished_at", "backtest_runs", ["finished_at"])


def downgrade() -> None:
    op.drop_table("backtest_runs")
