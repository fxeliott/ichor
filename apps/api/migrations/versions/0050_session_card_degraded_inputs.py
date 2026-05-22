"""session_card_degraded_inputs — ADR-104 (ADR-099 §T3.2) end-user persist.

Adds `session_card_audit.degraded_inputs JSONB NULL` — the ADR-103 runtime
FRED-liveness degraded-input manifest (`DataPool.degraded_inputs`), frozen
at card generation so the end-user `/briefing` surface (r96) reflects the
data health of the card the user is *actually reading*, not a drifting
live recompute (the temporal-honesty argument in ADR-104 §Context).

Shape (mirror of `DegradedInputOut`, the schemas.py SSOT) :

    [
      {
        "series_id": "MYAGM1CNM189N",
        "status": "stale",            # "stale" | "absent" — never "fresh"
        "latest_date": "2019-08-01",  # ISO date | null
        "age_days": 2481,             # int | null
        "max_age_days": 60,
        "impacted": "AUD composite — China M1 credit-impulse driver"
      },
      ... 0-N entries
    ]

DELIBERATE TRI-STATE — diverges on purpose from the 0049 `key_levels` /
0039 `scenarios` `NOT NULL DEFAULT '[]'::jsonb` pattern. This divergence
IS the core honesty decision of ADR-104 :

  - NULL  = "FRED-liveness was NOT tracked at this card's generation".
            The honest state of every pre-0050 card (the tracking did
            not exist when it was generated). A `'[]'::jsonb` backfill
            would falsely assert "all critical anchors were fresh" for
            cards that were never audited — the exact silent-skip
            dishonesty ADR-103 exists to kill. NULL must mean *unknown*,
            never *clean*.
  - []    = "tracked at generation, all critical FRED anchors fresh".
  - [...] = "generated on degraded inputs" (the per-series manifest).

Hence NULLABLE with NO server_default and NO backfill. On Postgres this
is a metadata-only catalog change (instant, no table rewrite, no long
lock) even on the `session_card_audit` TimescaleDB hypertable.

Reversible : `downgrade()` drops the column ; combined with
`git revert` + `redeploy-api.sh rollback` + `alembic downgrade 0049`
the change fully reverses. A `pg_dump` of `session_card_audit` is taken
before `alembic upgrade` on Hetzner (KEYWORD MIGRATION protocol).

Voie D respect : pure-Python deterministic persistence of an
already-computed runtime structure. ZERO LLM call. ZERO new feed. ZERO
new FRED series (the manifest is built by the r93 `_section_data_integrity`
over already-ingested `fred_observations`).

Revision ID: 0050
Revises: 0049
Create Date: 2026-05-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0050"
down_revision: str | None = "0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NULLABLE, NO server_default, NO backfill — see module docstring :
    # NULL is the honest "liveness not tracked at generation" state for
    # every pre-existing card; only cards generated post-deploy carry
    # the tracked [] / [...] manifest.
    op.add_column(
        "session_card_audit",
        sa.Column(
            "degraded_inputs",
            JSONB,
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("session_card_audit", "degraded_inputs")
