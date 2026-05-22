"""Per-asset tempo threshold recalibration — Mission centrale Axis-7.

The r125 ship hardcoded `TEMPO_THRESHOLDS_BY_ASSET` in `sessionPulse.ts` from
a one-shot 60-day SSH `psql` calibration on `polygon_intraday`. The r125
docstring explicitly flagged this as a r126+ deferral : "auto-recalibration
deferred to r126+ (could wire a Hetzner-side weekly cron to re-derive +
push to a `tempo_thresholds` table consumed via API)".

This module is the service-layer of that auto-recalibration : a weekly
cron (`cli/run_tempo_recalibration.py` → systemd `ichor-tempo-recalibration.timer`)
recomputes the per-asset percentile thresholds from a rolling 90-day window
on `polygon_intraday` and INSERTs one row per asset into the
`tempo_thresholds` table (migration 0051). The frontend wire to consume the
new endpoint via API is split to r127 (backend ships + cron runs + data
accumulates first ; doctrine-#2 strict scope).

Why per-Paris-day grouping : the frontend `<TodaySessionPulse>` panel uses
the Paris-date boundary on the *latest* bar to define "today's bars". For
the calibrated distribution to be semantically aligned with the live
classifier, the daily-range computation here must also group by Paris-date
(NOT UTC-date — would skew the distribution by ~22-hour vs 24-hour windows
for some boundary bars). Postgres `(bar_ts AT TIME ZONE 'Europe/Paris')::date`
is DST-correct.

Why percentiles (p25/p50/p75/p90) match the r125 mapping :
  - `breakout_bp     = p90`  → top 10% of days, "stretch event"
  - `active_bp       = p75`  → top 25%, "above-typical day"
  - `trending_bp     = p50`  → median, "typical day in motion"
  - `range_bound_bp  = p25`  → lower quartile, "quiet day"
  - `compressed`     = below p25 (implicit, no threshold stored)

Returns one `TempoRecalibrationResult` per asset — either `inserted` (the
row was committed) or `skipped` (sample too small, reason recorded). The
cron CLI emits both via structlog ; the `tempo_thresholds` table itself is
the persistent audit trail (historical-trace shape, one row per
recalibration). No `auto_improvement_log` integration — that table's
`loop_kind` enum is scoped to the 4 Phase D LLM loops (brier_aggregator /
adwin_drift / post_mortem / meta_prompt) ; r126 is pure-data percentile
recalibration, not an LLM-loop event, so doctrine #9 anti-accumulation
keeps it out of that audit surface.

ADR refs : ADR-099 §Impl(r126) ; sessionPulse.ts r125 (friendly-fermi
`feat(web2): r125 per-asset tempo threshold recalibration`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import TempoThreshold

# The 5 frontend-shipped priority assets (ADR-083 D1 universe minus
# USD_CAD which has no `/briefing/[asset]` route shipped yet — extends to
# USD_CAD when the 6th route lands, ROADMAP §1). Order matches the r125
# hardcoded `TEMPO_THRESHOLDS_BY_ASSET` declaration order for diff-clarity.
DEFAULT_RECALIBRATION_ASSETS: tuple[str, ...] = (
    "EUR_USD",
    "GBP_USD",
    "XAU_USD",
    "SPX500_USD",
    "NAS100_USD",
)

# Rolling window for daily-range distribution — 90 days = ~64 trading days
# per asset, enough for stable p90 estimation while staying responsive to
# regime shifts. r125 baseline used 60d ; widened here to 90d because the
# weekly cron amortizes the wider window (faster regime adaptation than a
# 60d shifted-once-per-week sliding median).
DEFAULT_WINDOW_DAYS: int = 90

# Minimum sample size below which we skip the asset (refuse to derive
# thresholds from a sample too small to be meaningful). 7 trading days is
# the floor — anything less and even the median is dominated by noise.
DEFAULT_MIN_SAMPLE_DAYS: int = 7

# Upper sanity clamp on a single Paris-day's range_bp. A corrupt polygon
# row (fat-finger open near 0) can produce millions of bp, which would
# overflow `Numeric(8, 2)` at INSERT time. 50_000 bp = 500% daily range
# is far beyond any realistic stretch event (XAU breakout extremes top
# ~5000 bp = 50%) — see code-reviewer MF-2.
_MAX_DAILY_RANGE_BP: float = 50_000.0


@dataclass(frozen=True)
class TempoThresholdValues:
    """The 4 thresholds + the metadata of one calibration snapshot."""

    asset: str
    breakout_bp: float  # p90
    active_bp: float  # p75
    trending_bp: float  # p50
    range_bound_bp: float  # p25
    sample_size: int
    window_days: int


@dataclass(frozen=True)
class TempoRecalibrationResult:
    """Per-asset outcome of one recalibration cycle.

    Either `status = "inserted"` (thresholds field populated + persisted to
    `tempo_thresholds`) OR `status = "skipped"` (thresholds None + reason
    populated). The CLI emits both to `auto_improvement_log` so the audit
    surface captures BOTH adaptations AND data-gaps.
    """

    asset: str
    status: Literal["inserted", "skipped"]
    thresholds: TempoThresholdValues | None
    reason: str | None
    sample_size: int


def _percentile(sorted_xs: list[float], p: float) -> float:
    """Linear-interp percentile (same pattern as
    `services.hourly_volatility._percentile` ; duplicated here as a private
    helper for service-local ownership and to avoid coupling two services
    via an internal import — doctrine-#2 strict scope, no premature shared
    module). `p` in [0, 100]. `sorted_xs` must be sorted ascending."""
    if not sorted_xs:
        return 0.0
    if len(sorted_xs) == 1:
        return sorted_xs[0]
    k = (len(sorted_xs) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_xs[int(k)]
    d0 = sorted_xs[int(f)] * (c - k)
    d1 = sorted_xs[int(c)] * (k - f)
    return d0 + d1


async def _daily_ranges_bp(session: AsyncSession, asset: str, *, window_days: int) -> list[float]:
    """Return per-Paris-day range bp = (high - low) / open * 10000 for
    `asset` over the last `window_days`. Paris-day grouping matches the
    frontend `<TodaySessionPulse>` semantic (latest bar's Paris-date).

    Empty list means the asset has no bars in the window (collector lag,
    or asset not yet shipped). Caller decides whether to skip.

    Aggregation is done in SQL (faster than fetching every bar + grouping
    in Python — ~100k bars per asset over 90 days = 9MB transfer avoided).
    """
    cutoff = datetime.now(UTC) - timedelta(days=window_days)
    stmt = text(
        """
        WITH bars AS (
            SELECT
                (bar_ts AT TIME ZONE 'Europe/Paris')::date AS paris_day,
                bar_ts,
                "open",
                high,
                low
            FROM polygon_intraday
            WHERE asset = :asset
              AND bar_ts >= :cutoff
        ),
        daily AS (
            SELECT
                paris_day,
                MAX(high) AS day_high,
                MIN(low) AS day_low,
                -- The "open" of the Paris-day = the open field of the
                -- earliest bar (by bar_ts) of that day. Ties resolved
                -- arbitrarily ; the field is a per-bar OHLC O, so ties
                -- across same bar_ts are not expected on 1-min data.
                (ARRAY_AGG("open" ORDER BY bar_ts ASC))[1] AS day_open
            FROM bars
            GROUP BY paris_day
        )
        SELECT
            paris_day,
            day_open,
            day_high,
            day_low
        FROM daily
        WHERE day_open > 0
          AND day_high >= day_low
        ORDER BY paris_day ASC
        """
    )
    result = await session.execute(stmt, {"asset": asset, "cutoff": cutoff})
    ranges_bp: list[float] = []
    for row in result.all():
        day_open = float(row.day_open)
        day_high = float(row.day_high)
        day_low = float(row.day_low)
        if day_open <= 0:
            continue
        rng = (day_high - day_low) / day_open * 10_000
        if not math.isfinite(rng) or rng < 0:
            continue
        # MF-2 upper sanity clamp : a corrupt polygon row (fat-finger 0.01
        # open on XAU) can produce millions of bp, which would later
        # overflow `Numeric(8, 2)` at INSERT time and nuke the entire
        # weekly commit (one bad bar kills 5 assets). 50_000 bp = 500%
        # daily range, an order of magnitude beyond any realistic stretch
        # event (XAU breakout extremes top ~5000 bp = 50%). Defense beats
        # cure : skip the bad Paris-day instead of failing the cron.
        if rng > _MAX_DAILY_RANGE_BP:
            continue
        ranges_bp.append(rng)
    return ranges_bp


def _compute_thresholds(
    asset: str, *, ranges_bp: list[float], window_days: int
) -> TempoThresholdValues:
    """Pure-fn: sort the ranges and pull p25/p50/p75/p90. Caller must have
    already verified `len(ranges_bp) >= min_sample_days`."""
    sorted_xs = sorted(ranges_bp)
    p25 = _percentile(sorted_xs, 25.0)
    p50 = _percentile(sorted_xs, 50.0)
    p75 = _percentile(sorted_xs, 75.0)
    p90 = _percentile(sorted_xs, 90.0)
    # Defense-in-depth : the input is sorted, so monotonicity is
    # mathematically guaranteed, but float arithmetic on near-equal samples
    # can produce tiny inversions (e.g., p75 = p90 numerically equal but
    # p90 slightly less due to interp rounding). Clamp BOTTOM-UP so each
    # successive clamp builds on the already-clamped lower bound — fixing
    # `p50 = max(p50, p25)` BEFORE using it in `p75 = max(p75, p50)`
    # closes the code-reviewer MF-1 ordering bug : the previous top-down
    # clamp let a negative-input-induced `p50 < p25` slip through to
    # `p75 < p25` (broke `trending >= range_bound`) when the negative
    # range came from `_compute_thresholds` being called directly with
    # malformed input (the upstream `_daily_ranges_bp` filters them, but
    # tests + future callers should not rely on that).
    p25 = max(p25, 0.0)
    p50 = max(p50, p25)
    p75 = max(p75, p50)
    p90 = max(p90, p75)
    return TempoThresholdValues(
        asset=asset,
        breakout_bp=round(p90, 2),
        active_bp=round(p75, 2),
        trending_bp=round(p50, 2),
        range_bound_bp=round(p25, 2),
        sample_size=len(ranges_bp),
        window_days=window_days,
    )


def _to_decimal_bp(x: float) -> Decimal:
    """Convert a bp float to a Numeric(8, 2)-safe Decimal (2 fractional
    digits, banker's rounding off via ROUND_HALF_UP). The DB column is
    Numeric(8, 2) so a 6-digit-integer-part ceiling applies — fine for
    bp values which top out around 5000 on extreme XAU days."""
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


async def recalibrate_tempo_thresholds(
    session: AsyncSession,
    *,
    assets: tuple[str, ...] = DEFAULT_RECALIBRATION_ASSETS,
    window_days: int = DEFAULT_WINDOW_DAYS,
    min_sample_days: int = DEFAULT_MIN_SAMPLE_DAYS,
    dry_run: bool = False,
) -> list[TempoRecalibrationResult]:
    """Recalibrate per-asset tempo thresholds and INSERT one row per asset
    into `tempo_thresholds`. Returns one `TempoRecalibrationResult` per
    asset (inserted OR skipped with reason).

    `dry_run=True` runs the SQL aggregation + percentile computation but
    skips the INSERT — used by the CLI `--dry-run` flag for safe pre-cron
    validation on Hetzner.

    NOT a session.commit() — caller decides transaction boundaries (one
    cron call = one commit, easier to audit failures).
    """
    if window_days < 7:
        raise ValueError(f"window_days must be >= 7 (matches DB CHECK), got {window_days}")
    if min_sample_days < 1:
        raise ValueError(f"min_sample_days must be >= 1, got {min_sample_days}")

    results: list[TempoRecalibrationResult] = []
    for asset in assets:
        ranges_bp = await _daily_ranges_bp(session, asset, window_days=window_days)
        n = len(ranges_bp)
        if n < min_sample_days:
            results.append(
                TempoRecalibrationResult(
                    asset=asset,
                    status="skipped",
                    thresholds=None,
                    reason=(
                        f"sample_size {n} < min_sample_days "
                        f"{min_sample_days} (window {window_days}d)"
                    ),
                    sample_size=n,
                )
            )
            continue

        values = _compute_thresholds(asset, ranges_bp=ranges_bp, window_days=window_days)
        if not dry_run:
            row = TempoThreshold(
                asset=values.asset,
                breakout_bp=_to_decimal_bp(values.breakout_bp),
                active_bp=_to_decimal_bp(values.active_bp),
                trending_bp=_to_decimal_bp(values.trending_bp),
                range_bound_bp=_to_decimal_bp(values.range_bound_bp),
                sample_size=values.sample_size,
                window_days=values.window_days,
            )
            session.add(row)
            # Flush — surface CHECK constraint violations EARLY (before
            # the next asset's compute). The CLI commits once at the end
            # (all-or-nothing semantic) ; a CHECK violation here aborts
            # the whole run via the CLI's try/except → rollback, so any
            # already-flushed rows from prior assets in this run are
            # ALSO rolled back. This is deliberate : a bad calibration
            # mid-batch shouldn't half-persist a stale snapshot. Code-
            # reviewer Y-1 docstring drift corrected here.
            await session.flush()

        results.append(
            TempoRecalibrationResult(
                asset=asset,
                status="inserted",
                thresholds=values,
                reason=None,
                sample_size=n,
            )
        )

    return results
