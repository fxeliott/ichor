"""fx_ticks retention policy — bound unbounded tick-stream disk growth.

`fx_ticks` (migration 0020) is the only high-write hypertable in the socle
(~1.5M rows/day from the Polygon Forex WebSocket). It has native compression
after 7 days (20-50x), but compression only SHRINKS chunks — it does NOT bound
total size, so without a retention policy the table grows on disk forever.

This adds a TimescaleDB retention policy that drops chunks older than 180 days.
The horizon is deliberately generous: it sits far above any VPIN microstructure
lookback (intraday/multi-day) and above the 7-day compression threshold, so it
only reclaims genuinely-cold tick history. At ~1.5M rows/day compressed ~30x,
180 days of ticks is a bounded, predictable footprint instead of an unbounded
one. `if_not_exists => TRUE` keeps the migration idempotent.

ADR-022 boundary unchanged : ticks feed VPIN probabilities only, never orders.

Revision ID: 0058
Revises: 0057
Create Date: 2026-06-18
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0058"
down_revision: str | None = "0057"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "SELECT add_retention_policy('fx_ticks', INTERVAL '180 days', if_not_exists => TRUE);"
    )


def downgrade() -> None:
    op.execute("SELECT remove_retention_policy('fx_ticks', if_exists => TRUE);")
