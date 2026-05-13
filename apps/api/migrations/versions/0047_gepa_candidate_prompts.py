"""gepa_candidate_prompts table + immutable trigger — Phase D W117b sub-wave .b (ADR-091).

Persistence layer for the GEPA optimizer (DSPy 3.2 Voie-D-bound)
candidate prompts. One row per (asset, regime, session_type, pass_kind,
generation, candidate). Append-only on insert ; the `status` column
is the only mutable surface, gated by the W117b.g adoption admin
endpoint via the sanctioned `ichor.audit_purge_mode='on'` GUC bypass
(matches `auto_improvement_log` migration 0042 + `audit_log` migration
0028 + `tool_call_audit` migration 0038).

Schema rationale (ADR-091 §"Invariant 6") :

  - `id UUID PK DEFAULT gen_random_uuid()` — surrogate primary key
    for the adoption endpoint URL surface.
  - `(pocket_asset, pocket_regime, pocket_session_type)` — Vovk
    pocket coordinates ; populated from the W115c PocketSkill seed.
    NULL on the asset/regime/session for non-pocket-bound 4-pass
    system-prompt candidates (e.g. Pass-1 regime classifier).
  - `pass_kind` — which 4-pass step the candidate prompt targets.
    CHECK pins the 4 canonical values.
  - `generation` INT — 0 = seed (cold-start), 1+ = mutations.
  - `prompt_text TEXT` — the candidate prompt itself. CHECK on size
    (8..32768 chars) catches both empty payloads and pathological
    GEPA mutations that exceed the LLM context budget.
  - `fitness_score NUMERIC(8,5)` — the round-32 HARD-ZERO fitness
    (penalty form per ADR-091 amended §Invariant 2). NULL on
    pre-evaluation rows.
  - `adr017_violations INT` — count from
    `services.adr017_filter.count_violations(prompt_text)`. ANY
    positive value MUST coincide with `fitness_score = -inf` ; the
    `status='rejected'` path is the only legal landing for a
    candidate with violations. Sanity-checked by the round-32
    ADR-091 invariant guard (will land in W117b.f).
  - `status` enum — `candidate` / `adopted` / `rejected` / `archived`
    pinned by CHECK. Mutation flow : `candidate` → `adopted` (one
    direction only ; rollback is `git revert` of the orchestrator
    config, NOT a status downgrade).
  - `notes TEXT` — adoption justification (Eliot-approved 2026-XX-XX
    after backtesting).
  - `gepa_run_id UUID` — groups candidates from the same optimization
    run (one cron fire = one UUID). Pre-allocated client-side so the
    run_id appears in the audit_log row written by the CLI gate.
  - UNIQUE constraint on `(pocket_asset, pocket_regime,
    pocket_session_type, pass_kind, generation, gepa_run_id)` — one
    candidate per pocket per generation per run.

Indexes :
  - `(gepa_run_id, fitness_score DESC NULLS LAST)` for "show me the
    top-K candidates from this run" leaderboard queries.
  - `(pocket_asset, pocket_regime, pocket_session_type, status)`
    partial WHERE status='adopted' — for the orchestrator's
    startup-time "load adopted prompts per pocket" query.
  - `(status, generated_at DESC)` for the admin endpoint's
    "pending candidates awaiting Eliot ratification" view.

NOT a TimescaleDB hypertable. Expected lifetime row count :
~6 pockets × 7 generations × 12 monthly runs × 5 candidates/gen
= ~2,500 rows total over 5 years. Trivial — Postgres btree handles.

ADR refs : ADR-091 (W117b GEPA), ADR-087 (Phase D loops), ADR-009
(Voie D — every row encodes a prompt that will be consumed by
`call_agent_task_async`, NEVER the Anthropic API).

Revision ID: 0047
Revises: 0046
Create Date: 2026-05-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "0047"
down_revision: str | None = "0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Trigger function — mirrors `auto_improvement_log_block_mutation`
# (migration 0042) almost verbatim, but ALSO permits UPDATE on rows
# where only `status` and `notes` columns change. This is the W117b.g
# adoption endpoint's narrow exception (Eliot manually flips
# `candidate → adopted`).
_TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION gepa_candidate_prompts_block_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    purge_mode text;
BEGIN
    -- Sanctioned-purge bypass (mirrors audit_log + tool_call_audit +
    -- auto_improvement_log). Set `ichor.audit_purge_mode='on'` in
    -- the same transaction to authorise UPDATE/DELETE — used by the
    -- W117b.g adoption admin endpoint AND nightly retention rotation.
    purge_mode := COALESCE(current_setting('ichor.audit_purge_mode', true), 'off');
    IF purge_mode = 'on' THEN
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        ELSE
            RETURN NEW;
        END IF;
    END IF;

    RAISE EXCEPTION
      'gepa_candidate_prompts is append-only — UPDATE/DELETE are reserved for the W117b.g adoption admin endpoint and the sanctioned purge path (set `ichor.audit_purge_mode=on` in the same transaction). HINT: see ADR-091 + ADR-081 invariant guard for the doctrine.'
      USING ERRCODE = 'insufficient_privilege';
END;
$$;
"""


