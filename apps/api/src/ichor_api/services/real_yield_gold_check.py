"""REAL_YIELD_GOLD_DIVERGENCE alert wiring (Phase D.5.c).

Gold and 10Y real yields (DFII10) are *historically inversely
correlated* — Δreal_yields ↑ ⇒ XAU ↓ — through the carry channel
(holding gold has zero yield ; if competing assets pay more, gold
demand falls). The long-run rolling-60d correlation lives around
-0.5 to -0.7 in normal regime.

When that correlation **diverges from its trailing distribution**
the gold market is no longer driven by real yields — it's responding
to something else (intervention, geopolitical premium, currency
debasement narrative, sovereign accumulation, etc). That divergence
is precisely the trader-actionable moment :

  - z-score of rolling 60d correlation against trailing 250d
    distribution
  - |z| > 2.0 ⇒ alert REAL_YIELD_GOLD_DIVERGENCE

This service is **pure** : it reads FRED observations from Postgres,
computes the rolling correlation + z-score, and fires the catalog
alert through `check_metric`. The FRED data ingestion lives in
`collectors/fred_extended.py` (DFII10 + GOLDAMGBD228NLBM are already
collected daily — cf cross_asset_heatmap §line 274).

Source-stamping (ADR-017) :
  - extra_payload.source = "FRED:DFII10+GOLDAMGBD228NLBM"
  - extra_payload includes current rolling correlation, baseline
    mean, baseline std, and the n_history used.

ROADMAP D.5.c. ADR-034.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import FredObservation
from .alerts_runner import check_metric

# Series identifiers (FRED). Gold London PM fix is the daily price
# series most commonly used for academic XAU studies — DFII10 is the
# 10Y TIPS real yield (constant maturity), the canonical gold-bench
# real-yield benchmark.
GOLD_SERIES_ID = "GOLDAMGBD228NLBM"
REAL_YIELD_SERIES_ID = "DFII10"

# Window parameters. 60d rolling correlation is the standard; the
# 250d distribution provides ~1y of trailing context for the z-score.
ROLLING_CORR_DAYS = 60
ZSCORE_LOOKBACK_DAYS = 250

# Threshold mirrors the catalog default (REAL_YIELD_GOLD_DIVERGENCE
# AlertDef default_threshold=2.0). Keep this constant in sync —
# enforced by test_threshold_constant_matches_catalog.
ALERT_Z_ABS_FLOOR: float = 2.0

# Minimum sample for a credible z-score on the rolling-correlation
# series. With 250 days lookback we expect ~190 valid rolling-corr
# observations after the warm-up period — be defensive.
_MIN_ZSCORE_HISTORY = 60


@dataclass(frozen=True)
class RealYieldGoldResult:
    """One run summary."""

    rolling_corr: float | None
    """Current 60d rolling correlation between XAU and DFII10."""
    baseline_mean: float | None
    """Mean of rolling correlations over the trailing 250d."""
    baseline_std: float | None
    """Std of rolling correlations over the trailing 250d."""
    z_score: float | None
    """How many σ the current rolling-corr is from baseline."""
    n_xau_obs: int
    n_dfii10_obs: int
    n_aligned_pairs: int
    n_zscore_history: int
    note: str = ""


async def _fetch_series(
    session: AsyncSession,
    *,
    series_id: str,
    days: int,
) -> list[tuple[date, float]]:
    """Daily observations for `series_id`, oldest-first, non-null values only."""
    cutoff = datetime.now(UTC).date() - timedelta(days=days)
    rows = (
        await session.execute(
            select(FredObservation.observation_date, FredObservation.value)
            .where(
                FredObservation.series_id == series_id,
                FredObservation.observation_date >= cutoff,
                FredObservation.value.is_not(None),
            )
            .order_by(FredObservation.observation_date.asc())
        )
    ).all()
    return [(r[0], float(r[1])) for r in rows if r[1] is not None]


def _aligned_pct_changes(
    xau: list[tuple[date, float]],
    yields: list[tuple[date, float]],
) -> tuple[list[date], list[float], list[float]]:
    """Inner-join two daily series on date, then compute :
       - XAU pct change (gold has level prices)
       - DFII10 first difference (yields are already %, level → diff)
    Returns (dates_aligned, xau_returns, yield_diffs) all of equal len.
    """
    xau_map = dict(xau)
    yield_map = dict(yields)
    common_dates = sorted(set(xau_map) & set(yield_map))
    if len(common_dates) < 2:
        return [], [], []

    out_dates: list[date] = []
    xau_rets: list[float] = []
    yield_diffs: list[float] = []
    prev_xau: float | None = None
    prev_yield: float | None = None
    for d in common_dates:
        x = xau_map[d]
        y = yield_map[d]
        if prev_xau is not None and prev_yield is not None and prev_xau > 0:
            xau_rets.append(math.log(x / prev_xau))  # log-return
            yield_diffs.append(y - prev_yield)
            out_dates.append(d)
        prev_xau = x
        prev_yield = y
    return out_dates, xau_rets, yield_diffs


def _rolling_corr(
    xau_rets: list[float],
    yield_diffs: list[float],
    *,
    window: int,
) -> list[float]:
    """Rolling Pearson correlation, output indexed at the END of each window."""
    n = len(xau_rets)
    if n < window or len(yield_diffs) != n:
        return []
    out: list[float] = []
    for end in range(window, n + 1):
        a = xau_rets[end - window : end]
        b = yield_diffs[end - window : end]
        ma = sum(a) / window
        mb = sum(b) / window
        cov = sum((a[i] - ma) * (b[i] - mb) for i in range(window)) / window
        va = sum((a[i] - ma) ** 2 for i in range(window)) / window
        vb = sum((b[i] - mb) ** 2 for i in range(window)) / window
        if va <= 0 or vb <= 0:
            continue
        rho = cov / math.sqrt(va * vb)
        out.append(rho)
    return out


def _zscore(values: list[float], current: float) -> tuple[float | None, float | None, float | None]:
    """(z, mean, std) of `current` against `values`. None on degenerate input."""
    n = len(values)
    if n < _MIN_ZSCORE_HISTORY:
        return None, None, None
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / n
    std = math.sqrt(var)
    if std == 0:
        return None, mean, std
    return (current - mean) / std, mean, std


async def evaluate_real_yield_gold_divergence(
    session: AsyncSession,
    *,
    persist: bool = True,
) -> RealYieldGoldResult:
    """Compute the rolling-correlation z-score and fire the alert when
    abs(z) > ALERT_Z_ABS_FLOOR.

    Returns a structured result so the CLI can print a one-liner.
    """
    # Pull ~5y of history so the 60d rolling-corr series has ~ 1200
    # observations and the trailing 250d distribution is well-formed.
    xau = await _fetch_series(session, series_id=GOLD_SERIES_ID, days=365 * 5)
    yields = await _fetch_series(session, series_id=REAL_YIELD_SERIES_ID, days=365 * 5)

    _, xau_rets, yield_diffs = _aligned_pct_changes(xau, yields)
    rolling = _rolling_corr(xau_rets, yield_diffs, window=ROLLING_CORR_DAYS)

    if not rolling:
        return RealYieldGoldResult(
            rolling_corr=None,
            baseline_mean=None,
            baseline_std=None,
            z_score=None,
            n_xau_obs=len(xau),
            n_dfii10_obs=len(yields),
            n_aligned_pairs=len(xau_rets),
            n_zscore_history=0,
            note=(
                f"insufficient aligned data : {len(xau_rets)} aligned pairs, "
                f"need >= {ROLLING_CORR_DAYS} for rolling-corr"
            ),
        )

    current = rolling[-1]
    baseline_window = rolling[-(ZSCORE_LOOKBACK_DAYS + 1) : -1]  # exclude today
    z, mean, std = _zscore(baseline_window, current)

    note = (
        f"rolling60d_corr={current:+.3f} baseline={mean:+.3f}±{std:.3f} z={z:+.2f}"
        if z is not None and mean is not None and std is not None
        else (
            f"rolling60d_corr={current:+.3f} (insufficient zscore history "
            f"{len(baseline_window)}d, need >= {_MIN_ZSCORE_HISTORY})"
        )
    )

    if z is not None and abs(z) >= ALERT_Z_ABS_FLOOR and persist:
        await check_metric(
            session,
            metric_name="real_yield_gold_div_z",
            current_value=z,
            asset="XAU_USD",  # alert is asset-specific to gold
            extra_payload={
                "rolling_corr": current,
                "baseline_mean": mean,
                "baseline_std": std,
                "n_zscore_history": len(baseline_window),
                "n_aligned_pairs": len(xau_rets),
                "source": f"FRED:{REAL_YIELD_SERIES_ID}+{GOLD_SERIES_ID}",
            },
        )

    return RealYieldGoldResult(
        rolling_corr=round(current, 4),
        baseline_mean=round(mean, 4) if mean is not None else None,
        baseline_std=round(std, 4) if std is not None else None,
        z_score=round(z, 3) if z is not None else None,
        n_xau_obs=len(xau),
        n_dfii10_obs=len(yields),
        n_aligned_pairs=len(xau_rets),
        n_zscore_history=len(baseline_window),
        note=note,
    )
