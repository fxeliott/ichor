"""Data loaders for the backtest framework.

Two paths :

1. **`SyntheticDataGenerator`** — regime-switching geometric brownian
   motion with vol clustering. No network, no DB. Used for unit tests
   and "does the framework run end-to-end" smoke. Reproducible via seed.

2. **`load_market_data_from_db`** — pull persisted bars from the
   `market_data` Postgres hypertable (BLOC A). Async, requires an
   AsyncSession. Used for real backtests.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Sequence, Iterable, Any


@dataclass(frozen=True)
class Bar:
    """Daily OHLCV bar — duck-typed compatible with the API ORM model
    (we don't import the ORM here to keep this package DB-agnostic)."""

    bar_date: date
    asset: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


# ───────────────────────── synthetic ─────────────────────────


@dataclass
class SyntheticDataGenerator:
    """Regime-switching GBM with vol clustering.

    Produces realistic-ish daily bars : 3 hidden vol regimes, daily
    transition probabilities, log-normal returns within regime. No
    drift bias by default (zero EV) — we don't want backtests to look
    great by accident.
    """

    seed: int = 42
    drift_ann: float = 0.0
    vol_low_ann: float = 0.05
    vol_mid_ann: float = 0.12
    vol_high_ann: float = 0.30
    transition_prob: float = 0.02
    """Per-day probability of switching to a different regime."""

    def generate(
        self,
        asset: str,
        start: date,
        n_days: int,
        initial_price: float = 1.0,
    ) -> list[Bar]:
        rng = random.Random(self.seed + hash(asset) % 1000)
        regimes = [self.vol_low_ann, self.vol_mid_ann, self.vol_high_ann]
        regime_idx = 1  # start mid

        bars: list[Bar] = []
        price = initial_price
        cursor = start
        for _ in range(n_days):
            # Skip weekends (simple Mon-Fri filter)
            while cursor.weekday() >= 5:
                cursor = cursor + timedelta(days=1)

            # Regime transition
            if rng.random() < self.transition_prob:
                regime_idx = rng.choice([i for i in (0, 1, 2) if i != regime_idx])

            ann_vol = regimes[regime_idx]
            day_vol = ann_vol / math.sqrt(252)
            day_drift = self.drift_ann / 252
            ret = rng.gauss(day_drift, day_vol)
            new_close = price * math.exp(ret)

            # Intraday range proportional to vol
            half_range = abs(rng.gauss(0, day_vol)) * price
            open_p = price * math.exp(rng.gauss(0, day_vol / 4))
            high_p = max(open_p, new_close) + half_range
            low_p = min(open_p, new_close) - half_range
            # Pin to envelope (no constraint violation downstream)
            high_p = max(high_p, open_p, new_close)
            low_p = min(low_p, open_p, new_close)

            bars.append(
                Bar(
                    bar_date=cursor,
                    asset=asset,
                    open=open_p,
                    high=high_p,
                    low=low_p,
                    close=new_close,
                    volume=None,
                )
            )
            price = new_close
            cursor = cursor + timedelta(days=1)

        return bars


# ───────────────────────── DB loader ─────────────────────────


async def load_market_data_from_db(
    session: Any,  # AsyncSession (kept untyped to avoid hard dep here)
    asset: str,
    start: date,
    end: date,
    *,
    preferred_source: str | None = None,
) -> list[Bar]:
    """Pull bars from the `market_data` hypertable. Async.

    If `preferred_source` is given, only that source is returned. Otherwise,
    if multiple sources have the same (asset, bar_date), the most recently
    fetched wins.
    """
    # Lazy-import the ORM to keep this package optional-DB
    from sqlalchemy import select, desc

    from ichor_api.models import MarketDataBar  # type: ignore[import-not-found]

    stmt = (
        select(MarketDataBar)
        .where(
            MarketDataBar.asset == asset,
            MarketDataBar.bar_date >= start,
            MarketDataBar.bar_date <= end,
        )
        .order_by(MarketDataBar.bar_date, desc(MarketDataBar.fetched_at))
    )
    if preferred_source:
        stmt = stmt.where(MarketDataBar.source == preferred_source)

    rows = (await session.execute(stmt)).scalars().all()

    # Dedup per bar_date — pick first (most recently fetched) source
    seen: set[date] = set()
    out: list[Bar] = []
    for r in rows:
        if r.bar_date in seen:
            continue
        seen.add(r.bar_date)
        out.append(
            Bar(
                bar_date=r.bar_date,
                asset=r.asset,
                open=float(r.open),
                high=float(r.high),
                low=float(r.low),
                close=float(r.close),
                volume=float(r.volume) if r.volume is not None else None,
            )
        )
    out.sort(key=lambda b: b.bar_date)
    return out


def bars_as_close_series(bars: Sequence[Bar]) -> list[tuple[date, float]]:
    """Convenience: extract a (date, close) timeseries from bars."""
    return [(b.bar_date, b.close) for b in bars]
