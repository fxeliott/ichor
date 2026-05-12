"""pass3_addenda table — Phase D W116 (ADR-087).

Stores W116 post-mortem addenda — short directional reminders that the
nightly Penalized-Brier-Score evaluator decides should be injected into
the next Pass-3 (revision) prompt for a given regime.

Rate-limit policy (per researcher SOTA brief round-15) :
* MAX_ACTIVE per regime = 3 (hard cap)
* `importance` score = Brier-improvement attribution computed by the
  W116 PBS evaluator (higher = retain longer)
* Exponential decay half-life 30 d (kept as soft selection criterion,
  enforced query-side at read time)
* `status = 'active' | 'expired' | 'superseded'`
* `expires_at` is a hard cutoff (90 d TTL by default)

Append-only by convention (NOT trigger-enforced like audit_log) :
* W116 inserts new rows when the evaluator promotes a finding.
* Status transitions ('active' → 'expired' / 'superseded') happen via
  UPDATE on the status column ; this is fine because the historical
  audit lives in `auto_improvement_log` (loop_kind='post_mortem'), and
  the addendum body content (`content`) never changes — only its
  lifecycle field.

Schema :
* id              UUID PK
* regime          TEXT NOT NULL (matches ichor_brain regime set)
* asset           TEXT (nullable — some addenda are macro-only)
* content         TEXT NOT NULL (the addendum body for Pass-3)
* importance      DOUBLE PRECISION NOT NULL (Brier-improvement points)
* status          TEXT NOT NULL CHECK in 4-enum
* source_card_id  UUID nullable — points to session_card_audit if the
                                   addendum was derived from one card
* created_at      TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
* expires_at      TIMESTAMPTZ NOT NULL (hard cutoff)
* superseded_by   UUID nullable — self-referential FK (logical only,
                                   not enforced at DB)

Indexes :
* (regime, status, importance DESC) — query path for `select_active`
* (asset, regime) WHERE asset IS NOT NULL — per-asset filtering

Revision ID: 0044
Revises: 0043
Create Date: 2026-05-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "0044"
down_revision: str | None = "0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pass3_addenda",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("regime", sa.String(64), nullable=False),
        sa.Column("asset", sa.String(16), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("importance", sa.Float(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("source_card_id", PG_UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_by", PG_UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('active', 'expired', 'superseded', 'rejected')",
            name="ck_pass3_addenda_status",
        ),
        sa.CheckConstraint(
            "importance >= 0.0",
            name="ck_pass3_addenda_importance_nonneg",
        ),
        sa.CheckConstraint(
            "char_length(content) >= 8 AND char_length(content) <= 4096",
            name="ck_pass3_addenda_content_size",
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_pass3_addenda_expires_after_created",
        ),
    )
    # Hot query path : pick the top-K active addenda for a regime by
    # decayed importance. The `WHERE status='active'` filter is partial
    # so the index doesn't bloat with retired rows.
    op.create_index(
        "ix_pass3_addenda_regime_active_importance",
        "pass3_addenda",
        ["regime", sa.text("importance DESC")],
        postgresql_where=sa.text("status = 'active'"),
    )
    # Secondary index : per-asset filtering for addenda that bind to a
    # specific asset rather than a regime-wide context.
    op.create_index(
        "ix_pass3_addenda_asset_regime",
        "pass3_addenda",
        ["asset", "regime"],
        postgresql_where=sa.text("asset IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_pass3_addenda_asset_regime", table_name="pass3_addenda")
    op.drop_index("ix_pass3_addenda_regime_active_importance", table_name="pass3_addenda")
    op.drop_table("pass3_addenda")
