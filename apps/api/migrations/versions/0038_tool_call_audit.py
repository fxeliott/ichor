"""tool_call_audit table + immutable trigger — Capability 5 PRE-2 (W73+).

ADR-071 PRE-2: append-only record of every Capability 5 client-tool
invocation (`query_db`, `calc`, `rag_historical`). Mirrors the
`audit_log` immutable trigger pattern (migration 0028) — UPDATE +
DELETE blocked unless `ichor.audit_purge_mode=on` is set in the
same transaction.

Schema fields per ADR-071 § Pre-requisites:
- `id UUID PK`
- `ran_at TIMESTAMPTZ` (also the Timescale partitioning column)
- `agent_kind`     — which 4-pass agent invoked the tool (Pass 1..5)
- `pass_index`     — 1..5 to support Pass 5 counterfactual scope
- `tool_name`      — MCP-qualified name (e.g. `mcp__ichor_db__query_db`)
- `tool_input`     — JSONB of the args sent to the tool handler
- `tool_output`    — JSONB of the result (or `{"error": ...}` on fail)
- `duration_ms`    — wall-time the tool handler took
- `error`          — text. NULL on success, exception class + message
                     on failure
- `session_card_id` — FK to session_card_audit when the call was made
                     inside a 4-pass run; NULL for ad-hoc CLI calls

The table is created BEFORE Capability 5 wiring lands so the
audit-trail-first invariant (ADR-029 EU AI Act §50 + AMF DOC-2008-23)
is enforced by construction. Until the wiring ships, the table is
empty — but its existence prevents any "we'll add audit later"
regression.

Revision ID: 0038
Revises: 0037
Create Date: 2026-05-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION tool_call_audit_block_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    purge_mode text;
BEGIN
    -- Mirrors audit_log_block_mutation (migration 0028).
    purge_mode := COALESCE(current_setting('ichor.audit_purge_mode', true), 'off');
    IF purge_mode = 'on' THEN
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END IF;

    RAISE EXCEPTION
      'tool_call_audit is append-only — UPDATE/DELETE are reserved for the sanctioned purge path (set `ichor.audit_purge_mode=on` in the same transaction). HINT: see services/audit_log.purge_older_than for the canonical pattern.'
      USING ERRCODE = 'insufficient_privilege';
END;
$$;
"""


def upgrade() -> None:
    op.create_table(
        "tool_call_audit",
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
            server_default=sa.text("now()"),
        ),
        sa.Column("agent_kind", sa.String(64), nullable=False),
        sa.Column("pass_index", sa.SmallInteger(), nullable=False),
        sa.Column("tool_name", sa.String(128), nullable=False),
        sa.Column("tool_input", JSONB(), nullable=False),
        sa.Column("tool_output", JSONB(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("session_card_id", PG_UUID(as_uuid=True), nullable=True),
        # CHECK constraints to catch bad data at insert time
        sa.CheckConstraint("pass_index BETWEEN 1 AND 5", name="ck_tool_call_audit_pass_index"),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_tool_call_audit_duration",
        ),
    )
    op.create_index(
        "ix_tool_call_audit_ran_at",
        "tool_call_audit",
        ["ran_at"],
    )
    op.create_index(
        "ix_tool_call_audit_agent_kind_ran_at",
        "tool_call_audit",
        ["agent_kind", "ran_at"],
    )
    op.create_index(
        "ix_tool_call_audit_tool_name_ran_at",
        "tool_call_audit",
        ["tool_name", "ran_at"],
    )
    op.create_index(
        "ix_tool_call_audit_session_card_id",
        "tool_call_audit",
        ["session_card_id"],
        postgresql_where=sa.text("session_card_id IS NOT NULL"),
    )
    # TimescaleDB hypertable on ran_at, 30-day chunks (relatively low
    # cadence: a few k tool calls per day at peak; 30-day chunks keep
    # query plans fast for the typical "what did the orchestrator do
    # last week" introspection).
    op.execute(
        "SELECT create_hypertable('tool_call_audit', 'ran_at', "
        "chunk_time_interval => INTERVAL '30 days', if_not_exists => TRUE);"
    )
    # Immutable trigger
    op.execute(_TRIGGER_FUNCTION)
    op.execute(
        """
        CREATE TRIGGER tool_call_audit_immutable_trigger
        BEFORE UPDATE OR DELETE ON tool_call_audit
        FOR EACH ROW
        EXECUTE FUNCTION tool_call_audit_block_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS tool_call_audit_immutable_trigger ON tool_call_audit;")
    op.execute("DROP FUNCTION IF EXISTS tool_call_audit_block_mutation();")
    op.drop_index("ix_tool_call_audit_session_card_id", table_name="tool_call_audit")
    op.drop_index("ix_tool_call_audit_tool_name_ran_at", table_name="tool_call_audit")
    op.drop_index("ix_tool_call_audit_agent_kind_ran_at", table_name="tool_call_audit")
    op.drop_index("ix_tool_call_audit_ran_at", table_name="tool_call_audit")
    op.drop_table("tool_call_audit")
