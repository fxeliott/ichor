"""Proactive collector-freshness monitor — S03 / Chantier D.

Why this module exists
----------------------
The dead-collector class has fired repeatedly: COT silently empty for
weeks (fixed 06-09), ecb_sdmx/bls/eia crashing their persist step while
timers reported clean (fixed 06-09), crypto_fear_greed stopped 05-05,
runner outages masked by ``SuccessExitStatus=0 1`` (3 firings — killed
for the RUNNER by ADR-110). For the DATA layer the same hole stayed
open: ``data_liveness.classify_liveness`` is day-granular, passive, and
consulted only inside ``data_pool`` sections. Nothing ALERTS when a
table stops moving.

This module is the active half (PLAN_DIRECTEUR §5 Chantier D gate: "a
deliberately-killed collector fires an alert < 15 min"). A registry maps
every persisted collect table to its expected freshness window; the
``run_data_freshness_check`` CLI (5-min systemd timer) MAX()es each
table's timestamp, classifies, emits ``COLLECTOR_STALE`` /
``COLLECTOR_ABSENT`` alerts through the canonical alerts pipeline, and
exits 2 on the healthy→degraded TRANSITION so ``OnFailure=ichor-notify@``
fires (transition-based, mirrors ``ichor-runner-health-check``).

Exit-code policing was deliberately rejected: collectors legitimately
exit 1 on benign empty sources (weekend flat-files, dormant creds), so
``SuccessExitStatus=0 1`` must stay on collector units. Freshness of the
DESTINATION TABLE is the outcome that matters — this monitor measures
that, not the process.

Design contract
---------------
Pure functions only in this module (mirrors ``data_liveness`` /
``conviction_fusion``): ``now`` injected, no I/O, no ``datetime.now()``.
The CLI owns SQL + state-file + alert emission. Minute-granular on
purpose — ``classify_liveness``'s whole-day arithmetic cannot see a 2h
WebSocket outage; its byte-consistency invariant with the FRED path is
left untouched.

Market gating (ADR-105 reuse)
-----------------------------
Market-driven sources (FX ticks, intraday bars, briefings, cards) are
only expected to move while their market is open. A source gated ``fx``
or ``us_equity`` is checked ONLY when the market was open over the
ENTIRE lookback window ``[now - max_age, now]`` — this kills both the
weekend false alarm and the Monday-reopen false alarm (age measured
against a Friday timestamp seconds after reopen).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from .market_session import SessionStatus

Criticality = Literal["critical", "warning"]
MarketGate = Literal["none", "fx", "us_equity"]
FreshnessStatus = Literal["fresh", "stale", "absent", "skipped_market_closed"]
ContentVerdict = Literal["ok", "null_dead", "degenerate", "insufficient_sample"]

_IDENT_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")  # ≥2 chars ("ts" is real)


@dataclass(frozen=True, slots=True)
class FreshnessSpec:
    """One monitored collect table and its expected freshness window."""

    source_key: str
    table: str
    ts_column: str
    max_age: timedelta
    criticality: Criticality
    gate: MarketGate = "none"
    note: str = ""

    def __post_init__(self) -> None:
        # The CLI interpolates table/column into SQL — registry entries are
        # code-owned constants, but pin the identifier shape anyway so a
        # future typo can never become an injection surface.
        if not _IDENT_RE.match(self.table) or not _IDENT_RE.match(self.ts_column):
            raise ValueError(f"invalid SQL identifier in spec {self.source_key!r}")
        # source_key lands in alerts.asset VARCHAR(16) via check_metric —
        # an overlong key would crash the alert flush at exactly the moment
        # the source degrades (verifier finding #1).
        if len(self.source_key) > 16:
            raise ValueError(f"source_key {self.source_key!r} exceeds alerts.asset VARCHAR(16)")


@dataclass(frozen=True, slots=True)
class FreshnessResult:
    """Verdict for one source at one instant."""

    spec: FreshnessSpec
    status: FreshnessStatus
    latest_at: datetime | None
    age: timedelta | None

    @property
    def is_degraded(self) -> bool:
        return self.status in ("stale", "absent")


def classify_content(
    *,
    sample_size: int,
    non_null: int,
    distinct: int,
    min_sample: int = 20,
    max_null_rate: float = 0.95,
) -> ContentVerdict:
    """Content-validity verdict for a value column over a RECENT window.

    The freshness sweep above answers "are rows still arriving?"; this answers
    "do the arriving rows carry real values?". It closes the blind spot proven
    by the Kalshi incident (2026-06-19): the collector kept persisting rows
    (freshness GREEN) but every ``yes_price`` was NULL after an upstream schema
    migration — undetectable by a MAX(ts) check. Catches both classes:

    - ``null_dead``   : > ``max_null_rate`` of the sample is NULL (Kalshi class).
    - ``degenerate``  : every value is identical (distinct ≤ 1) — e.g. the
      GDELT ``tone`` = 0.0-everywhere incident (2026-06-11, fixed ADR-112).

    A RECENT window + ``min_sample`` floor are mandatory: a wide window would
    false-flag a freshly-fixed collector on its aged-out NULL history, and a
    thin sample cannot distinguish a dead column from a quiet one.
    """
    if sample_size < min_sample:
        return "insufficient_sample"
    null_rate = 1.0 - (non_null / sample_size)
    if null_rate > max_null_rate:
        return "null_dead"
    if distinct <= 1:
        return "degenerate"
    return "ok"


# ── Registry ──────────────────────────────────────────────────────────
# max_age = expected cadence × a 2-3 missed-runs grace, OR the upstream
# publication rhythm + its documented lag for slow series (GPR/MCT/TIC
# publish monthly with multi-week lag — witnessed in prod 06-10/06-11,
# "stale upstream" there is a publication calendar, not a fault).


def _M(n: int) -> timedelta:  # noqa: N802 — registry shorthand
    return timedelta(minutes=n)


def _H(n: int) -> timedelta:  # noqa: N802
    return timedelta(hours=n)


def _D(n: int) -> timedelta:  # noqa: N802
    return timedelta(days=n)


FRESHNESS_REGISTRY: tuple[FreshnessSpec, ...] = (
    # ── critical tier: the real-time promise itself ──
    FreshnessSpec(
        # ts (not created_at): partition key of the hypertable — max() gets
        # chunk exclusion + index; created_at is unindexed (~1.5M rows/day,
        # columnar-compressed past 7d → max(created_at) would full-scan
        # every 5 min). For a live stream ts ≈ created_at within seconds.
        "fx_ticks",
        "fx_ticks",
        "ts",
        _M(15),
        "critical",
        "fx",
        "Polygon FX WebSocket stream — continuous while FX is open",
    ),
    FreshnessSpec(
        # bar_ts (not fetched_at): same hypertable-partition-key reasoning,
        # and the bar timestamp measures DATA freshness directly.
        "polygon_intraday",
        "polygon_intraday",
        "bar_ts",
        _M(15),
        "critical",
        "fx",
        "1-min polygon aggs timer",
    ),
    FreshnessSpec(
        "polymarket",
        "polymarket_snapshots",
        "fetched_at",
        _M(30),
        "critical",
        "none",
        "5-min timer, 24/7 markets",
    ),
    FreshnessSpec(
        "news_items",
        "news_items",
        "fetched_at",
        _M(90),
        "critical",
        "none",
        "rss 15-min + polygon_news + social — 24/7 flow",
    ),
    FreshnessSpec(
        "gdelt",
        "gdelt_events",
        "fetched_at",
        _H(2),
        "critical",
        "none",
        "30-min timer, 24/7 world news",
    ),
    FreshnessSpec(
        "economic_events",
        "economic_events",
        "fetched_at",
        _H(12),
        "critical",
        "none",
        "forex_factory calendar 4x/day",
    ),
    FreshnessSpec(
        "fred",
        "fred_observations",
        "fetched_at",
        _H(30),
        "critical",
        "fx",
        "multiple daily timers incl. VIX_LIVE intraday; quiet weekends",
    ),
    FreshnessSpec(
        "briefings",
        "briefings",
        "created_at",
        _H(9),
        "critical",
        "fx",
        "4 windows/day 06-22h CEST; widest gap ny_close->pre_londres = 8h",
    ),
    FreshnessSpec(
        "session_cards",
        "session_card_audit",
        "generated_at",
        _H(9),
        "critical",
        "fx",
        "4 batches/day + streaming_refresh regens",
    ),
    # ── warning tier: depth/positioning/sentiment layers ──
    FreshnessSpec("kalshi", "kalshi_markets", "fetched_at", _H(1), "warning"),
    FreshnessSpec("manifold", "manifold_markets", "fetched_at", _H(1), "warning"),
    FreshnessSpec(
        "couche2",
        "couche2_outputs",
        "created_at",
        _H(9),
        "warning",
        "none",
        "LLM-dependent; runner outage already alerts via runner-health-check",
    ),
    FreshnessSpec("myfxbook", "myfxbook_outlooks", "fetched_at", _H(9), "warning"),
    FreshnessSpec("cb_speeches", "cb_speeches", "fetched_at", _H(26), "warning"),
    FreshnessSpec("gex", "gex_snapshots", "created_at", _H(36), "warning", "us_equity"),
    FreshnessSpec("market_data", "market_data", "fetched_at", _D(4), "warning"),
    FreshnessSpec("bund_10y", "bund_10y_observations", "fetched_at", _D(5), "warning"),
    FreshnessSpec("estr", "estr_observations", "fetched_at", _D(5), "warning"),
    FreshnessSpec("finra_short", "finra_short_volume", "fetched_at", _D(6), "warning"),
    FreshnessSpec("cboe_skew", "cboe_skew_observations", "fetched_at", _D(6), "warning"),
    FreshnessSpec("cboe_vvix", "cboe_vvix_observations", "fetched_at", _D(6), "warning"),
    FreshnessSpec(
        "cot",
        "cot_positions",
        "fetched_at",
        _D(9),
        "warning",
        "none",
        "weekly Friday release + processing lag",
    ),
    FreshnessSpec("cftc_tff", "cftc_tff_observations", "fetched_at", _D(9), "warning"),
    FreshnessSpec("eia_crude", "eia_crude_stocks", "fetched_at", _D(9), "warning"),
    # source_key ≤ 16 chars HARD LIMIT — it lands in alerts.asset VARCHAR(16)
    # (verifier finding #1: "cleveland_nowcast" = 17 chars would crash the
    # flush → exit 3 masked by systemd → the monitor silently self-kills).
    # Pinned by __post_init__ below + test_registry invariant.
    FreshnessSpec("cleveland_now", "cleveland_fed_nowcasts", "fetched_at", _D(10), "warning"),
    FreshnessSpec(
        "gpr",
        "gpr_observations",
        "fetched_at",
        _D(12),
        "warning",
        "none",
        "Caldara-Iacoviello publication lag is normal (witnessed 06-10)",
    ),
    FreshnessSpec("nfib_sbet", "nfib_sbet_observations", "fetched_at", _D(40), "warning"),
    FreshnessSpec(
        "nyfed_mct",
        "nyfed_mct_observations",
        "fetched_at",
        _D(50),
        "warning",
        "none",
        "monthly + multi-week publication lag",
    ),
    FreshnessSpec(
        "treasury_tic",
        "treasury_tic_holdings",
        "fetched_at",
        _D(75),
        "warning",
        "none",
        "monthly with ~6-week lag",
    ),
)


def market_open_for_gate(gate: MarketGate, status: SessionStatus) -> bool:
    """ADR-105 SSOT reuse: is the gated market open in ``status``?"""
    if gate == "none":
        return True
    if status.market_closed_fx:
        return False
    if gate == "us_equity" and status.market_closed_us_equity:
        return False
    return True


def should_check(
    spec: FreshnessSpec,
    *,
    status_now: SessionStatus,
    status_window_start: SessionStatus,
) -> bool:
    """Check only when the gated market was open over the ENTIRE lookback
    window — both endpoints. (A closure strictly inside the window with
    both endpoints open cannot happen for these gates: FX/US-equity
    closures last longer than every gated spec's max_age.)"""
    return market_open_for_gate(spec.gate, status_now) and market_open_for_gate(
        spec.gate, status_window_start
    )


def evaluate_freshness(
    spec: FreshnessSpec,
    latest_at: datetime | None,
    *,
    now: datetime,
) -> FreshnessResult:
    """Pure minute-granular classification: fresh | stale | absent."""
    if latest_at is None:
        return FreshnessResult(spec, "absent", None, None)
    if latest_at.tzinfo is None:
        latest_at = latest_at.replace(tzinfo=UTC)
    age = now - latest_at
    status: FreshnessStatus = "fresh" if age <= spec.max_age else "stale"
    return FreshnessResult(spec, status, latest_at, age)


# ── Transition-based exit contract (mirrors runner-health-check) ─────

RENOTIFY_SECONDS = 7200  # re-notify every 2h while degraded (not every 5 min)


def decide_exit(
    prev_state: dict[str, Any] | None,
    *,
    critical_degraded: bool,
    now_epoch: int,
    renotify_seconds: int = RENOTIFY_SECONDS,
) -> tuple[int, dict[str, Any]]:
    """(exit_code, new_state). Exit 2 ONLY on the healthy→degraded
    transition or on the periodic re-notify while degraded — steady
    states exit 0 so ``OnFailure=ichor-notify@`` does not spam."""
    prev_status = (prev_state or {}).get("status", "ok")
    last_notify = int((prev_state or {}).get("last_notify_epoch", 0))

    if not critical_degraded:
        return 0, {"status": "ok", "last_notify_epoch": last_notify}
    if prev_status != "degraded":
        return 2, {"status": "degraded", "last_notify_epoch": now_epoch}
    if now_epoch - last_notify >= renotify_seconds:
        return 2, {"status": "degraded", "last_notify_epoch": now_epoch}
    return 0, {"status": "degraded", "last_notify_epoch": last_notify}
