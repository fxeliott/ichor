"""auto_improvement_log table + immutable trigger — Phase D W113 (ADR-087).

Cross-cutting table backing all 4 Phase D auto-improvement loops :

  - W115 brier_aggregator  — Vovk-Zhdanov AA weight updates (per-asset,
                              per-regime pocket promotions/freezes)
  - W114 adwin_drift       — ADWIN drift detector tier-1/2/3 events
  - W116 post_mortem       — Penalized Brier Score (Ahmadian 2025)
                              attribution + addendum lineage
  - W117 meta_prompt       — DSPy GEPA Pareto-front candidates,
                              promotion/rejection + ancestor lineage

Every row is an append-only audit record of one auto-improvement step.
ADR-029-class immutability : `UPDATE` and `DELETE` raise `EXCEPTION`
unless the sanctioned `ichor.audit_purge_mode='on'` GUC is set in
the same transaction (matches `audit_log` and `tool_call_audit`).

Schema rationale :
- `loop_kind`            — partition the table along the 4 loops ;
                            CHECK constraint freezes the enum.
- `trigger_event`        — free-text "what fired this loop"
                            (cron name, ADWIN detector name, manual
                            CLI invocation).
- `asset`/`regime`       — nullable (W117 meta-prompt is asset-agnostic).
- `input_summary` JSONB  — frozen snapshot of relevant inputs (n_obs,
                            feature vector hash, model_version, etc.).
- `output_summary` JSONB — the auto-improvement DECISION : new weights,
                            new prompt text, new pocket id, etc.
- `metric_before`/`_after` — before/after the chosen metric. Stored
                              independently of `metric_name` so future
                              metric additions don't need column adds.
- `metric_name`          — 'brier_multiclass' | 'pbs' | 'log_loss' |
                            'adwin_pvalue' | etc. (free text — no
                            CHECK ; W116 will add 'pbs' later).
- `decision`             — 'adopted' | 'rejected' | 'pending_review' |
                            'sequestered' (Bridgewater-style).
- `disposition`          — secondary classification : 'keep' | 'tweak' |
                            'sequester' | 'retire'. Optional.
- `executor_user`        — Postgres user that authored the row (defaults
                            to `current_user`).
- `model_version`        — SR 11-7-class lineage tag (e.g. version hash).
- `parent_id`            — self-referential FK for W117 GEPA Pareto-front
                            ancestry. NULL for cold-start entries.
- `ran_at`               — TimescaleDB partitioning column ;
                            `clock_timestamp()` default for per-row
                            precision (audit standard 2026).

Indexes :
- `(loop_kind, ran_at DESC)` — recent-N-per-loop introspection.
- `(asset, regime)` partial — pocket-level lineage queries.
- `input_summary` GIN     — searchable JSONB (e.g. find all rows where
                              `input_summary.feature == 'vpin'`).

Phase D ADR ref : ADR-087 §"Cross-cutting".

Revision ID: 0042
Revises: 0041
Create Date: 2026-05-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "0042"
down_revision: str | None = "0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION auto_improvement_log_block_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    purge_mode text;
BEGIN
    -- Mirrors audit_log_block_mutation (migration 0028) and
    -- tool_call_audit_block_mutation (migration 0038). The sanctioned
    -- purge path uses the `ichor.audit_purge_mode` GUC set within the
    -- same transaction to allow nightly retention rotation.
    purge_mode := COALESCE(current_setting('ichor.audit_purge_mode', true), 'off');
    IF purge_mode = 'on' THEN
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END IF;

    RAISE EXCEPTION
      'auto_improvement_log is append-only — UPDATE/DELETE are reserved for the sanctioned purge path (set `ichor.audit_purge_mode=on` in the same transaction). HINT: see ADR-087 + ADR-081 invariant guard for the doctrine.'
      USING ERRCODE = 'insufficient_privilege';
END;
$$;
"""


