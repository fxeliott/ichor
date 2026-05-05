"""collector tables — news_items + polymarket_snapshots (TimescaleDB hypertables)

Both tables are partitioned by ingest time (`fetched_at`) since reads are
overwhelmingly "what arrived in the last X minutes" or "what's the latest
snapshot of slug Y" — TimescaleDB compresses chunks > 30d to keep storage
flat, and chunk pruning makes time-range queries O(log N).

`news_items`:
  - `guid_hash` (sha256[:32], not full UUID) is unique per source — ensures the
    cron-fired collector never inserts the same headline twice.
  - `(source, fetched_at)` index supports per-source dashboards.
  - `tone_label` + `tone_score` populated by FinBERT-tone in a separate worker;
    nullable so we can ingest without blocking on the model.

`polymarket_snapshots`:
  - One row per (slug, fetched_at). No upsert — every poll is a snapshot for
    historical analysis (price evolution, volume bursts).
  - `outcomes`/`last_prices` kept as JSONB to absorb multi-outcome markets
    without schema changes.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ──────────────────────── news_items ────────────────────────
    op.create_table(
        "news_items",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("source_kind", sa.String(32), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("summary", sa.Text()),
        sa.Column("url", sa.String(1024), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("guid_hash", sa.String(32), nullable=False),
        sa.Column("raw_categories", ARRAY(sa.String(64))),
        # NLP tagging — populated asynchronously
        sa.Column("tone_label", sa.String(16)),  # positive/neutral/negative
        sa.Column("tone_score", sa.Float()),
        sa.PrimaryKeyConstraint("id", "fetched_at"),
        sa.UniqueConstraint(
            "source", "guid_hash", "fetched_at", name="uq_news_items_source_guid_fetchedat"
        ),
        sa.CheckConstraint(
            "source_kind IN ('news','central_bank','regulator','social','academic')",
            name="ck_news_items_source_kind_valid",
        ),
        sa.CheckConstraint(
            "tone_label IS NULL OR tone_label IN ('positive','neutral','negative')",
            name="ck_news_items_tone_label_valid",
        ),
    )
    op.create_index("ix_news_items_source", "news_items", ["source"])
    op.create_index("ix_news_items_published_at", "news_items", ["published_at"])
    op.create_index("ix_news_items_fetched_at", "news_items", ["fetched_at"])
    op.create_index("ix_news_items_guid_hash", "news_items", ["guid_hash"])

    op.execute(
        "SELECT create_hypertable('news_items', 'fetched_at', "
        "chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE);"
    )

    # ──────────────────────── polymarket_snapshots ────────────────────────
    op.create_table(
        "polymarket_snapshots",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("slug", sa.String(128), nullable=False),
        sa.Column("market_id", sa.String(128), nullable=False),
        sa.Column("question", sa.String(512), nullable=False),
        sa.Column("closed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("outcomes", JSONB(), nullable=False),
        sa.Column("last_prices", JSONB(), nullable=False),
        sa.Column("volume_usd", sa.Float()),
        sa.PrimaryKeyConstraint("id", "fetched_at"),
    )
    op.create_index("ix_polymarket_snapshots_slug", "polymarket_snapshots", ["slug"])
    op.create_index("ix_polymarket_snapshots_fetched_at", "polymarket_snapshots", ["fetched_at"])

    op.execute(
        "SELECT create_hypertable('polymarket_snapshots', 'fetched_at', "
        "chunk_time_interval => INTERVAL '30 days', if_not_exists => TRUE);"
    )


def downgrade() -> None:
    op.drop_table("polymarket_snapshots")
    op.drop_table("news_items")
