"""brier_aggregator_weights table — Phase D W115 (ADR-087).

Vovk-Zhdanov Aggregating Algorithm (JMLR 2009 vol.10) maintains a
weight distribution over `N` Brier-scoring experts (e.g. brier
optimizer v1, brier optimizer v2, equal-weight baseline, climatology
baseline) per `(asset, regime)` pocket. The AA's mathematical guarantee :

    Regret_T(AA) ≤ ln(N) / η = ln(N)   (constant in T, at η=1 the
                                         Brier-game mixability optimum)

This table holds ONE row per `(asset, regime, expert_kind,
pocket_version)`. Unlike the audit_log family, this table is MUTABLE
by design — `update()` rewrites weights every nightly step. The audit
trail of WHO updated the weights and WHY lives in
`auto_improvement_log` (table 0042, append-only).

`pocket_version` bumps on W114 tier-2 drift sequester : the production
pocket is frozen at the current version, a challenger spawns at
version+1, both update in parallel until W114 decides which wins (per
ADR-087 cross-cutting §"Concurrent loops").

Schema field map :
- id              UUID PK (auto-generated)
- asset           TEXT NOT NULL (e.g. 'EUR_USD', 'NAS100_USD' from
                                  ADR-083 D1 6-card universe)
- regime          TEXT NOT NULL (e.g. 'usd_complacency', 'goldilocks',
                                  'haven_bid', etc.)
- expert_kind     TEXT NOT NULL (free text — no CHECK, new experts can
                                  be added without migration ; the AA
                                  is agnostic to expert identity)
- weight          DOUBLE PRECISION NOT NULL CHECK 0 ≤ weight ≤ 1
- n_observations  INTEGER NOT NULL DEFAULT 0 (samples used for this
                                  weight — feeds the regret bound check)
- cumulative_loss DOUBLE PRECISION NOT NULL DEFAULT 0.0 (Σ Brier loss
                                  this expert has incurred ; used for
                                  audit + post-W116 PBS extension)
- pocket_version  INTEGER NOT NULL DEFAULT 1 (W114 freeze-spawn atom)
- updated_at      TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
- UNIQUE          (asset, regime, expert_kind, pocket_version)

Revision ID: 0043
Revises: 0042
Create Date: 2026-05-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "0043"
down_revision: str | None = "0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "brier_aggregator_weights",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("asset", sa.String(16), nullable=False),
        sa.Column("regime", sa.String(64), nullable=False),
        sa.Column("expert_kind", sa.String(64), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column(
            "n_observations",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "cumulative_loss",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.0"),
        ),
        sa.Column(
            "pocket_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.CheckConstraint(
            "weight >= 0.0 AND weight <= 1.0",
            name="ck_brier_agg_weight_unit_interval",
        ),
        sa.CheckConstraint(
            "n_observations >= 0",
            name="ck_brier_agg_n_observations_nonneg",
        ),
        sa.CheckConstraint(
            "cumulative_loss >= 0.0",
            name="ck_brier_agg_cumulative_loss_nonneg",
        ),
        sa.CheckConstraint(
            "pocket_version >= 1",
            name="ck_brier_agg_pocket_version_positive",
        ),
        sa.UniqueConstraint(
            "asset",
            "regime",
            "expert_kind",
            "pocket_version",
            name="uq_brier_agg_pocket_expert",
        ),
    )
    # Fast read for the confluence_engine (W115b) : look up all expert
    # weights for a (asset, regime, pocket_version) tuple in one query.
    op.create_index(
        "ix_brier_agg_pocket",
        "brier_aggregator_weights",
        ["asset", "regime", "pocket_version"],
    )


def downgrade() -> None:
    op.drop_index("ix_brier_agg_pocket", table_name="brier_aggregator_weights")
    op.drop_table("brier_aggregator_weights")