def upgrade() -> None:
    op.create_table(
        "auto_improvement_log",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "ran_at",
            sa.DateTime(timezone=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.Column("loop_kind", sa.String(32), nullable=False),
        sa.Column("trigger_event", sa.Text(), nullable=False),
        sa.Column("asset", sa.String(16), nullable=True),
        sa.Column("regime", sa.String(32), nullable=True),
        sa.Column("input_summary", JSONB(), nullable=False),
        sa.Column("output_summary", JSONB(), nullable=False),
        sa.Column("metric_before", sa.Float(), nullable=True),
        sa.Column("metric_after", sa.Float(), nullable=True),
        sa.Column("metric_name", sa.String(32), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("disposition", sa.String(32), nullable=True),
        sa.Column(
            "executor_user",
            sa.Text(),
            nullable=False,
            server_default=sa.text("current_user"),
        ),
        sa.Column("model_version", sa.Text(), nullable=True),
        # NOTE: self-referential FK NOT enforced at the DB level — the
        # parent may live in a different Timescale chunk and the FK
        # checker won't follow chunk boundaries reliably. The
        # application layer guarantees referential integrity by always
        # writing the parent row first (W117 GEPA Pareto-front
        # producer).
        sa.Column("parent_id", PG_UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint(
            "loop_kind IN ('brier_aggregator', 'adwin_drift', 'post_mortem', 'meta_prompt')",
            name="ck_auto_improvement_log_loop_kind",
        ),
        sa.CheckConstraint(
            "decision IN ('adopted', 'rejected', 'pending_review', 'sequestered')",
            name="ck_auto_improvement_log_decision",
        ),
        sa.CheckConstraint(
            "disposition IS NULL OR disposition IN ('keep', 'tweak', 'sequester', 'retire')",
            name="ck_auto_improvement_log_disposition",
        ),
    )
    op.create_index(
        "ix_auto_imp_loop_kind_ran_at",
        "auto_improvement_log",
        ["loop_kind", sa.text("ran_at DESC")],
    )
    op.create_index(
        "ix_auto_imp_asset_regime",
        "auto_improvement_log",
        ["asset", "regime"],
        postgresql_where=sa.text("asset IS NOT NULL"),
    )
    op.create_index(
        "ix_auto_imp_input_summary_gin",
        "auto_improvement_log",
        ["input_summary"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_auto_imp_parent_id",
        "auto_improvement_log",
        ["parent_id"],
        postgresql_where=sa.text("parent_id IS NOT NULL"),
    )
    # TimescaleDB hypertable on ran_at, 30-day chunks. Auto-improvement
    # log volume is low (a few rows per loop per day, peak ~500/day
    # under W117 GEPA optimization runs). 30-day chunks keep nightly
    # introspection queries fast.
    op.execute(
        "SELECT create_hypertable('auto_improvement_log', 'ran_at', "
        "chunk_time_interval => INTERVAL '30 days', if_not_exists => TRUE);"
    )
    # Immutable trigger — mirrors audit_log + tool_call_audit pattern.
    op.execute(_TRIGGER_FUNCTION)
    op.execute(
        """
        CREATE TRIGGER auto_improvement_log_immutable_trigger
        BEFORE UPDATE OR DELETE ON auto_improvement_log
        FOR EACH ROW
        EXECUTE FUNCTION auto_improvement_log_block_mutation();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS auto_improvement_log_immutable_trigger ON auto_improvement_log;"
    )
    op.execute("DROP FUNCTION IF EXISTS auto_improvement_log_block_mutation();")
    op.drop_index("ix_auto_imp_parent_id", table_name="auto_improvement_log")
    op.drop_index("ix_auto_imp_input_summary_gin", table_name="auto_improvement_log")
    op.drop_index("ix_auto_imp_asset_regime", table_name="auto_improvement_log")
    op.drop_index("ix_auto_imp_loop_kind_ran_at", table_name="auto_improvement_log")
    op.drop_table("auto_improvement_log")
