"""seed_reactive_learning_feature_flags — Session 02 socle audit (2026-06-17).

The four flags that gate Ichor's "vivant / réactif / apprend" behaviour live
ONLY as runtime rows in the Hetzner ``feature_flags`` table — invisible to a
reconstruct-from-repo and un-auditable from source (S02 architecture audit,
cross-axis risk #2). This migration documents them in versioned code and seeds
each at its fail-closed default (``enabled = false``), so a from-scratch rebuild
has a defined, safe state instead of an undefined flag.

The four flags :
  - ``streaming_refresh_enabled``             — réactif : 12-min intra-session
        targeted card regen when a strong new event lands (ADR-109).
  - ``scenario_invalidation_monitor_enabled`` — réactif : auto-invalidates a
        Pass-6 scenario + pushes when a hard condition breaches (ADR-106 Strand D).
  - ``phase_d_w115c_confluence_enabled``      — apprend : feeds the measured
        Vovk/Brier pocket skill back into Pass-3 (the learning act-loop, ADR-087).
  - ``conviction_calibrator_oos_enabled``     — apprend : OOS-gated conviction
        recalibration on the apex verdict (ADR-117/118/119).

SAFETY — NON-DESTRUCTIVE BY CONSTRUCTION : ``INSERT ... ON CONFLICT (key) DO
NOTHING``. If a flag already has a prod row (e.g. ``streaming_refresh_enabled``
flipped ON), this migration leaves it UNTOUCHED — it only seeds the fail-closed
default where no row exists. It NEVER turns a live feature off.

This documents flag EXISTENCE + intended default in the repo ; the live ON/OFF
state still lives in the DB by design (runtime flags). Capture the prod state in
a runbook after deploy (owner step — no prod access from the repo) :
``SELECT key, enabled, rollout_pct, updated_at FROM feature_flags WHERE key IN
('streaming_refresh_enabled', 'scenario_invalidation_monitor_enabled',
'phase_d_w115c_confluence_enabled', 'conviction_calibrator_oos_enabled') ;``

Reversible : ``downgrade()`` removes ONLY the rows still at the seeded
fail-closed default (``enabled = false``), so a flag an operator flipped ON
between upgrade and downgrade is preserved.

Voie D : pure DB seed, ZERO LLM call / feed / FRED series. A ``pg_dump`` of
``feature_flags`` is taken before ``alembic upgrade`` on Hetzner (KEYWORD
MIGRATION protocol) — though ON CONFLICT DO NOTHING makes this seed safe to
re-run.

ADR refs : ADR-109 (streaming), ADR-106 (invalidation), ADR-087 (Phase-D
learning), ADR-117/118/119 (OOS calibration), ADR-009 Voie D.

Revision ID: 0057
Revises: 0056
Create Date: 2026-06-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0057"
down_revision: str | None = "0056"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (key, description) — every flag seeded at enabled=false (fail-closed default).
# Keys are verified verbatim against the runtime callers
# (services/feature_flags.is_enabled call-sites), NOT invented.
_SEEDED_FLAGS: tuple[tuple[str, str], ...] = (
    (
        "streaming_refresh_enabled",
        "Réactif : 12-min intra-session targeted card regen on a strong new "
        "event (ADR-109). Fail-closed default seeded by migration 0057.",
    ),
    (
        "scenario_invalidation_monitor_enabled",
        "Réactif : auto-invalidates a Pass-6 scenario + pushes on a hard "
        "condition breach (ADR-106 Strand D). Fail-closed default seeded by 0057.",
    ),
    (
        "phase_d_w115c_confluence_enabled",
        "Apprend : feeds the measured Vovk/Brier pocket skill back into Pass-3 "
        "(learning act-loop, ADR-087). Fail-closed default seeded by 0057.",
    ),
    (
        "conviction_calibrator_oos_enabled",
        "Apprend : OOS-gated conviction recalibration on the apex verdict "
        "(ADR-117/118/119). Fail-closed default seeded by 0057.",
    ),
)


def upgrade() -> None:
    # ON CONFLICT DO NOTHING — seed the fail-closed default ONLY where the flag
    # has no row yet. NEVER overrides a prod row (a live-ON flag stays ON).
    for key, description in _SEEDED_FLAGS:
        op.execute(
            sa.text(
                "INSERT INTO feature_flags (key, enabled, description, created_by) "
                "VALUES (:key, false, :description, 'migration_0057') "
                "ON CONFLICT (key) DO NOTHING"
            ).bindparams(key=key, description=description)
        )


def downgrade() -> None:
    # Remove ONLY rows still at the seeded fail-closed default — preserve any
    # flag an operator flipped ON between upgrade and downgrade.
    for key, _description in _SEEDED_FLAGS:
        op.execute(
            sa.text("DELETE FROM feature_flags WHERE key = :key AND enabled = false").bindparams(
                key=key
            )
        )
