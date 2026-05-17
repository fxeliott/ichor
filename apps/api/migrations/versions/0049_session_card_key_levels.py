"""session_card_key_levels — ADR-083 D3 KeyLevel snapshot persistence (r62).

Adds `session_card_audit.key_levels JSONB NOT NULL DEFAULT '[]'::jsonb` —
per-card snapshot of all currently-firing KeyLevel objects (TGA + HKMA +
gamma_flip + call_wall + put_wall + VIX + SKEW + HY OAS + polymarket)
captured at the moment the 4-pass orchestrator finalizes the session card.

Closes the ADR-083 D3 -> D4 architectural bridge :

- D3 (r54-r58 + r60) shipped 9 KeyLevel computers + r59 shipped
  /v1/key-levels real-time endpoint.
- Without persistence, historical session cards lose their KeyLevel
  context — Pass-2 prompt enrichment + D4 frontend replay both need
  the snapshot frozen at generation time, not recomputed at read time.

Shape per ADR-083 D3 canonical (mirror of /v1/key-levels response items) :

    [
      {
        "asset": "USD",
        "level": 838.584,
        "kind": "tga_liquidity_gate",
        "side": "above_liquidity_drain_below_inject",
        "source": "FRED:WTREGEN 2026-05-13",
        "note": "TGA $839B above $700B threshold..."
      },
      ... 0-N entries depending on which bands are firing
    ]

Empty list `[]` is the canonical "all bands NORMAL" state — distinct
from NULL which would imply "snapshot not computed".

NOT NULL with server_default `'[]'::jsonb` so existing rows backfill
cleanly without an explicit UPDATE. Mirrors migration 0039 `scenarios`
pattern verbatim (W105a, ADR-085) — same JSONB column shape semantics.

Voie D respect : pure-Python compute from already-collected upstream
data. ZERO LLM call. ZERO new paid feed. Frontend gel rule 4 honored —
no `apps/web2` touch ; this is pure backend persistence.

Revision ID: 0049
Revises: 0048
Create Date: 2026-05-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0049"
down_revision: str | None = "0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "session_card_audit",
        sa.Column(
            "key_levels",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("session_card_audit", "key_levels")
