"""MACRO_QUARTET_STRESS alert wiring (Phase E.4).

Composite stress-regime detector based on the **macro quartet** :

    DXY (DTWEXBGS)         — dollar strength / safe-haven flows
    10Y yield (DGS10)      — duration / fiscal stress
    VIX (VIXCLS)           — equity vol / fear gauge
    HY OAS (BAMLH0A0HYM2)  — credit stress / default risk

The original Ichor "macro trinity" (DXY + 10Y + VIX) covers liquidity +
duration + equity vol. Adding **HY OAS** as the 4th pillar closes the
**credit-stress dimension** — without which the trinity systematically
misses funding-stress regimes (March 2020 COVID, 2008 GFC) where credit
spreads blow out before equities catch up.

Per TORVAQ framework + OFR Financial Stress Index methodology, a stress
regime is best detected by **N ≥ 3 of 4 dimensions aligned** in extreme
territory. This filters out "single-axis" noise (e.g. VIX spike from
Volmageddon-style positioning unwind without credit confirmation) from
genuine systemic stress.

The alert :

  1. Fetches the last 100d of each FRED series (90d window + buffer)
  2. For each, computes z-score of latest reading vs trailing 89d
  3. Counts how many dimensions are |z| > 2.0 ("stressed extreme")
  4. Fires when count >= 3 (3-of-4 alignment)

Severity : warning. The alert flags regime-shift moments, not absolute
levels. A 3-of-4 alignment in the same direction (all 4 z's positive
= stress, all 4 z's negative = complacency) is informative even when
the absolute levels look benign in isolation.

Source-stamping (ADR-017) :
  - extra_payload.source = "FRED:DTWEXBGS+DGS10+VIXCLS+BAMLH0A0HYM2"
  - extra_payload includes per-dimension z-scores, signs, n_history
  - regime tag : 'stress' (positive z's) | 'complacency' (negative z's) |
    'mixed' (no directional alignment despite count >= 3)

ROADMAP E.4. ADR-042.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import FredObservation
from .alerts_runner import check_metric

# The 4 quartet dimensions. Order matters for output stability.
QUARTET_SERIES: tuple[tuple[str, str], ...] = (
    ("DTWEXBGS", "DXY"),  # Trade-weighted USD broad
    ("DGS10", "10Y"),  # 10-year Treasury yield
    ("VIXCLS", "VIX"),  # CBOE Volatility Index
    ("BAMLH0A0HYM2", "HY_OAS"),  # ICE BofA HY Option-Adjusted Spread
)

# Window parameter. 90d catches narrative-shift episodes (rate-vol
# repricing, credit-cycle inflections) without absorbing structural drift.
ZSCORE_WINDOW_DAYS = 90

# Z-score threshold per dimension. |z| > 2.0 = "extreme territory"
# (~1-in-20 day under approx normality).
PER_DIM_Z_FLOOR: float = 2.0

# Composite alignment threshold. ≥ 3 of 4 dimensions in extreme territory
# = 3-of-4 alignment — the classic TORVAQ + OFR FSI threshold.
ALERT_COUNT_FLOOR: int = 3

# Minimum sample for credible per-dimension z-score.
_MIN_ZSCORE_HISTORY = 60


@dataclass(frozen=True)
class DimensionState:
    """Per-dimension z-score reading."""

    series_id: str
    dim_label: str
    current_value: float | None
    z_score: float | None
    sign: int  # +1 if z > floor, -1 if z < -floor, 0 otherwise


@dataclass(frozen=True)
class MacroQuartetResult:
    """One run summary."""

    n_dimensions_evaluated: int
    n_stressed_extreme: int
    """Dimensions with |z| > PER_DIM_Z_FLOOR."""

    n_aligned_positive: int
    """Dimensions with z > +PER_DIM_Z_FLOOR (stress side)."""

    n_aligned_negative: int
    """Dimensions with z < -PER_DIM_Z_FLOOR (complacency side)."""

    regime: str
    """'stress' if N pos >= 3, 'complacency' if N neg >= 3, 'mixed' if
    extreme count >= 3 but no directional consensus, '' otherwise."""

    alert_fired: bool

    per_dim: list[DimensionState] = field(default_factory=list)

    note: str = ""


async def _fetch_series_history(
    session: AsyncSession,
    *,
    series_id: str,
    days: int,
) -> list[float]:
    """Pull last `days` observations for a given FRED series, oldest-first
    (last value = most recent reading)."""
    cutoff = datetime.now(UTC).date() - timedelta(days=days)
    stmt = (
        select(FredObservation.observation_date, FredObservation.value)
        .where(
            FredObservation.series_id == series_id,
            FredObservation.observation_date >= cutoff,
            FredObservation.value.is_not(None),
        )
        .order_by(desc(FredObservation.observation_date))
    )
    rows = list((await session.execute(stmt)).all())
    rows.reverse()
    return [float(r[1]) for r in rows if r[1] is not None]


def _zscore(history: list[float], current: float) -> float | None:
    """Compute z = (current - mean(history)) / std(history). Returns None
    on degenerate input (insufficient history or zero std)."""
    n = len(history)
    if n < _MIN_ZSCORE_HISTORY:
        return None
    mean = sum(history) / n
    var = sum((v - mean) ** 2 for v in history) / n
    std = math.sqrt(var)
    if std == 0:
        return None
    return (current - mean) / std


def _classify_regime(
    n_pos: int, n_neg: int, n_extreme: int, *, count_floor: int = ALERT_COUNT_FLOOR
) -> str:
    """Map (positive count, negative count, extreme count) → regime tag."""
    if n_pos >= count_floor:
        return "stress"
    if n_neg >= count_floor:
        return "complacency"
    if n_extreme >= count_floor:
        return "mixed"
    return ""


async def evaluate_macro_quartet(
    session: AsyncSession,
    *,
    persist: bool = True,
) -> MacroQuartetResult:
    """Compute z-scores for the 4 quartet dimensions, count alignment,
    fire MACRO_QUARTET_STRESS when N >= ALERT_COUNT_FLOOR.

    Returns a structured result so the CLI can print a one-liner.
    """
    per_dim: list[DimensionState] = []
    n_pos = 0
    n_neg = 0
    n_extreme = 0
    n_evaluated = 0

    for series_id, dim_label in QUARTET_SERIES:
        history_full = await _fetch_series_history(
            session, series_id=series_id, days=ZSCORE_WINDOW_DAYS + 14
        )
        if not history_full:
            per_dim.append(
                DimensionState(
                    series_id=series_id,
                    dim_label=dim_label,
                    current_value=None,
                    z_score=None,
                    sign=0,
                )
            )
            continue

        current = history_full[-1]
        history = history_full[:-1][-ZSCORE_WINDOW_DAYS:]
        z = _zscore(history, current)

        sign = 0
        if z is not None:
            n_evaluated += 1
            if z > PER_DIM_Z_FLOOR:
                n_pos += 1
                n_extreme += 1
                sign = 1
            elif z < -PER_DIM_Z_FLOOR:
                n_neg += 1
                n_extreme += 1
                sign = -1

        per_dim.append(
            DimensionState(
                series_id=series_id,
                dim_label=dim_label,
                current_value=round(current, 4),
                z_score=round(z, 3) if z is not None else None,
                sign=sign,
            )
        )

    regime = _classify_regime(n_pos, n_neg, n_extreme)
    breakdown = " ".join(
        f"{d.dim_label}={d.z_score if d.z_score is not None else 'n/a'}" for d in per_dim
    )
    note = (
        f"quartet evaluated={n_evaluated}/4 stressed_extreme={n_extreme} "
        f"(pos={n_pos} neg={n_neg}) regime={regime or 'normal'} | {breakdown}"
    )

    fired = False
    if n_extreme >= ALERT_COUNT_FLOOR and persist:
        await check_metric(
            session,
            metric_name="quartet_stress_count",
            current_value=float(n_extreme),
            asset=None,  # macro-broad
            extra_payload={
                "n_evaluated": n_evaluated,
                "n_stressed_extreme": n_extreme,
                "n_aligned_positive": n_pos,
                "n_aligned_negative": n_neg,
                "regime": regime,
                "per_dim": [
                    {
                        "series_id": d.series_id,
                        "dim_label": d.dim_label,
                        "current_value": d.current_value,
                        "z_score": d.z_score,
                        "sign": d.sign,
                    }
                    for d in per_dim
                ],
                "source": "FRED:" + "+".join(s for s, _ in QUARTET_SERIES),
            },
        )
        fired = True

    return MacroQuartetResult(
        n_dimensions_evaluated=n_evaluated,
        n_stressed_extreme=n_extreme,
        n_aligned_positive=n_pos,
        n_aligned_negative=n_neg,
        regime=regime,
        alert_fired=fired,
        per_dim=per_dim,
        note=note,
    )