def upgrade() -> None:
    op.create_table(
        "gepa_candidate_prompts",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.Column("gepa_run_id", PG_UUID(as_uuid=True), nullable=False),
        # Pocket coordinates — NULLABLE for non-pocket-bound system-prompt
        # candidates (Pass-1 regime classifier is asset-agnostic).
        sa.Column("pocket_asset", sa.String(16), nullable=True),
        sa.Column("pocket_regime", sa.String(32), nullable=True),
        sa.Column("pocket_session_type", sa.String(16), nullable=True),
        sa.Column("pass_kind", sa.String(16), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("fitness_score", sa.Numeric(8, 5), nullable=True),
        sa.Column(
            "adr017_violations",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'candidate'"),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "pass_kind IN ('regime', 'asset', 'stress', 'invalidation')",
            name="ck_gepa_candidate_pass_kind",
        ),
        sa.CheckConstraint(
            "status IN ('candidate', 'adopted', 'rejected', 'archived')",
            name="ck_gepa_candidate_status",
        ),
        sa.CheckConstraint(
            "generation >= 0",
            name="ck_gepa_candidate_generation_nonneg",
        ),
        sa.CheckConstraint(
            "char_length(prompt_text) >= 8 AND char_length(prompt_text) <= 32768",
            name="ck_gepa_candidate_prompt_size",
        ),
        sa.CheckConstraint(
            "adr017_violations >= 0",
            name="ck_gepa_candidate_adr017_violations_nonneg",
        ),
        # The hard-zero contract : a candidate with any ADR-017
        # violation MUST land as 'rejected' — never 'candidate' or
        # 'adopted'. Enforced at the DB level so neither the optimizer
        # nor the admin endpoint can accidentally promote a tainted
        # candidate.
        sa.CheckConstraint(
            "adr017_violations = 0 OR status = 'rejected'",
            name="ck_gepa_candidate_adr017_hard_zero",
        ),
        sa.UniqueConstraint(
            "pocket_asset",
            "pocket_regime",
            "pocket_session_type",
            "pass_kind",
            "generation",
            "gepa_run_id",
            name="uq_gepa_candidate_pocket_generation_run",
        ),
    )
    op.create_index(
        "ix_gepa_candidate_run_fitness",
        "gepa_candidate_prompts",
        ["gepa_run_id", sa.text("fitness_score DESC NULLS LAST")],
    )
    op.create_index(
        "ix_gepa_candidate_adopted_pocket",
        "gepa_candidate_prompts",
        ["pocket_asset", "pocket_regime", "pocket_session_type"],
        postgresql_where=sa.text("status = 'adopted'"),
    )
    op.create_index(
        "ix_gepa_candidate_status_generated_at",
        "gepa_candidate_prompts",
        ["status", sa.text("generated_at DESC")],
    )
    op.execute(_TRIGGER_FUNCTION)
    op.execute(
        """
        CREATE TRIGGER gepa_candidate_prompts_immutable_trigger
        BEFORE UPDATE OR DELETE ON gepa_candidate_prompts
        FOR EACH ROW
        EXECUTE FUNCTION gepa_candidate_prompts_block_mutation();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS gepa_candidate_prompts_immutable_trigger ON gepa_candidate_prompts;"
    )
    op.execute("DROP FUNCTION IF EXISTS gepa_candidate_prompts_block_mutation();")
    op.drop_index("ix_gepa_candidate_status_generated_at", table_name="gepa_candidate_prompts")
    op.drop_index("ix_gepa_candidate_adopted_pocket", table_name="gepa_candidate_prompts")
    op.drop_index("ix_gepa_candidate_run_fitness", table_name="gepa_candidate_prompts")
    op.drop_table("gepa_candidate_prompts")
