"""TERM_PREMIUM_INTRADAY_30D — intra-month acute companion to TERM_PREMIUM_REPRICING.

Phase E completeness — completes the 30d/90d/252d trinity for fiscal stress
detection :

| Alert                            | Window | Severity | Cadence       | ADR     |
| -------------------------------- | ------ | -------- | ------------- | ------- |
| TERM_PREMIUM_INTRADAY_30D ✨ NEW | 30d    | warning  | daily 22:25   | ADR-052 |
| TERM_PREMIUM_REPRICING            | 90d    | warning  | daily 22:30   | ADR-041 |
| TERM_PREMIUM_STRUCTURAL_252D     | 252d   | info     | weekly Sun    | ADR-045 |

The 30d window catches **intra-month event-driven shifts** that the 90d
window dampens (auction-tail surprise, debt-ceiling cliff, FOMC press
conference reaction, USTR tariff escalation, Fed-independence headline).

Per Phase E doctrine (cf GEOPOL_FLASH 30d / GEOPOL_REGIME_STRUCTURAL 252d
sister-pair pattern, ADR-039) : multiple windows on the same series provide
**signal stacking** for the trader — fast (intraday/event), tactical (90d),
structural (252d).

ADR-052. Catalog 53 → 54.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import FredObservation
from .alerts_runner import check_metric

# 30d window — catches intra-month event-driven shifts.
ZSCORE_WINDOW_DAYS = 30

# Phase E threshold convention.
ALERT_Z_ABS_FLOOR: float = 2.0

# Minimum sample for credible z-score.
_MIN_ZSCORE_HISTORY = 20

# FRED series — same Kim-Wright 10y term premium as sister 90d/252d alerts.
SERIES_ID = "THREEFYTP10"


@dataclass(frozen=True)
class TermPremiumIntradayResult:
    """One run summary."""

    term_premium_pct: float | None
    term_premium_z: float | None
    baseline_mean: float | None
    baseline_std: float | None
    n_history: int
    regime: str
    """'expansion' (z > +floor) | 'contraction' (z < -floor) | '' """
    alert_fired: bool
    note: str = ""


async def _fetch_recent_observations(
    session: AsyncSession,
    *,
    days: int,
) -> list[tuple[datetime, float]]:
    """Pull last `days` observations for THREEFYTP10, oldest-first."""
    cutoff = datetime.now(UTC).date() - timedelta(days=days)
    stmt = (
        select(FredObservation.observation_date, FredObservation.value)
        .where(
            FredObservation.series_id == SERIES_ID,
            FredObservation.observation_date >= cutoff,
            FredObservation.value.is_not(None),
        )
        .order_by(desc(FredObservation.observation_date))
    )
    rows = list((await session.execute(stmt)).all())
    rows.reverse()
    return [(r[0], float(r[1])) for r in rows]


def _zscore(
    history: list[float], current: float
) -> tuple[float | None, float | None, float | None]:
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
        return "contraction"
    return ""


async def evaluate_term_premium_intraday(
    session: AsyncSession,
    *,
    persist: bool = True,
) -> TermPremiumIntradayResult:
    """Compute z-score of latest THREEFYTP10 vs trailing 30d distribution,
    fire TERM_PREMIUM_INTRADAY_30D when |z| >= 2.0."""
    observations = await _fetch_recent_observations(session, days=ZSCORE_WINDOW_DAYS + 14)

    if not observations:
        return TermPremiumIntradayResult(
            term_premium_pct=None,
            term_premium_z=None,
            baseline_mean=None,
            baseline_std=None,
            n_history=0,
            regime="",
            alert_fired=False,
            note="no THREEFYTP10 observations available",
        )

    latest_date, current = observations[-1]
    history_values = [v for _, v in observations[:-1][-ZSCORE_WINDOW_DAYS:]]

    z, mean, std = _zscore(history_values, current)
    regime = _classify_regime(z)

    note = (
        f"term_premium_30d · {current:+.4f}% on "
        f"{latest_date.date() if hasattr(latest_date, 'date') else latest_date} "
    )
    if z is None:
        if mean is None:
            note += f"(insufficient history: {len(history_values)}d, need >= {_MIN_ZSCORE_HISTORY})"
        else:
            note += f"baseline={mean:+.4f}%±0.0000% z=None (zero std)"
    else:
        note += f"baseline={mean:+.4f}%±{std:.4f}% z={z:+.2f} regime={regime or 'normal'}"

    alert_fired = False
    if z is not None and abs(z) >= ALERT_Z_ABS_FLOOR and persist:
        await check_metric(
            session,
            metric_name="term_premium_z_30d",
            current_value=z,
            asset=None,
            extra_payload={
                "source": f"FRED:{SERIES_ID}",
                "term_premium_pct": round(current, 4),
                "term_premium_bps": round(current * 100, 1),
                "baseline_mean_pct": round(mean, 4) if mean is not None else None,
                "baseline_std_pct": round(std, 4) if std is not None else None,
                "n_history": len(history_values),
                "window_days": ZSCORE_WINDOW_DAYS,
                "regime": regime,
                "observation_date": str(
                    latest_date.date() if hasattr(latest_date, "date") else latest_date
                ),
                "methodology": "KW 10y term premium z-score vs trailing 30d (intra-month acute)",
                "sister_alerts": [
                    "TERM_PREMIUM_REPRICING (90d tactical)",
                    "TERM_PREMIUM_STRUCTURAL_252D (252d structural)",
                ],
            },
        )
        alert_fired = True

    return TermPremiumIntradayResult(
        term_premium_pct=round(current, 4),
        term_premium_z=round(z, 3) if z is not None else None,
        baseline_mean=round(mean, 4) if mean is not None else None,
        baseline_std=round(std, 4) if std is not None else None,
        n_history=len(history_values),
        regime=regime,
        alert_fired=alert_fired,
        note=note,
    )
