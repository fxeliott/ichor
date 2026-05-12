"""scenarios_persistence — Pass-6 scenario_decompose persistence (W105a, ADR-085).

Adds the two persistence surfaces ratified by ADR-085 :

1. `session_card_audit.scenarios JSONB NOT NULL DEFAULT '[]'::jsonb` —
   per-card 7-bucket decomposition emitted by Pass-6 (`ScenariosPass`).
   Shape per ADR-085 :
       [{"label": "crash_flush", "p": 0.02,
         "magnitude_pips": [-300, -120], "mechanism": "..."},
        ... 7 entries total, sum(p) == 1.0, all p in [0, 0.95]]

2. `session_card_audit.realized_scenario_bucket TEXT NULL` — populated
   by the W105g/W108 realized-outcome reconciler. One of the 7 canonical
   labels (`crash_flush`, `strong_bear`, `mild_bear`, `base`,
   `mild_bull`, `strong_bull`, `melt_up`) or NULL when the session is
   still open. CHECK constraint enforces the label whitelist at DB
   level (defence-in-depth alongside the Pydantic enum at
   `apps/api/src/ichor_api/services/scenarios.py:BUCKET_LABELS`).

3. `scenario_calibration_bins` — new table holding per
   (asset, session_type) z-score → pip-threshold calibration computed
   weekly by W105b `services/scenario_calibration.py`. Append-only by
   design (PK includes `computed_at`) so the consumer can pick the
   most recent row deterministically and the history stays auditable.

Boundary recap (ADR-017) : nothing here emits a trade signal. The
`scenarios` column stores realized-outcome-bucket probabilities ;
the `realized_scenario_bucket` column stores the bucket the session
actually ended in (read from `polygon_intraday`, not a prediction).

Revision ID: 0039
Revises: 0038
Create Date: 2026-05-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# The 7 canonical bucket labels — mirror of
# `apps/api/src/ichor_api/services/scenarios.py:BUCKET_LABELS`. Pinned
# here at migration level so the DB rejects a typo regardless of
# whether the Pydantic enum drifted. ADR-081 CI guard
# `test_pass6_bucket_labels_exactly_seven_canonical` enforces the
# code-side tuple ; this CHECK enforces the DB-side string.
_CANONICAL_BUCKETS_SQL = (
    "'crash_flush','strong_bear','mild_bear','base','mild_bull','strong_bull','melt_up'"
)


def upgrade() -> None:
    # 1. Extend session_card_audit with scenarios + realized_scenario_bucket.
    op.add_column(
        "session_card_audit",
        sa.Column(
            "scenarios",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "session_card_audit",
        sa.Column(
            "realized_scenario_bucket",
            sa.Text(),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_session_card_audit_realized_scenario_bucket_canonical",
        "session_card_audit",
        (
            "realized_scenario_bucket IS NULL "
            f"OR realized_scenario_bucket IN ({_CANONICAL_BUCKETS_SQL})"
        ),
    )

    # 2. Create the per-asset/session calibration bins table.
    op.create_table(
        "scenario_calibration_bins",
        sa.Column("asset", sa.Text(), nullable=False),
        sa.Column("session_type", sa.Text(), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("bins_z_thresholds", JSONB, nullable=False),
        sa.Column("bins_pip_thresholds", JSONB, nullable=False),
        sa.Column("sample_n", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint(
            "asset",
            "session_type",
            "computed_at",
            name="pk_scenario_calibration_bins",
        ),
        sa.CheckConstraint(
            "sample_n >= 0",
            name="ck_scenario_calibration_bins_sample_n_nonneg",
        ),
        sa.CheckConstraint(
            ("session_type IN ('pre_londres','pre_ny','ny_mid','ny_close','event_driven')"),
            name="ck_scenario_calibration_bins_session_type",
        ),
    )
    # Reverse-lookup index : "most recent calibration for this pair" is
    # the dominant access pattern from Pass-6 prompt builder + reconciler.
    op.create_index(
        "ix_scenario_calibration_bins_latest",
        "scenario_calibration_bins",
        ["asset", "session_type", sa.text("computed_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scenario_calibration_bins_latest",
        table_name="scenario_calibration_bins",
    )
    op.drop_table("scenario_calibration_bins")
    op.drop_constraint(
        "ck_session_card_audit_realized_scenario_bucket_canonical",
        "session_card_audit",
        type_="check",
    )
    op.drop_column("session_card_audit", "realized_scenario_bucket")
    op.drop_column("session_card_audit", "scenarios")
