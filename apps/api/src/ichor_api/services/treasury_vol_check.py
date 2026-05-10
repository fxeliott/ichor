"""TREASURY_VOL_SPIKE alert wiring (Phase E innovation, MOVE Index proxy).

Closes the followup gap from MACRO_QUARTET_STRESS (ADR-042) — the
original macro quartet missed the **MOVE Index dimension** because
FRED doesn't host the actual ICE BofAML MOVE Index. We construct a
**realized-vol proxy** from FRED:DGS10 daily changes :

    realized_vol_30d_annualized
        = stdev(daily_diff_in_pct[-30:]) × √252

Where daily_diff = DGS10[t] - DGS10[t-1] (yield change in pct, e.g.
+0.05 = +5 bps).

The methodology follows industry standard for converting realized vol
of a yield series to an annualized number comparable to MOVE :

  - Daily yield changes in pct (FRED units)
  - 30-day rolling stdev
  - × √252 to annualize (252 trading days/year)

We then z-score the latest realized-vol vs trailing 252d distribution
to catch *acceleration* — fires when |z| ≥ 2.0.

Why a proxy and not actual MOVE :
  - Actual MOVE = ICE BofAML implied vol from 1m-tenor swaptions on
    2y/5y/10y/30y Treasuries. Bloomberg / Cboe DataShop only.
  - Realized vol is a 1-month-lagged backward-looking proxy. Implied
    vs realized divergence is itself a signal (vol risk premium) but
    that's v2 work.
  - For Ichor's purpose (regime detection), realized-vol z-score
    captures the *direction of stress* well enough.

Industry-standard MOVE thresholds (for context) :
  - <80 = calm bond market
  - 80-120 = typical uncertainty
  - >120 = moderate stress
  - >150 = high stress
  - 2008 GFC peak ~264
  - March 2023 SVB crisis ~200
  - October 2025 ~69 = ultra-calm
  - April 2026 ~70 = complacency continues
  - Long-run mean ~103

For a realized-vol proxy with similar units, comparable stress
thresholds adjusted for the implied-vs-realized lag.

Source-stamping (ADR-017) :
  - extra_payload.source = "FRED:DGS10"
  - extra_payload includes realized_vol_30d_annualized (in bps),
    z-score, regime tag, n_history

ROADMAP E innovations. ADR-048.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import FredObservation
from .alerts_runner import check_metric

DGS10_SERIES_ID = "DGS10"

# Realized-vol window: 30 calendar days (= ~22 trading days). Common
# convention for 1-month MOVE comparison.
REALIZED_VOL_WINDOW_DAYS = 30

# Z-score window: 252 trading days = 1 year. Captures structural
# stress regime context.
ZSCORE_WINDOW_DAYS = 252

# Threshold (catalog-level constant, mirrored).
ALERT_Z_ABS_FLOOR: float = 2.0

# Trading-days-per-year scaling factor for annualization.
TRADING_DAYS_PER_YEAR = 252

# Minimum sample for credible z-score on the 252d window.
_MIN_ZSCORE_HISTORY = 180

# Minimum sample for credible 30d realized-vol calculation.
_MIN_REALIZED_VOL_HISTORY = 22


@dataclass(frozen=True)
class TreasuryVolResult:
    """One run summary."""

    realized_vol_30d_pct: float | None
    """Latest annualized 30d realized vol (in pct, FRED units)."""

    realized_vol_30d_bps: float | None
    """Same in bps (= pct * 100)."""

    z_score: float | None
    """How many σ above/below trailing 252d realized-vol distribution."""

    baseline_mean: float | None
    baseline_std: float | None

    n_history: int

    regime: str = ""
    """'stress' if z > floor (vol rising), 'complacency' if z < -floor
    (vol crushing), '' otherwise."""

    alert_fired: bool = False
    note: str = ""

    related_assets: list[str] = field(default_factory=list)


def _annualized_realized_vol(daily_changes_pct: list[float]) -> float | None:
    """Annualized stdev of daily yield changes (in pct units).

    Returns None if < _MIN_REALIZED_VOL_HISTORY samples.
    """
    if len(daily_changes_pct) < _MIN_REALIZED_VOL_HISTORY:
        return None
    n = len(daily_changes_pct)
    mean = sum(daily_changes_pct) / n
    var = sum((x - mean) ** 2 for x in daily_changes_pct) / max(1, n - 1)
    daily_std = math.sqrt(var)
    return daily_std * math.sqrt(TRADING_DAYS_PER_YEAR)


def _zscore(
    history: list[float], current: float
) -> tuple[float | None, float | None, float | None]:
    """(z, mean, std). None on degenerate input."""
    n = len(history)
    if n < _MIN_ZSCORE_HISTORY:
        return None, None, None
    mean = sum(history) / n
    var = sum((v - mean) ** 2 for v in history) / n
    std = math.sqrt(var)
    if std == 0:
        return None, mean, std
    return (current - mean) / std, mean, std


def _classify_regime(z: float | None) -> str:
    """Map z-score to régime tag."""
    if z is None or abs(z) < ALERT_Z_ABS_FLOOR:
        return ""
    return "stress" if z > 0 else "complacency"


async def _fetch_dgs10_history(session: AsyncSession, *, days: int) -> list[float]:
    """Pull last `days` DGS10 observations, oldest-first (last = most recent)."""
    cutoff = datetime.now(UTC).date() - timedelta(days=days)
    stmt = (
        select(FredObservation.observation_date, FredObservation.value)
        .where(
            FredObservation.series_id == DGS10_SERIES_ID,
            FredObservation.observation_date >= cutoff,
            FredObservation.value.is_not(None),
        )
        .order_by(desc(FredObservation.observation_date))
    )
    rows = list((await session.execute(stmt)).all())
    rows.reverse()
    return [float(r[1]) for r in rows if r[1] is not None]


def _rolling_realized_vols(daily_changes_pct: list[float], *, window: int) -> list[float]:
    """Rolling realized vols. Each entry is annualized stdev over a
    `window`-sample slice. Returns list aligned to slice end-points."""
    n = len(daily_changes_pct)
    if n < window:
        return []
    out: list[float] = []
    for end in range(window, n + 1):
        slice_changes = daily_changes_pct[end - window : end]
        rv = _annualized_realized_vol(slice_changes)
        if rv is not None:
            out.append(rv)
    return out


async def evaluate_treasury_vol(
    session: AsyncSession,
    *,
    persist: bool = True,
) -> TreasuryVolResult:
    """Compute 30d realized vol of DGS10, z-score against trailing 252d
    distribution, fire TREASURY_VOL_SPIKE when |z| ≥ 2.0.
    """
    # Pull ~2y of history so we have 252d of rolling realized-vols + 30d window.
    raw_yields = await _fetch_dgs10_history(
        session, days=ZSCORE_WINDOW_DAYS + REALIZED_VOL_WINDOW_DAYS + 14
    )

    if len(raw_yields) < REALIZED_VOL_WINDOW_DAYS + 1:
        return TreasuryVolResult(
            realized_vol_30d_pct=None,
            realized_vol_30d_bps=None,
            z_score=None,
            baseline_mean=None,
            baseline_std=None,
            n_history=len(raw_yields),
            note=(
                f"insufficient DGS10 data ({len(raw_yields)} rows) — verify "
                f"ichor-collector-fred_extended.timer is active"
            ),
        )

    # Daily first-differences (today - yesterday in pct units, FRED native)
    daily_changes = [raw_yields[i] - raw_yields[i - 1] for i in range(1, len(raw_yields))]

    # Rolling realized vol series — each entry is 30d-window stdev × √252
    rolling_rv = _rolling_realized_vols(daily_changes, window=REALIZED_VOL_WINDOW_DAYS)
    if not rolling_rv:
        return TreasuryVolResult(
            realized_vol_30d_pct=None,
            realized_vol_30d_bps=None,
            z_score=None,
            baseline_mean=None,
            baseline_std=None,
            n_history=0,
            note=(
                f"unable to compute rolling realized vol — "
                f"{len(daily_changes)} diffs, need >= {REALIZED_VOL_WINDOW_DAYS}"
            ),
        )

    current_rv = rolling_rv[-1]
    history_rv = rolling_rv[:-1][-ZSCORE_WINDOW_DAYS:]
    z, mean, std = _zscore(history_rv, current_rv)

    if z is None:
        note = (
            f"realized_vol_30d={current_rv:.4f}% (= {current_rv * 100:.1f} bps "
            f"annualized) on {len(rolling_rv)} samples (insufficient z-score "
            f"history {len(history_rv)}d, need >= {_MIN_ZSCORE_HISTORY})"
        )
        return TreasuryVolResult(
            realized_vol_30d_pct=round(current_rv, 4),
            realized_vol_30d_bps=round(current_rv * 100, 1),
            z_score=None,
            baseline_mean=mean,
            baseline_std=std,
            n_history=len(history_rv),
            note=note,
        )

    regime = _classify_regime(z)
    note = (
        f"realized_vol_30d={current_rv:.4f}% (= {current_rv * 100:.1f} bps "
        f"annualized) baseline_252d={mean:.4f}±{std:.4f} z={z:+.2f} "
        f"regime={regime or 'normal'}"
    )

    fired = False
    related = []
    if abs(z) >= ALERT_Z_ABS_FLOOR and persist:
        # Treasury vol regime affects: bonds (TLT/IEF), USD (haven on
        # stress / weak on complacency), gold (haven), credit (HY OAS
        # widens on Treasury vol stress).
        related = (
            ["DGS10", "DXY", "XAU_USD", "BAMLH0A0HYM2"]
            if regime == "stress"
            else ["DGS10", "BAMLC0A0CM", "VIXCLS"]
        )
        await check_metric(
            session,
            metric_name="treasury_realized_vol_z",
            current_value=z,
            asset=None,
            extra_payload={
                "realized_vol_30d_pct": current_rv,
                "realized_vol_30d_bps": current_rv * 100,
                "baseline_mean": mean,
                "baseline_std": std,
                "n_history": len(history_rv),
                "window_realized_vol": REALIZED_VOL_WINDOW_DAYS,
                "window_zscore": ZSCORE_WINDOW_DAYS,
                "regime": regime,
                "related_assets": related,
                "source": f"FRED:{DGS10_SERIES_ID}",
            },
        )
        fired = True

    return TreasuryVolResult(
        realized_vol_30d_pct=round(current_rv, 4),
        realized_vol_30d_bps=round(current_rv * 100, 1),
        z_score=round(z, 3),
        baseline_mean=round(mean, 4) if mean is not None else None,
        baseline_std=round(std, 4) if std is not None else None,
        n_history=len(history_rv),
        regime=regime,
        alert_fired=fired,
        note=note,
        related_assets=related,
    )
