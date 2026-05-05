"""economic_events — ForexFactory weekly calendar persistence.

Stores parsed events from the FairEconomy/ForexFactory XML feed (NFP,
CPI, FOMC, ECB, ...) so the brain pipeline + /v1/calendar can query
them alongside the existing FRED-projected releases.

Dedup via the natural composite key (currency, scheduled_at, title) —
ForexFactory republishes the same event multiple times per week as
forecast/previous values are revised, and we want the latest copy.

Revision ID: 0019
Revises: 0018
Create Date: 2026-05-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "economic_events",
        sa.Column("id", UUID(as_uuid=True), nullable=False, primary_key=True),
        sa.Column("currency", sa.String(length=8), nullable=False, index=True),
        sa.Column(
            "scheduled_at",
            sa.DateTime(timezone=True),
            nullable=True,
            index=True,
        ),
        sa.Column("is_all_day", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("impact", sa.String(length=16), nullable=False, index=True),
        sa.Column("forecast", sa.String(length=64), nullable=True),
        sa.Column("previous", sa.String(length=64), nullable=True),
        sa.Column("url", sa.String(length=512), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="forex_factory"),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "impact IN ('low', 'medium', 'high', 'holiday')",
            name="ck_economic_events_impact",
        ),
        sa.UniqueConstraint(
            "currency",
            "scheduled_at",
            "title",
            name="uq_economic_events_natural_key",
        ),
    )
    # Common query : "next N high-impact events for a currency".
    op.create_index(
        "ix_economic_events_currency_scheduled",
        "economic_events",
        ["currency", "scheduled_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_economic_events_currency_scheduled", table_name="economic_events")
    op.drop_table("economic_events")
