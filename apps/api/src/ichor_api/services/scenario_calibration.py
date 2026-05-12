"""Pass-6 scenario calibration — per (asset, session_type) z-thresholds.

Computes the rolling 252 trading-day calibration of the canonical
z-score thresholds (`(-2.5, -1.0, -0.25, 0.25, 1.0, 2.5)` from
`ichor_brain.scenarios.BUCKET_Z_THRESHOLDS`) into per-asset pip/point
thresholds, using EWMA λ=0.94 RiskMetrics convention on session-window
realized returns. Persists one row per (asset, session_type) into
`scenario_calibration_bins` (migration 0039) at every Sunday 00:00 UTC
refresh.

Architecture choices (W105 researcher 2026-05-12 web review) :

  * **EWMA λ=0.94** (RiskMetrics J.P. Morgan convention, half-life
    ≈ 11.2 trading days) — adapts faster than rolling std on regime
    transitions, standard since 1996, used by GS / BlackRock / IMF.
  * **252 trading-day window** for the EWMA bootstrap + simple-std
    fallback when sample_n < 60 — industry convention 1 trading year.
  * **Weekly Sunday refresh** — sufficient (intra-week recalibration
    would be noise, per Stanford EWMM Boyd 2024).
  * **Per-asset unit handling** — FX majors return pips (10000×
    log-return for EURUSD/GBPUSD/USDCAD ; 100× for USDJPY) ; XAU/USD
    returns price points ; NAS100/SPX500 return index points.

Pure-Python compute function — no LLM, no network. Reads
`polygon_intraday` realized session-window returns via SQLAlchemy.
Tests can mock the session and stub return arrays directly without
hitting the DB.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from ichor_brain.scenarios import BUCKET_Z_THRESHOLDS
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.polygon_intraday import PolygonIntradayBar
from ..models.scenario_calibration_bins import ScenarioCalibrationBins

# RiskMetrics J.P. Morgan 1996 — λ=0.94 daily for FX / equity index
# returns. Half-life = log(0.5)/log(λ) ≈ 11.2 trading days. Still the
# standard 2026 (cf BIS Quarterly Review + IMF WP/2025/105).
EWMA_LAMBDA: float = 0.94

# Sample-size floor before we trust the EWMA σ estimate enough to write
# the calibration bins to the DB. Below this, write the row with
# `sample_n` set anyway so downstream consumers can decide whether to
# skip (typical : `passes/scenarios.py` falls back to canonical
# magnitudes when sample_n < CONFIDENCE_FLOOR).
CONFIDENCE_FLOOR: int = 60

# Trading-day rolling window. Institutional convention = 252.
ROLLING_WINDOW_DAYS: int = 252

# Per-asset unit factor : multiplied against log-returns to get the
# asset's pip/point unit. FX majors store pips ; XAU stores price-points
# (~$1 unit) ; NAS100/SPX500 store index points (~10-100 unit).
_PIP_UNIT_FACTOR: dict[str, float] = {
    "EUR_USD": 10_000.0,
    "GBP_USD": 10_000.0,
    "USD_CAD": 10_000.0,
    "AUD_USD": 10_000.0,
    "USD_JPY": 100.0,
    "XAU_USD": 1.0,  # price points
    "NAS100_USD": 1.0,  # index points
    "SPX500_USD": 1.0,  # index points
}

# Asset-aware fallback magnitude scaling, in the asset's pip/point unit,
# when the EWMA can't be computed (cold-start / empty polygon_intraday).
# Conservative typical-session-window 1σ magnitudes from public
# historical references (researcher 2026-05-12 web review) — used by
# `compute_calibration_bins` when sample_n < CONFIDENCE_FLOOR.
_FALLBACK_1SIG_PIPS: dict[str, float] = {
    "EUR_USD": 35.0,
    "GBP_USD": 45.0,
    "USD_CAD": 35.0,
    "AUD_USD": 40.0,
    "USD_JPY": 30.0,
    "XAU_USD": 12.0,  # USD points
    "NAS100_USD": 120.0,  # NDX points
    "SPX500_USD": 25.0,  # SPX points
}

SessionTypeStr = Literal[
    "pre_londres",
    "pre_ny",
    "ny_mid",
    "ny_close",
    "event_driven",
]


@dataclass(frozen=True)
class CalibrationResult:
    """Pure output of `compute_calibration_bins` — does NOT include DB
    side-effects. Caller persists separately via `persist_calibration`."""

    asset: str
    session_type: str
    bins_z_thresholds: list[float]  # = list(BUCKET_Z_THRESHOLDS)
    bins_pip_thresholds: list[float]  # per-asset translation
    sample_n: int
    sigma_pips: float
    """The rolling EWMA σ in pip/point units. NaN-safe ; falls back
    to `_FALLBACK_1SIG_PIPS[asset]` when sample_n < CONFIDENCE_FLOOR."""


def _ewma_std(returns: list[float], lam: float = EWMA_LAMBDA) -> float:
    """EWMA σ on log-returns. RiskMetrics 1996 convention — zero-mean
    return assumption, σ² uses raw r² throughout (no demeaning).

    σ²_t = (1 - λ) · r²_{t-1} + λ · σ²_{t-1}

    Bootstrapped with the simple mean-squared-return of the first 20%
    of the sample (or all of it if shorter), as is standard for
    cold-start EWMA per RiskMetrics Technical Document §2.2.
    """
    n = len(returns)
    if n == 0:
        return float("nan")
    if n < 2:
        # 1 observation → return raw magnitude (zero-mean convention).
        return abs(returns[0])

    bootstrap_len = max(2, n // 5)
    bootstrap = returns[:bootstrap_len]
    # RiskMetrics : raw r² (NO demeaning) — zero-mean return assumption.
    var = sum(r * r for r in bootstrap) / bootstrap_len

    # Iterate EWMA over remaining samples.
    for r in returns[bootstrap_len:]:
        var = (1.0 - lam) * (r * r) + lam * var

    return math.sqrt(var)


def compute_calibration_bins_from_returns(
    asset: str,
    session_type: SessionTypeStr,
    returns: list[float],
) -> CalibrationResult:
    """Pure compute — given realized log-returns, emit a CalibrationResult.

    Used by `compute_calibration_bins` (which reads from polygon_intraday)
    AND by unit tests (which stub returns directly without DB).

    `returns` is a list of session-window log-returns in their native
    asset unit (the function multiplies by the per-asset PIP_UNIT_FACTOR
    internally). Cold-start / sparse data falls back to the
    `_FALLBACK_1SIG_PIPS` table per asset.
    """
    sample_n = len(returns)
    unit_factor = _PIP_UNIT_FACTOR.get(asset, 1.0)

    if sample_n < CONFIDENCE_FLOOR:
        sigma_pips = _FALLBACK_1SIG_PIPS.get(asset, 30.0)
    else:
        sigma_native = _ewma_std(returns)
        if math.isnan(sigma_native) or sigma_native <= 0.0:
            sigma_pips = _FALLBACK_1SIG_PIPS.get(asset, 30.0)
        else:
            sigma_pips = sigma_native * unit_factor

    # Translate canonical z-thresholds to pip/point thresholds.
    bins_pip_thresholds = [z * sigma_pips for z in BUCKET_Z_THRESHOLDS]

    return CalibrationResult(
        asset=asset,
        session_type=session_type,
        bins_z_thresholds=list(BUCKET_Z_THRESHOLDS),
        bins_pip_thresholds=bins_pip_thresholds,
        sample_n=sample_n,
        sigma_pips=sigma_pips,
    )


async def fetch_session_window_returns(
    session: AsyncSession,
    asset: str,
    *,
    window_days: int = ROLLING_WINDOW_DAYS,
    now: datetime | None = None,
) -> list[float]:
    """Read session-window log-returns from polygon_intraday.

    Computes a simple close-to-close 12h-session log-return per
    rolling trading-day from `polygon_intraday.close`. Returns are in
    the asset's native unit (raw log-return) — `compute_calibration_
    bins_from_returns` handles the unit translation.

    Conservative approach for W105b : we don't yet split by
    session_type in the historical computation — the same calibration
    is reused across all 5 windows. A future W105b+ can split by
    window if the data justifies (very few assets have meaningfully
    distinct session-window variance distributions).
    """
    now = now or datetime.now(UTC)
    cutoff = now - _timedelta_days(window_days)

    stmt = (
        select(PolygonIntradayBar.bar_ts, PolygonIntradayBar.close)
        .where(PolygonIntradayBar.asset == asset)
        .where(PolygonIntradayBar.bar_ts >= cutoff)
        .order_by(PolygonIntradayBar.bar_ts.asc())
    )
    result = await session.execute(stmt)
    rows = result.all()
    if len(rows) < 2:
        return []

    # Daily-close approximation : pick the last close of each calendar
    # day. For a 252-day window with 1-min bars this gives ~252 daily
    # log-returns — enough for a stable EWMA.
    daily_close: dict[str, float] = {}
    for bar_ts, close in rows:
        day_key = bar_ts.date().isoformat()
        daily_close[day_key] = close  # last-write wins = end-of-day

    closes = list(daily_close.values())
    if len(closes) < 2:
        return []

    returns: list[float] = []
    for i in range(1, len(closes)):
        c_prev, c_curr = closes[i - 1], closes[i]
        if c_prev > 0.0 and c_curr > 0.0:
            returns.append(math.log(c_curr / c_prev))
    return returns


def _timedelta_days(days: int):
    """Avoid importing timedelta at module level — defensive."""
    from datetime import timedelta

    return timedelta(days=days)


async def compute_calibration_bins(
    session: AsyncSession,
    asset: str,
    session_type: SessionTypeStr,
    *,
    now: datetime | None = None,
) -> CalibrationResult:
    """End-to-end : read returns → compute CalibrationResult."""
    returns = await fetch_session_window_returns(session, asset, now=now)
    return compute_calibration_bins_from_returns(asset, session_type, returns)


async def persist_calibration(
    session: AsyncSession,
    result: CalibrationResult,
    *,
    computed_at: datetime | None = None,
) -> ScenarioCalibrationBins:
    """Insert a new ScenarioCalibrationBins row (append-only by design ;
    PK includes `computed_at` so concurrent writes are safe)."""
    row = ScenarioCalibrationBins(
        asset=result.asset,
        session_type=result.session_type,
        computed_at=computed_at or datetime.now(UTC),
        bins_z_thresholds=result.bins_z_thresholds,
        bins_pip_thresholds=result.bins_pip_thresholds,
        sample_n=result.sample_n,
    )
    session.add(row)
    await session.flush()
    return row


def format_calibration_block(result: CalibrationResult) -> str:
    """Render a Pass-6 prompt-friendly calibration block from a
    CalibrationResult — used by `cli/run_session_card.py` to inject
    pre-computed thresholds into the Pass-6 prompt's CALIBRATION
    section."""
    z_thresholds = result.bins_z_thresholds
    pip_thresholds = result.bins_pip_thresholds
    rows = [
        f"  - z={z:+.2f} → {pip:+.1f} {_unit_label(result.asset)}"
        for z, pip in zip(z_thresholds, pip_thresholds, strict=True)
    ]
    return (
        f"Per-asset rolling 252d (EWMA λ={EWMA_LAMBDA}) calibration for "
        f"{result.asset}/{result.session_type} :\n"
        f"  - σ = {result.sigma_pips:.2f} {_unit_label(result.asset)} "
        f"(sample_n = {result.sample_n})\n"
        f"  - z-threshold → magnitude mapping :\n" + "\n".join(rows)
    )


def _unit_label(asset: str) -> str:
    if asset in {"NAS100_USD", "SPX500_USD"}:
        return "points"
    if asset == "XAU_USD":
        return "USD"
    return "pips"
