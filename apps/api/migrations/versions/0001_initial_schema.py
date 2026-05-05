"""initial Ichor schema — briefings, alerts, predictions_audit, bias_signals + TimescaleDB hypertable

Revision ID: 0001
Revises:
Create Date: 2026-05-02

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- briefings ----
    op.create_table(
        "briefings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("briefing_type", sa.String(32), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assets", ARRAY(sa.String(16)), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("context_markdown", sa.Text()),
        sa.Column("context_token_estimate", sa.Integer()),
        sa.Column("claude_runner_task_id", UUID(as_uuid=True)),
        sa.Column("briefing_markdown", sa.Text()),
        sa.Column("claude_raw_response", JSONB()),
        sa.Column("claude_duration_ms", sa.Integer()),
        sa.Column("audio_mp3_url", sa.String(512)),
        sa.Column("error_message", sa.Text()),
    )
    op.create_index("ix_briefings_briefing_type", "briefings", ["briefing_type"])
    op.create_index("ix_briefings_triggered_at", "briefings", ["triggered_at"])
    op.create_index("ix_briefings_status", "briefings", ["status"])

    # ---- alerts ----
    op.create_table(
        "alerts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("alert_code", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("asset", sa.String(16)),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metric_name", sa.String(128), nullable=False),
        sa.Column("metric_value", sa.Float(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("source_payload", JSONB()),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "severity IN ('info','warning','critical')",
            name="alerts_severity_valid",
        ),
        sa.CheckConstraint(
            "direction IN ('above','below','cross_up','cross_down')",
            name="alerts_direction_valid",
        ),
    )
    op.create_index("ix_alerts_alert_code", "alerts", ["alert_code"])
    op.create_index("ix_alerts_severity", "alerts", ["severity"])
    op.create_index("ix_alerts_asset", "alerts", ["asset"])
    op.create_index("ix_alerts_triggered_at", "alerts", ["triggered_at"])

    # ---- predictions_audit (TimescaleDB hypertable) ----
    # Composite PK (id, generated_at): TimescaleDB requires the partitioning
    # column to be part of every UNIQUE constraint, including the PK.
    op.create_table(
        "predictions_audit",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("model_id", sa.String(128), nullable=False),
        sa.Column("model_family", sa.String(32), nullable=False),
        sa.Column("asset", sa.String(16), nullable=False),
        sa.Column("horizon_hours", sa.Integer(), nullable=False),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("raw_score", sa.Float(), nullable=False),
        sa.Column("calibrated_probability", sa.Float()),
        sa.Column("feature_snapshot_hash", sa.String(64), nullable=False),
        sa.Column("realized_direction", sa.String(8)),
        sa.Column("realized_at", sa.DateTime(timezone=True)),
        sa.Column("brier_contribution", sa.Float()),
        sa.PrimaryKeyConstraint("id", "generated_at"),
    )
    op.create_index("ix_predictions_audit_model_id", "predictions_audit", ["model_id"])
    op.create_index("ix_predictions_audit_model_family", "predictions_audit", ["model_family"])
    op.create_index("ix_predictions_audit_asset", "predictions_audit", ["asset"])
    op.create_index("ix_predictions_audit_generated_at", "predictions_audit", ["generated_at"])

    # Convert to TimescaleDB hypertable partitioned by generated_at
    # (chunks of 7 days, fits FX 24/5 throughput easily)
    op.execute(
        "SELECT create_hypertable('predictions_audit', 'generated_at', "
        "chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE);"
    )

    # ---- bias_signals ----
    op.create_table(
        "bias_signals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("asset", sa.String(16), nullable=False),
        sa.Column("horizon_hours", sa.Integer(), nullable=False),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("probability", sa.Float(), nullable=False),
        sa.Column("credible_interval_low", sa.Float(), nullable=False),
        sa.Column("credible_interval_high", sa.Float(), nullable=False),
        sa.Column("contributing_predictions", ARRAY(UUID(as_uuid=True)), nullable=False),
        sa.Column("weights_snapshot", JSONB(), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("probability BETWEEN 0 AND 1", name="bias_signals_prob_range"),
        sa.CheckConstraint(
            "direction IN ('long','short','neutral')",
            name="bias_signals_direction_valid",
        ),
    )
    op.create_index("ix_bias_signals_asset", "bias_signals", ["asset"])
    op.create_index("ix_bias_signals_generated_at", "bias_signals", ["generated_at"])

    # NOTE: AGE graph creation deferred — requires ag_catalog schema privileges
    # (granted to postgres superuser only by default). Created out-of-band by the
    # postgres role; the migration just verifies the graph exists.
    op.execute(
        "DO $$ BEGIN "
        "  IF NOT EXISTS (SELECT 1 FROM ag_catalog.ag_graph WHERE name = 'ichor_graph') THEN "
        "    RAISE NOTICE 'ichor_graph not found — create manually as postgres user'; "
        "  END IF; "
        "EXCEPTION WHEN insufficient_privilege OR undefined_table THEN "
        "  RAISE NOTICE 'AGE catalog access skipped (privileges)'; "
        "END $$;"
    )


def downgrade() -> None:
    op.drop_table("bias_signals")
    # TimescaleDB chunks dropped on parent table drop
    op.drop_table("predictions_audit")
    op.drop_table("alerts")
    op.drop_table("briefings")
