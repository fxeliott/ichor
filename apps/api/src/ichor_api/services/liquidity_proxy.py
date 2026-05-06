"""Liquidity proxy = RRP overnight usage + Treasury General Account.

Wires the previously DORMANT `LIQUIDITY_TIGHTENING` alert (catalog.py
metric `liq_proxy_d`, threshold ≤ -200 below). The proxy combines :

  - **RRP** (Reverse Repo overnight, FRED `RRPONTSYD` in $bn)
  - **TGA** (Treasury General Account close, FRED `DTS_TGA_CLOSE`
    persisted by the dts_treasury collector, in $mn → /1000 → $bn)

`liq_proxy_t = RRP_t + TGA_t / 1000` (both in $bn).

The delta `liq_proxy_d = liq_proxy_t - liq_proxy_(t-N)` (default
N=5 business days) is what the alert thresholds against : a 200 $bn
drop in 5 trading days is the textbook "the Treasury / Fed is
draining cash from money markets" signal — historically precedes
funding-rate spikes by ~1-2 weeks.

Reads only ; persistence + alert firing live in
`cli/run_liquidity_check.py` so this module stays unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import FredObservation


@dataclass(frozen=True)
class LiquidityProxyReading:
    """Snapshot of RRP + TGA + their delta in $bn."""

    rrp_bn: float | None
    tga_bn: float | None
    proxy_bn: float | None
    """RRP + TGA in $bn at the most recent observation date for which
    BOTH series have a value. None if either side is missing."""

    proxy_bn_lag: float | None
    """Same proxy lookback_days earlier (or first available at/before)."""

    delta_bn: float | None
    """proxy_bn - proxy_bn_lag in $bn. Negative = liquidity drained."""

    note: str = ""


async def _latest_value_at_or_before(
    session: AsyncSession,
    *,
    series_id: str,
    cutoff_date,
) -> tuple[object | None, float | None]:
    """Most recent FredObservation row at or before `cutoff_date`.

    Returns `(observation_date, value)` or `(None, None)` if the
    series has no row in the lookback window.
    """
    stmt = (
        select(FredObservation.observation_date, FredObservation.value)
        .where(
            FredObservation.series_id == series_id,
            FredObservation.observation_date <= cutoff_date,
            FredObservation.value.is_not(None),
        )
        .order_by(desc(FredObservation.observation_date))
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        return None, None
    return row[0], float(row[1]) if row[1] is not None else None


async def assess_liquidity_proxy(
    session: AsyncSession,
    *,
    lookback_days: int = 5,
) -> LiquidityProxyReading:
    """Compute the RRP+TGA proxy and its `lookback_days` delta.

    Strategy : take the most recent date for which BOTH `RRPONTSYD`
    and `DTS_TGA_CLOSE` have a value, then look back exactly that
    many *calendar* days (FRED + DTS skip weekends, so the
    `at-or-before` query handles the slack).
    """
    today = datetime.now(UTC).date()

    rrp_t_date, rrp_bn = await _latest_value_at_or_before(
        session, series_id="RRPONTSYD", cutoff_date=today
    )
    tga_t_date, tga_mn = await _latest_value_at_or_before(
        session, series_id="DTS_TGA_CLOSE", cutoff_date=today
    )

    if rrp_bn is None or tga_mn is None or rrp_t_date is None or tga_t_date is None:
        # Cannot compute — log a clear note for observability.
        missing = []
        if rrp_bn is None:
            missing.append("RRPONTSYD")
        if tga_mn is None:
            missing.append("DTS_TGA_CLOSE")
        return LiquidityProxyReading(
            rrp_bn=rrp_bn,
            tga_bn=(tga_mn / 1000.0) if tga_mn is not None else None,
            proxy_bn=None,
            proxy_bn_lag=None,
            delta_bn=None,
            note=f"missing series: {', '.join(missing)}",
        )

    # Snap to the more recent of the two series-specific dates so we
    # don't pretend a stale TGA value is "today's" liquidity proxy.
    snap_date = min(rrp_t_date, tga_t_date)

    tga_bn = tga_mn / 1000.0
    proxy_t = round(rrp_bn + tga_bn, 2)

    cutoff_lag = snap_date - timedelta(days=lookback_days)
    rrp_lag_date, rrp_lag_bn = await _latest_value_at_or_before(
        session, series_id="RRPONTSYD", cutoff_date=cutoff_lag
    )
    tga_lag_date, tga_lag_mn = await _latest_value_at_or_before(
        session, series_id="DTS_TGA_CLOSE", cutoff_date=cutoff_lag
    )

    if rrp_lag_bn is None or tga_lag_mn is None:
        return LiquidityProxyReading(
            rrp_bn=rrp_bn,
            tga_bn=tga_bn,
            proxy_bn=proxy_t,
            proxy_bn_lag=None,
            delta_bn=None,
            note=f"insufficient history (need ≥ {lookback_days} d)",
        )

    proxy_lag = round(rrp_lag_bn + tga_lag_mn / 1000.0, 2)
    delta = round(proxy_t - proxy_lag, 2)
    return LiquidityProxyReading(
        rrp_bn=rrp_bn,
        tga_bn=tga_bn,
        proxy_bn=proxy_t,
        proxy_bn_lag=proxy_lag,
        delta_bn=delta,
        note=(
            f"RRP {rrp_bn:.0f}bn + TGA {tga_bn:.0f}bn = {proxy_t:.0f}bn "
            f"vs {proxy_lag:.0f}bn ({lookback_days}d ago) "
            f"→ Δ {delta:+.0f}bn"
        ),
    )
