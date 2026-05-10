"""Risk-reversal 25-delta z-score wiring for RISK_REVERSAL_25D alert.

Wires the previously DORMANT `RISK_REVERSAL_25D` alert (catalog
metric `rr25_z`, threshold ≥ 2.0). RR25 is the *25-delta risk
reversal* — call IV minus put IV at strikes ≈ spot ± 5 %, an
options-market measure of skew preference :

  RR25 > 0  →  calls bid up vs puts (bullish skew)
  RR25 < 0  →  puts bid up vs calls (hedging demand, downside risk)

A 2-sigma z-score deviation against the rolling 60-trading-day
distribution is the textbook contrarian signal — the market has
crowded into one side of the book.

This module is pure : it persists a single (asset, rr25_pct) point
into `fred_observations` (series_id = `RR25_<ASSET>`) and then
reads back the rolling 60d window to compute the z-score and fire
the catalog alert. The yfinance fetching lives in the CLI runner
(`cli/run_rr25_check.py`) so unit tests don't touch the network.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import FredObservation
from .alerts_runner import check_metric

# Ticker → Phase-1 asset symbol used in the catalog. Keep this map
# minimal — adding a new asset means adding both a yfinance ticker
# and the corresponding ALERT_TRIGGER_SERIES wiring.
TICKER_TO_ASSET: dict[str, str] = {
    "SPY": "SPX500_USD",
    "QQQ": "NAS100_USD",
    "GLD": "XAU_USD",
}


@dataclass(frozen=True)
class Rr25CheckResult:
    asset: str
    series_id: str
    rr25_pct: float
    """Today's RR25 in pct points (e.g. -0.0123 = -1.23 %)."""

    n_history: int
    z_score: float | None
    """None when n_history < 30 (minimum sample for a credible z)."""

    note: str = ""


_MIN_HISTORY = 30
_LOOKBACK_DAYS = 90  # ~ 60 trading days


async def _persist_rr25(session: AsyncSession, *, series_id: str, value: float) -> None:
    """Idempotent insert keyed on (series_id, observation_date).

    We don't dedupe on full upsert because the catalog rolling z-score
    is sensitive to multiple-points-per-day if the runner is invoked
    twice. The collector schedule is twice-daily (14h + 21h30 Paris)
    so we de-duplicate on `observation_date`.
    """
    today = datetime.now(UTC).date()
    existing = await session.execute(
        select(FredObservation.id)
        .where(
            FredObservation.series_id == series_id,
            FredObservation.observation_date == today,
        )
        .limit(1)
    )
    if existing.scalar_one_or_none() is not None:
        # Update in place rather than insert duplicate.
        from sqlalchemy import update

        await session.execute(
            update(FredObservation)
            .where(
                FredObservation.series_id == series_id,
                FredObservation.observation_date == today,
            )
            .values(value=value, fetched_at=datetime.now(UTC))
        )
        return
    now = datetime.now(UTC)
    session.add(
        FredObservation(
            id=uuid4(),
            created_at=now,
            series_id=series_id,
            observation_date=today,
            value=value,
            fetched_at=now,
        )
    )


async def _read_history(
    session: AsyncSession, *, series_id: str, days: int = _LOOKBACK_DAYS
) -> list[float]:
    """Pull the last `days` observations of `series_id` ordered by
    date, oldest first."""
    cutoff = datetime.now(UTC).date() - timedelta(days=days)
    rows = (
        await session.execute(
            select(FredObservation.value)
            .where(
                FredObservation.series_id == series_id,
                FredObservation.observation_date >= cutoff,
                FredObservation.value.is_not(None),
            )
            .order_by(FredObservation.observation_date.asc())
        )
    ).all()
    return [float(r[0]) for r in rows]


def _zscore(values: list[float], current: float) -> float | None:
    """Population z-score of `current` against `values`. None when
    sample is too small or std is zero (degenerate)."""
    n = len(values)
    if n < _MIN_HISTORY:
        return None
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / n
    std = math.sqrt(var)
    if std == 0:
        return None
    return (current - mean) / std


async def evaluate_rr25(
    session: AsyncSession,
    *,
    asset: str,
    rr25_pct: float,
    persist: bool = True,
) -> Rr25CheckResult:
    """Persist today's RR25 for `asset`, compute the rolling z-score,
    and fire `RISK_REVERSAL_25D` if the z exceeds the catalog threshold.

    Returns the structured result so the caller can log / dashboard.
    """
    series_id = f"RR25_{asset}"
    if persist:
        await _persist_rr25(session, series_id=series_id, value=rr25_pct)
        await session.flush()

    history = await _read_history(session, series_id=series_id)
    # Exclude today's value from the distribution we z-score against,
    # otherwise the latest point pulls the mean toward itself and
    # under-states the deviation.
    history_excl_today = history[:-1] if len(history) >= 1 else []
    z = _zscore(history_excl_today, rr25_pct)

    note = (
        f"RR25 {asset} = {rr25_pct:+.4f} ({len(history_excl_today)} d hist, z={z:+.2f})"
        if z is not None
        else f"RR25 {asset} = {rr25_pct:+.4f} (insufficient history "
        f"{len(history_excl_today)} d, need ≥ {_MIN_HISTORY})"
    )

    if z is not None and persist:
        await check_metric(
            session,
            metric_name="rr25_z",
            current_value=z,
            asset=asset,
            extra_payload={"rr25_pct": rr25_pct, "n_history": len(history_excl_today)},
        )

    return Rr25CheckResult(
        asset=asset,
        series_id=series_id,
        rr25_pct=rr25_pct,
        n_history=len(history_excl_today),
        z_score=z,
        note=note,
    )
