"""trader_notes table — Eliot's private journal (Phase B.5d v2).

Annotation libre par session/asset (or untagged). Used by /journal
route (apps/web2). Explicitly OUT of ADR-017 boundary surface — it's
Eliot's notebook, never fed back to ML/Brier/Pass-1..5.

Schema deliberately minimal:
  - id UUID PK
  - ts TIMESTAMPTZ — when the entry was *authored* (source-of-truth ordering)
  - asset VARCHAR(16) NULL — optional tag (e.g. "EUR_USD")
  - body TEXT — entry content (markdown allowed, never rendered server-side)
  - created_at TIMESTAMPTZ — DB write time (audit-friendly, may differ
    from `ts` if entry is migrated from localStorage drafts)

No FK to session_card_audit on purpose — entries can reference cards
informally in the body, but the journal must remain authoritative
even if a card is purged.

Index on `ts DESC` for the typical "last 30 entries" listing query.

Revision ID: 0029
Revises: 0028
Create Date: 2026-05-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trader_notes",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("asset", sa.String(16), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.execute("CREATE INDEX trader_notes_ts_desc_idx ON trader_notes (ts DESC);")
    op.execute(
        "CREATE INDEX trader_notes_asset_ts_idx "
        "ON trader_notes (asset, ts DESC) WHERE asset IS NOT NULL;"
    )


def downgrade() -> None:
    op.drop_index("trader_notes_asset_ts_idx", table_name="trader_notes")
    op.drop_index("trader_notes_ts_desc_idx", table_name="trader_notes")
    op.drop_table("trader_notes")
