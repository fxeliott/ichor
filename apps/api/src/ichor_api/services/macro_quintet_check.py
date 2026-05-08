"""MACRO_QUINTET_STRESS alert wiring (Phase E completeness).

Upgrade of MACRO_QUARTET_STRESS (ADR-042) by adding **Treasury vol** as
the 5th dimension. Closes the explicit followup in ADR-048 §Followups :

    "MACRO_QUARTET_STRESS could become MACRO_QUINTET_STRESS by adding
     TREASURY_VOL_SPIKE z-score as 5th dimension."

The 5 dimensions cover all 5 axes of macro 2026 stress per OFR Financial
Stress Index methodology + TORVAQ four-invariants framework + Federal
Reserve supervisory stress test :

    DXY (DTWEXBGS)         — dollar strength / safe-haven flows
    10Y yield (DGS10)      — duration / fiscal stress
    VIX (VIXCLS)           — equity vol / fear gauge
    HY OAS (BAMLH0A0HYM2)  — credit stress / default risk
    Treasury vol (DGS10 30d realized x sqrt(252))  — bond vol regime ✨ NEW

Threshold : N >= 4 of 5 dimensions with |z| > 2.0 (4-of-5 alignment).
Stricter than the 3-of-4 quartet because adding a 5th independent axis
should NOT lower the bar to 4-of-5 simple count — we want HIGHER specificity
when 5 axes are available. Per academic literature (OFR FSI, Fed stress
test), 4-of-5 alignment in same direction = unmistakable systemic stress.

ADR-051. Phase E completeness.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import FredObservation
from .alerts_runner import check_metric

# 5 quintet dimensions. First 4 = original quartet ADR-042. 5th = Treasury vol.
# Order matters for output stability.
QUINTET_SERIES: tuple[tuple[str, str, str], ...] = (
    ("DTWEXBGS", "DXY", "level"),  # Trade-weighted USD broad
    ("DGS10", "10Y", "level"),  # 10-year Treasury yield level
    ("VIXCLS", "VIX", "level"),  # CBOE Volatility Index
    ("BAMLH0A0HYM2", "HY_OAS", "level"),  # ICE BofA HY OAS
    ("DGS10", "TREASURY_VOL", "realized_vol"),  # DGS10 30d realized vol annualized
)

# Window parameter — same as quartet for direct comparability.
ZSCORE_WINDOW_DAYS = 90

# Per-dim threshold (matches quartet).
PER_DIM_Z_FLOOR: float = 2.0

# Composite alignment threshold — 4-of-5 (stricter than quartet 3-of-4 to
# maintain specificity given 5 independent axes).
ALERT_COUNT_FLOOR: int = 4

# Minimum sample for credible per-dim z-score.
_MIN_ZSCORE_HISTORY = 60

# Realized-vol window (matches TREASURY_VOL_SPIKE / ADR-048 methodology).
_REALIZED_VOL_WINDOW = 30
_TRADING_DAYS_PER_YEAR = 252


@dataclass(frozen=True)
class DimensionState:
    """Per-dimension reading."""

    series_id: str
    dim_label: str
    extraction_mode: str  # "level" or "realized_vol"
    current_value: float | None
    z_score: float | None
    sign: int  # +1 if z > floor, -1 if z < -floor, 0 otherwise


@dataclass(frozen=True)
class MacroQuintetResult:
    """One run summary."""

    n_dimensions_evaluated: int
    n_stressed_extreme: int
    n_aligned_positive: int
    n_aligned_negative: int
    regime: str
    """'stress' | 'complacency' | 'mixed' | '' """
    alert_fired: bool
    per_dim: list[DimensionState] = field(default_factory=list)
    note: str = ""


async def _fetch_series_history(
    session: AsyncSession,
    *,
    series_id: str,
    days: int,
) -> list[float]:
    """Pull last `days` observations for a given FRED series, oldest-first."""
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
    """z = (current - mean(history)) / std(history) ; None on degenerate."""
    n = len(history)
    if n < _MIN_ZSCORE_HISTORY:
        return None
    mean = sum(history) / n
    var = sum((v - mean) ** 2 for v in history) / n
    std = math.sqrt(var)
    if std == 0:
        return None
    return (current - mean) / std


def _compute_realized_vol_series(levels: list[float]) -> list[float]:
    """Convert level series to rolling realized-vol-annualized series.

    For each window-position t with t >= window: compute log-changes on
    [t-window+1, t], stdev, annualize x sqrt(252). Returns realized-vol
    series (length = len(levels) - window).
    """
    if len(levels) < _REALIZED_VOL_WINDOW + 1:
        return []
    log_changes = []
    for i in range(1, len(levels)):
        if levels[i - 1] > 0 and levels[i] > 0:
            log_changes.append(math.log(levels[i] / levels[i - 1]))
        else:
            log_changes.append(0.0)
    rv_series = []
    for end in range(_REALIZED_VOL_WINDOW, len(log_changes) + 1):
        window = log_changes[end - _REALIZED_VOL_WINDOW : end]
        n = len(window)
        if n == 0:
            continue
        mean = sum(window) / n
        var = sum((v - mean) ** 2 for v in window) / n
        std = math.sqrt(var)
        rv_annualized = std * math.sqrt(_TRADING_DAYS_PER_YEAR) * 100  # in %
        rv_series.append(rv_annualized)
    return rv_series


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


async def evaluate_macro_quintet(
    session: AsyncSession,
    *,
    persist: bool = True,
) -> MacroQuintetResult:
    """Compute z-scores for the 5 quintet dimensions, count alignment,
    fire MACRO_QUINTET_STRESS when N >= ALERT_COUNT_FLOOR (4-of-5)."""
    per_dim: list[DimensionState] = []
    n_pos = 0
    n_neg = 0
    n_extreme = 0
    n_evaluated = 0

    for series_id, dim_label, mode in QUINTET_SERIES:
        # Fetch enough history for the longest needed buffer
        # (realized_vol needs ZSCORE_WINDOW + REALIZED_VOL_WINDOW + extra).
        fetch_days = ZSCORE_WINDOW_DAYS + _REALIZED_VOL_WINDOW + 30
        history_full = await _fetch_series_history(
            session, series_id=series_id, days=fetch_days
        )

        if not history_full:
            per_dim.append(
                DimensionState(
                    series_id=series_id,
                    dim_label=dim_label,
                    extraction_mode=mode,
                    current_value=None,
                    z_score=None,
                    sign=0,
                )
            )
            continue

        if mode == "level":
            current = history_full[-1]
            history = history_full[:-1][-ZSCORE_WINDOW_DAYS:]
            z = _zscore(history, current)
        elif mode == "realized_vol":
            rv_series = _compute_realized_vol_series(history_full)
            if not rv_series:
                per_dim.append(
                    DimensionState(
                        series_id=series_id,
                        dim_label=dim_label,
                        extraction_mode=mode,
                        current_value=None,
                        z_score=None,
                        sign=0,
                    )
                )
                continue
            current = rv_series[-1]
            history = rv_series[:-1][-ZSCORE_WINDOW_DAYS:]
            z = _zscore(history, current)
        else:
            raise ValueError(f"Unknown extraction mode: {mode!r}")

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
                extraction_mode=mode,
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
        f"quintet evaluated={n_evaluated}/5 stressed_extreme={n_extreme} "
        f"(pos={n_pos} neg={n_neg}) regime={regime or 'normal'} | {breakdown}"
    )

    alert_fired = False
    if n_extreme >= ALERT_COUNT_FLOOR and persist:
        await check_metric(
            session,
            metric_name="quintet_stress_count",
            current_value=float(n_extreme),
            asset=None,
            extra_payload={
                "source": "FRED:DTWEXBGS+DGS10+VIXCLS+BAMLH0A0HYM2+DGS10_realized_vol",
                "n_dimensions_evaluated": n_evaluated,
                "n_stressed_extreme": n_extreme,
                "n_aligned_positive": n_pos,
                "n_aligned_negative": n_neg,
                "regime": regime,
                "per_dim": [
                    {
                        "series_id": d.series_id,
                        "dim_label": d.dim_label,
                        "extraction_mode": d.extraction_mode,
                        "current_value": d.current_value,
                        "z_score": d.z_score,
                        "sign": d.sign,
                    }
                    for d in per_dim
                ],
                "methodology": (
                    "5-dim z-score alignment count (DXY+10Y+VIX+HY OAS levels, "
                    "DGS10 30d realized vol annualized). Threshold N>=4/5."
                ),
            },
        )
        alert_fired = True

    return MacroQuintetResult(
        n_dimensions_evaluated=n_evaluated,
        n_stressed_extreme=n_extreme,
        n_aligned_positive=n_pos,
        n_aligned_negative=n_neg,
        regime=regime,
        alert_fired=alert_fired,
        per_dim=per_dim,
        note=note,
    )
