"""Phase 1 collector tables — fred + gdelt + gpr + cot + cb_speeches + kalshi + manifold + session_card_audit

Adds 8 tables for the Phase 1 Living Macro Entity ingestion layer :

  - fred_observations    : (key, observation_date, value) — TimescaleDB hypertable
  - gdelt_events         : translingual news from GDELT 2.0
  - gpr_observations     : daily AI-GPR Index readings
  - cot_positions        : weekly CFTC Disaggregated Futures Only
  - cb_speeches          : central bank speeches (BIS aggregator + per-CB feeds)
  - kalshi_markets       : Kalshi public market snapshots
  - manifold_markets     : Manifold market snapshots
  - session_card_audit   : Claude-generated session verdicts (replaces
                            predictions_audit purpose, but kept distinct
                            so old data survives)

Hypertable strategy : partition by ingestion / observation time, chunk
intervals tuned to write rate (high-frequency = smaller chunks).

Revision ID: 0005
Revises: 0003
Create Date: 2026-05-03 (Phase 1 reset)
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision: str = "0005"
# Chain on top of 0004 even though backtest_runs was archived at the code
# level (ADR-017 reset, 2026-05-03) — production DB already applied 0004,
# so we keep the linear chain. A later migration may drop the table.
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ──────────────────────── fred_observations ────────────────────────
    op.create_table(
        "fred_observations",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("observation_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("series_id", sa.String(64), nullable=False),
        sa.Column("value", sa.Float()),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", "observation_date"),
        sa.UniqueConstraint("series_id", "observation_date", name="uq_fred_series_date"),
    )
    op.create_index("ix_fred_obs_series_id", "fred_observations", ["series_id"])
    op.create_index("ix_fred_obs_observation_date", "fred_observations", ["observation_date"])
    op.execute(
        "SELECT create_hypertable('fred_observations', 'observation_date', "
        "chunk_time_interval => INTERVAL '90 days', if_not_exists => TRUE);"
    )

    # ──────────────────────── gdelt_events ────────────────────────
    op.create_table(
        "gdelt_events",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("seendate", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("query_label", sa.String(64), nullable=False),
        sa.Column("url", sa.String(1024), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("domain", sa.String(128)),
        sa.Column("language", sa.String(32)),
        sa.Column("sourcecountry", sa.String(32)),
        sa.Column("tone", sa.Float(), nullable=False),
        sa.Column("image_url", sa.String(1024)),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", "seendate"),
        # TimescaleDB requires the partition column (`seendate`) inside any
        # unique key on a hypertable. App-level dedup still uses
        # (url, query_label) before INSERT.
        sa.UniqueConstraint("url", "query_label", "seendate", name="uq_gdelt_url_query_seen"),
    )
    op.create_index("ix_gdelt_query_label", "gdelt_events", ["query_label"])
    op.create_index("ix_gdelt_seendate", "gdelt_events", ["seendate"])
    op.create_index("ix_gdelt_domain", "gdelt_events", ["domain"])
    op.execute(
        "SELECT create_hypertable('gdelt_events', 'seendate', "
        "chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE);"
    )

    # ──────────────────────── gpr_observations ────────────────────────
    op.create_table(
        "gpr_observations",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("observation_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("ai_gpr", sa.Float(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", "observation_date"),
        sa.UniqueConstraint("observation_date", name="uq_gpr_observation_date"),
    )
    op.create_index("ix_gpr_observation_date", "gpr_observations", ["observation_date"])
    op.execute(
        "SELECT create_hypertable('gpr_observations', 'observation_date', "
        "chunk_time_interval => INTERVAL '180 days', if_not_exists => TRUE);"
    )

    # ──────────────────────── cot_positions ────────────────────────
    op.create_table(
        "cot_positions",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("market_code", sa.String(16), nullable=False),
        sa.Column("market_name", sa.String(128)),
        sa.Column("producer_net", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("swap_dealer_net", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("managed_money_net", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("other_reportable_net", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("non_reportable_net", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("open_interest", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", "report_date"),
        sa.UniqueConstraint("market_code", "report_date", name="uq_cot_market_date"),
    )
    op.create_index("ix_cot_market_code", "cot_positions", ["market_code"])
    op.create_index("ix_cot_report_date", "cot_positions", ["report_date"])
    op.execute(
        "SELECT create_hypertable('cot_positions', 'report_date', "
        "chunk_time_interval => INTERVAL '180 days', if_not_exists => TRUE);"
    )

    # ──────────────────────── cb_speeches ────────────────────────
    op.create_table(
        "cb_speeches",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("central_bank", sa.String(32), nullable=False),
        sa.Column("speaker", sa.String(128)),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("summary", sa.Text()),
        sa.Column("url", sa.String(1024), nullable=False),
        sa.Column("source_feed", sa.String(64), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", "published_at"),
        # TimescaleDB requires the partition column (`published_at`) inside
        # any unique key on a hypertable. App-level dedup uses (url) alone.
        sa.UniqueConstraint("url", "published_at", name="uq_cb_speech_url_pub"),
    )
    op.create_index("ix_cb_speeches_central_bank", "cb_speeches", ["central_bank"])
    op.create_index("ix_cb_speeches_published_at", "cb_speeches", ["published_at"])
    op.create_index("ix_cb_speeches_speaker", "cb_speeches", ["speaker"])
    op.execute(
        "SELECT create_hypertable('cb_speeches', 'published_at', "
        "chunk_time_interval => INTERVAL '90 days', if_not_exists => TRUE);"
    )

    # ──────────────────────── kalshi_markets ────────────────────────
    op.create_table(
        "kalshi_markets",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("ticker", sa.String(128), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("yes_price", sa.Float()),
        sa.Column("no_price", sa.Float()),
        sa.Column("volume_24h", sa.Integer()),
        sa.Column("open_interest", sa.Integer()),
        sa.Column("expiration_time", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(32)),
        sa.PrimaryKeyConstraint("id", "fetched_at"),
    )
    op.create_index("ix_kalshi_ticker", "kalshi_markets", ["ticker"])
    op.create_index("ix_kalshi_fetched_at", "kalshi_markets", ["fetched_at"])
    op.execute(
        "SELECT create_hypertable('kalshi_markets', 'fetched_at', "
        "chunk_time_interval => INTERVAL '30 days', if_not_exists => TRUE);"
    )

    # ──────────────────────── manifold_markets ────────────────────────
    op.create_table(
        "manifold_markets",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("slug", sa.String(128), nullable=False),
        sa.Column("market_id", sa.String(128), nullable=False),
        sa.Column("question", sa.String(512), nullable=False),
        sa.Column("probability", sa.Float()),
        sa.Column("volume", sa.Float()),
        sa.Column("closed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("creator_username", sa.String(128)),
        sa.PrimaryKeyConstraint("id", "fetched_at"),
    )
    op.create_index("ix_manifold_slug", "manifold_markets", ["slug"])
    op.create_index("ix_manifold_fetched_at", "manifold_markets", ["fetched_at"])
    op.execute(
        "SELECT create_hypertable('manifold_markets', 'fetched_at', "
        "chunk_time_interval => INTERVAL '30 days', if_not_exists => TRUE);"
    )

    # ──────────────────────── session_card_audit ────────────────────────
    # The replacement for predictions_audit (which stays for historical data).
    # Stores Claude-generated session card verdicts with full provenance for
    # calibration tracking (Brier scores per asset, session, regime).
    op.create_table(
        "session_card_audit",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("session_type", sa.String(32), nullable=False),
        # 'pre_londres' | 'pre_ny' | 'event_driven'
        sa.Column("asset", sa.String(16), nullable=False),
        sa.Column("model_id", sa.String(64), nullable=False),
        # 'claude-opus-4-7' or similar
        sa.Column("regime_quadrant", sa.String(32)),
        # 'haven_bid' | 'funding_stress' | 'goldilocks' | 'usd_complacency'
        sa.Column("bias_direction", sa.String(8), nullable=False),
        # 'long' | 'short' | 'neutral'
        sa.Column("conviction_pct", sa.Float(), nullable=False),
        # 0-100, capped at 95 (per macro-frameworks 100% red flag)
        sa.Column("magnitude_pips_low", sa.Float()),
        sa.Column("magnitude_pips_high", sa.Float()),
        sa.Column("timing_window_start", sa.DateTime(timezone=True)),
        sa.Column("timing_window_end", sa.DateTime(timezone=True)),
        sa.Column("mechanisms", JSONB()),
        # JSONB array of {claim, sources[]}
        sa.Column("invalidations", JSONB()),
        # JSONB array of {condition, threshold, source}
        sa.Column("catalysts", JSONB()),
        # JSONB array of {time, event, expected_impact}
        sa.Column("correlations_snapshot", JSONB()),
        # JSONB dict of {asset_pair: rolling_60d_corr}
        sa.Column("polymarket_overlay", JSONB()),
        # JSONB array of {market, yes_price, divergence_vs_consensus}
        sa.Column("source_pool_hash", sa.String(64), nullable=False),
        # Hash of the data pool used (for reproducibility + cache key)
        sa.Column("critic_verdict", sa.String(32)),
        # 'approved' | 'amendments' | 'blocked'
        sa.Column("critic_findings", JSONB()),
        sa.Column("claude_raw_response", JSONB()),
        sa.Column("claude_duration_ms", sa.Integer()),
        # Outcome tracking (filled later)
        sa.Column("realized_close_session", sa.Float()),
        sa.Column("realized_high_session", sa.Float()),
        sa.Column("realized_low_session", sa.Float()),
        sa.Column("realized_at", sa.DateTime(timezone=True)),
        sa.Column("brier_contribution", sa.Float()),
        # (conviction_pct/100 - realized_outcome)^2
        sa.PrimaryKeyConstraint("id", "generated_at"),
        sa.CheckConstraint(
            "bias_direction IN ('long', 'short', 'neutral')",
            name="ck_session_card_bias_valid",
        ),
        sa.CheckConstraint(
            "conviction_pct >= 0 AND conviction_pct <= 100",
            name="ck_session_card_conviction_range",
        ),
        sa.CheckConstraint(
            "session_type IN ('pre_londres', 'pre_ny', 'event_driven')",
            name="ck_session_card_session_type_valid",
        ),
    )
    op.create_index("ix_session_card_asset", "session_card_audit", ["asset"])
    op.create_index("ix_session_card_session_type", "session_card_audit", ["session_type"])
    op.create_index("ix_session_card_generated_at", "session_card_audit", ["generated_at"])
    op.execute(
        "SELECT create_hypertable('session_card_audit', 'generated_at', "
        "chunk_time_interval => INTERVAL '30 days', if_not_exists => TRUE);"
    )


def downgrade() -> None:
    op.drop_table("session_card_audit")
    op.drop_table("manifold_markets")
    op.drop_table("kalshi_markets")
    op.drop_table("cb_speeches")
    op.drop_table("cot_positions")
    op.drop_table("gpr_observations")
    op.drop_table("gdelt_events")
    op.drop_table("fred_observations")
