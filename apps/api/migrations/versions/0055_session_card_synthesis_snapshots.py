"""session_card_synthesis_snapshots — Session 04 (« kill the 50/50 »).

Adds three NULLABLE JSONB columns to ``session_card_audit`` that freeze the
synthesis-layer reads at card generation so the apex ``SessionVerdict``
conviction fusion (``services.conviction_fusion.fuse_conviction``) is
REPRODUCIBLE at read-time :

  - ``confluence_snapshot`` — confluence_engine dominant direction + scores.
        {"dominant_direction": "long"|"short"|"neutral",
         "score_long": float, "score_short": float, "confluence_count": int}
  - ``theme_snapshot``      — dominant market theme (GLOBAL, not per-asset).
        {"present": bool, "top_theme": str|null, "strength": float|null}
  - ``dollar_snapshot``     — cross-asset dollar-coherence consensus.
        {"consensus": "usd_up"|"usd_down"|"mixed"|"neutral",
         "consensus_strength": float}

WHY a write-time snapshot (not a read-time recompute) : ``/v1/verdict`` is
polled every 60 s by the frontend. Recomputing the 12-factor confluence, the
theme classifier (6 heterogeneous DB inputs) and the cross-asset dollar lens
on every poll × 5 assets would be both heavy AND non-reproducible (the apex
conviction would drift under the user between polls). Freezing the read at
generation makes the fused apex conviction deterministic from the persisted
card — the same temporal-honesty argument as 0050 ``degraded_inputs``.

DELIBERATE TRI-STATE — NULLABLE, NO server_default, NO backfill (mirror of the
0050 ``degraded_inputs`` honesty decision) :

  - NULL  = "synthesis not captured at this card's generation". The honest
            state of every pre-0055 card AND any card whose best-effort capture
            failed. The verdict fuser then degrades to the bucket-only
            conviction (the GRADED dead-zone still applies). A ``'{}'::jsonb``
            backfill would falsely assert "synthesis was computed and neutral".
  - {...} = "captured at generation".

On Postgres this is a metadata-only catalog change (instant, no table rewrite,
no long lock) even on the ``session_card_audit`` TimescaleDB hypertable.

Reversible : ``downgrade()`` drops the three columns ; combined with
``git revert`` + ``alembic downgrade 0054`` the change fully reverses. A
``pg_dump`` of ``session_card_audit`` is taken before ``alembic upgrade`` on
Hetzner (KEYWORD MIGRATION protocol).

Voie D respect : pure-Python deterministic persistence of already-computed
runtime structures. ZERO LLM call, ZERO new feed, ZERO new FRED series.

ADR refs : ADR-017 (snapshots carry bias/probability context, never an order),
ADR-022 (cap-95 honoured by the fuser), ADR-009 Voie D.

Revision ID: 0055
Revises: 0054
Create Date: 2026-06-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0055"
down_revision: str | None = "0054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Order matters only for downgrade symmetry ; add then drop in reverse.
_COLUMNS: tuple[str, ...] = (
    "confluence_snapshot",
    "theme_snapshot",
    "dollar_snapshot",
)


def upgrade() -> None:
    # NULLABLE, NO server_default, NO backfill — NULL is the honest "synthesis
    # not captured at generation" state for every pre-existing card ; only
    # cards generated post-deploy carry the frozen snapshots.
    for name in _COLUMNS:
        op.add_column("session_card_audit", sa.Column(name, JSONB, nullable=True))


def downgrade() -> None:
    for name in reversed(_COLUMNS):
        op.drop_column("session_card_audit", name)
