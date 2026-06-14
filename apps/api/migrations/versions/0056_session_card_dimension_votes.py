"""session_card_dimension_votes — Session 06 Chantier C (C-3b wiring).

Adds ONE NULLABLE JSONB column to ``session_card_audit`` that freezes the
Chantier-C ``DimensionVote`` layers (COT positioning today ; rates / volume /
geopolitics next) at card generation, so the apex ``SessionVerdict`` conviction
fusion (``services.conviction_fusion.fuse_conviction``) can fold them in
REPRODUCIBLY at read-time — the exact same write-time-snapshot rationale as the
0055 synthesis snapshots (``/v1/verdict`` is polled every 60 s ; re-fetching COT
live per poll would drift the apex under the user and diverge from the card the
Chantier-A benchmark replays).

  - ``dimension_votes`` — list of serialised ``DimensionVote`` dicts, exactly
        ``services.dimension_vote.votes_to_snapshot(votes)``. Each entry :
        {"provenance": str, "direction_hint": "up"|"down"|"neutral",
         "strength": float, "freshness": float, "honest_absence": bool,
         "directional": bool}.

DELIBERATE TRI-STATE — NULLABLE, NO server_default, NO backfill (mirror of the
0050 ``degraded_inputs`` / 0055 synthesis-snapshot honesty decision) :

  - NULL  = "dimension votes not captured at this card's generation" : every
            pre-0056 card AND any card generated while the
            ``cot_dimension_vote_enabled`` feature flag is OFF AND any card
            whose best-effort capture failed. ``votes_from_snapshot(None)``
            returns ``()`` → the fuser is byte-identical to the legacy path
            (``votes=()`` — C-2a). A ``'[]'::jsonb`` backfill would falsely
            assert "votes were computed and all abstained".
  - [...] = "captured at generation" (flag ON).

On Postgres this is a metadata-only catalog change (instant, no table rewrite,
no long lock) even on the ``session_card_audit`` TimescaleDB hypertable.

Reversible : ``downgrade()`` drops the column ; combined with ``git revert`` +
``alembic downgrade 0055`` the change fully reverses. A ``pg_dump`` of
``session_card_audit`` is taken before ``alembic upgrade`` on Hetzner
(KEYWORD MIGRATION protocol).

DEPLOY SEQUENCING (mandatory) : this migration MUST be applied to prod BEFORE
the C-3b code is deployed. ``build_session_verdict`` loads ALL columns of
``session_card_audit`` (no projection) ; deploying the ORM column before the DB
column exists would 500 every verdict read. Apply 0056 → deploy code → THEN flip
the flag.

Voie D respect : pure-Python deterministic persistence of an
already-computable runtime structure (COT positioning the LLM already saw).
ZERO LLM call, ZERO new feed, ZERO new FRED series.

ADR refs : ADR-120 (DimensionVote contract), ADR-103 (honest absence == 0),
ADR-017 (votes carry bias/probability magnitude, never an order ; direction
stays bucket-derived), ADR-022 (cap-95 honoured by the fuser), ADR-009 Voie D.

Revision ID: 0056
Revises: 0055
Create Date: 2026-06-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0056"
down_revision: str | None = "0055"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMN = "dimension_votes"


def upgrade() -> None:
    # NULLABLE, NO server_default, NO backfill — NULL is the honest "votes not
    # captured at generation" state for every pre-existing card ; only cards
    # generated post-deploy with the flag ON carry the frozen votes.
    op.add_column("session_card_audit", sa.Column(_COLUMN, JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("session_card_audit", _COLUMN)
