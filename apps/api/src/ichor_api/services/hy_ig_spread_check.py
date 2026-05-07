"""HY_IG_SPREAD_DIVERGENCE alert wiring (Phase E completeness).

Detects credit-cycle inflection by tracking the **HY-IG spread differential**
(BAMLH0A0HYM2 minus BAMLC0A0CM, both ICE BofA option-adjusted spreads in %).

Why this matters
================

The HY-IG spread differential is the canonical credit-cycle gauge :
- Compression (z << 0) : IG widens FASTER than HY = institutional flight-to-
  quality / EARLY recession warning (paradoxically — investors rotate from
  IG to safer assets while HY is bid by yield-hunters)
- Expansion (z >> 0) : HY widens FASTER than IG = late-cycle credit stress,
  high-yield issuers losing access to capital, default rates rising

Per Federal Reserve research + Macrosynergy 2024 + InvestmentGrade Q1 2026
Outlook : the HY-IG differential historically front-runs HY OAS spikes by
2-4 weeks. A spike in the differential is the clearest free-data risk-on/
risk-off pivot signal.

Both source series are already collected in `collectors/fred_extended.py`
EXTENDED_SERIES_TO_POLL : `BAMLH0A0HYM2` (HY OAS) + `BAMLC0A0CM` (IG OAS).
No new data feed required.

Architecture
============

1. Fetch last ~104d (90d window + 14d buffer) of BOTH series, inner-join
   by observation_date
2. Compute differential = HY - IG per day
3. Z-score current differential vs trailing 90d distribution
4. Fire when `|z| >= 2.0` (above threshold)
5. Regime classifier : 'expansion' (z > +2) / 'compression' (z < -2) / ''

Source-stamp (ADR-017) : `FRED:BAMLH0A0HYM2-BAMLC0A0CM`. Asset = None
(macro-broad credit signal). Severity warning.

ROADMAP Phase E completeness. ADR-049.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import FredObservation
from .alerts_runner import check_metric

# 90d window per Phase E convention. Captures credit-cycle inflection
# (typically 6-12 month cycles) without absorbing structural drift.
ZSCORE_WINDOW_DAYS = 90

# Phase E threshold convention (matches sister Phase E innovations).
ALERT_Z_ABS_FLOOR: float = 2.0

# Minimum sample for credible z-score.
_MIN_ZSCORE_HISTORY = 60

# Series IDs (FRED) — both already in fred_extended.py.
HY_OAS_SERIES_ID = "BAMLH0A0HYM2"
IG_OAS_SERIES_ID = "BAMLC0A0CM"


@dataclass(frozen=True)
class HyIgSpreadResult:
    """One run summary."""

    hy_oas_pct: float | None
    ig_oas_pct: float | None
    differential_pct: float | None
    """HY - IG in % (matching FRED reporting unit). 1.0% = 100 bps."""

    differential_z: float | None
    baseline_mean: float | None
    baseline_std: float | None
    n_history: int

    regime: str
    """'expansion' (z > +floor) | 'compression' (z < -floor) | '' otherwise."""

    alert_fired: bool
    note: str = ""


async def _fetch_recent_paired(
    session: AsyncSession,
    *,
    days: int,
) -> list[tuple[datetime, float, float]]:
    """Pull last `days` observations for HY_OAS and IG_OAS, inner-joined by
    observation_date. Returns list of (date, hy_oas, ig_oas) oldest-first.
    """
    cutoff = datetime.now(UTC).date() - timedelta(days=days)

    # Fetch HY OAS observations
    hy_stmt = (
        select(FredObservation.observation_date, FredObservation.value)
        .where(
            FredObservation.series_id == HY_OAS_SERIES_ID,
            FredObservation.observation_date >= cutoff,
            FredObservation.value.is_not(None),
        )
        .order_by(desc(FredObservation.observation_date))
    )
    hy_rows = (await session.execute(hy_stmt)).all()

    # Fetch IG OAS observations
    ig_stmt = (
        select(FredObservation.observation_date, FredObservation.value)
        .where(
            FredObservation.series_id == IG_OAS_SERIES_ID,
            FredObservation.observation_date >= cutoff,
            FredObservation.value.is_not(None),
        )
        .order_by(desc(FredObservation.observation_date))
    )
    ig_rows = (await session.execute(ig_stmt)).all()

    # Inner-join by date
    ig_by_date = {r[0]: float(r[1]) for r in ig_rows}
    paired: list[tuple[datetime, float, float]] = []
    for hy_date, hy_val in hy_rows:
        if hy_date in ig_by_date:
            paired.append((hy_date, float(hy_val), ig_by_date[hy_date]))

    paired.reverse()  # oldest-first
    return paired


def _zscore(history: list[float], current: float) -> tuple[float | None, float | None, float | None]:
    """Compute z = (current - mean(history)) / std(history). Returns
    (z, mean, std) — z=None if degenerate."""
    n = len(history)
    if n < _MIN_ZSCORE_HISTORY:
        return None, None, None
    mean = sum(history) / n
    var = sum((v - mean) ** 2 for v in history) / n
    std = math.sqrt(var)
    if std == 0:
        return None, mean, std
    return (current - mean) / std, mean, std


def _classify_regime(z: float | None, *, floor: float = ALERT_Z_ABS_FLOOR) -> str:
    """Map z-score → regime tag."""
    if z is None:
        return ""
    if z > floor:
        return "expansion"
    if z < -floor:
        return "compression"
    return ""


async def evaluate_hy_ig_spread_divergence(
    session: AsyncSession,
    *,
    persist: bool = True,
) -> HyIgSpreadResult:
    """Compute HY-IG spread differential z-score, fire HY_IG_SPREAD_DIVERGENCE
    when threshold crossed. Returns structured result for CLI 1-line punch."""
    paired = await _fetch_recent_paired(
        session, days=ZSCORE_WINDOW_DAYS + 14
    )

    if len(paired) < 2:
        return HyIgSpreadResult(
            hy_oas_pct=None,
            ig_oas_pct=None,
            differential_pct=None,
            differential_z=None,
            baseline_mean=None,
            baseline_std=None,
            n_history=0,
            regime="",
            alert_fired=False,
            note="insufficient paired observations (need >= 2)",
        )

    # Latest pair = current reading
    latest_date, hy_current, ig_current = paired[-1]
    differential_current = hy_current - ig_current

    # History = all but latest
    history_pairs = paired[:-1]
    history_diffs = [hy - ig for _, hy, ig in history_pairs[-ZSCORE_WINDOW_DAYS:]]

    z, mean, std = _zscore(history_diffs, differential_current)
    regime = _classify_regime(z)

    note = (
        f"HY-IG diff={differential_current:+.3f}% (HY={hy_current:.3f} IG={ig_current:.3f}) "
        f"on {latest_date.date() if hasattr(latest_date, 'date') else latest_date} "
    )
    if z is None:
        if mean is None:
            note += f"(insufficient history: {len(history_diffs)}d, need >= {_MIN_ZSCORE_HISTORY})"
        else:
            note += f"baseline={mean:.3f}%±0.000% z=None (zero std)"
    else:
        note += f"baseline={mean:+.3f}%±{std:.3f}% z={z:+.2f} regime={regime or 'normal'}"

    alert_fired = False
    if z is not None and abs(z) >= ALERT_Z_ABS_FLOOR and persist:
        await check_metric(
            session,
            metric_name="hy_ig_spread_z",
            current_value=z,
            asset=None,
            extra_payload={
                "source": f"FRED:{HY_OAS_SERIES_ID}-{IG_OAS_SERIES_ID}",
                "hy_oas_pct": round(hy_current, 4),
                "ig_oas_pct": round(ig_current, 4),
                "differential_pct": round(differential_current, 4),
                "differential_bps": round(differential_current * 100, 1),
                "baseline_mean_pct": round(mean, 4) if mean is not None else None,
                "baseline_std_pct": round(std, 4) if std is not None else None,
                "n_history": len(history_diffs),
                "regime": regime,
                "observation_date": str(
                    latest_date.date() if hasattr(latest_date, "date") else latest_date
                ),
                "methodology": "(HY_OAS - IG_OAS) z-score vs trailing 90d distribution",
            },
        )
        alert_fired = True

    return HyIgSpreadResult(
        hy_oas_pct=round(hy_current, 4),
        ig_oas_pct=round(ig_current, 4),
        differential_pct=round(differential_current, 4),
        differential_z=round(z, 3) if z is not None else None,
        baseline_mean=round(mean, 4) if mean is not None else None,
        baseline_std=round(std, 4) if std is not None else None,
        n_history=len(history_diffs),
        regime=regime,
        alert_fired=alert_fired,
        note=note,
    )
