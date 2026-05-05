"""Order-flow microstructure metrics on top of polygon_intraday bars.

Pure-stdlib functions (math + statistics) — no pandas, no numpy.
The intraday bar layer is already 1-min OHLCV from Polygon Massive
($49/mo Currencies plan), so we have everything we need without
extra subscriptions.

Metrics shipped V1 :
  - Amihud illiquidity ratio (Amihud 2002) :
        ILLIQ = mean( |return_t| / (volume_t * price_t) )
    high values = thin market, scarce liquidity. The reciprocal is
    sometimes called "market depth".

  - Kyle's lambda (Kyle 1985) — simplified OLS slope :
        lambda = cov(price_change, signed_volume) / var(signed_volume)
    measures price impact per unit signed volume. Sign of volume is
    Lee-Ready-style : up-tick → +volume, down-tick → -volume.

  - Realized volatility (close-to-close, annualized for the window) :
        RV = sqrt( sum(log_returns^2) ) * sqrt( bars_per_year / n_bars )

  - VWAP-like Volume Profile : POC (price of max volume), VAH/VAL
    (value-area high/low at 70% volume coverage)

VISION_2026 delta A — order-flow microstructure stack.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import PolygonIntradayBar


@dataclass(frozen=True)
class IntradayBar:
    """Lightweight bar for math — copy of the relevant ORM fields."""

    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class MicrostructureReading:
    """All microstructure metrics for one asset over one time window."""

    asset: str
    n_bars: int
    window_minutes: int
    amihud_illiquidity: float | None
    """Higher = more illiquid. Multiplied by 1e6 in the rendered text
    so the unit-less ratio is human-readable."""
    kyles_lambda: float | None
    """Price impact per unit signed volume. Higher = market more sensitive
    to flow."""
    realized_vol_pct: float | None
    """Annualized realized vol (%) over the window. Diagnostic only."""
    vwap: float | None
    poc: float | None
    """Price of Control = price level with the highest volume in the window."""
    value_area_low: float | None
    value_area_high: float | None
    """70%-volume value area boundaries (POC ± until 70% volume captured)."""


def _signed_volume(bars: list[IntradayBar]) -> list[float]:
    """Lee-Ready-style sign : current close vs previous close.

    Up-tick → +volume, down-tick → -volume, no-change → +volume
    (no zero-tick rule because we don't have the trade-by-trade tape).
    """
    out: list[float] = []
    prev_close = bars[0].close if bars else 0.0
    for b in bars:
        if b.close > prev_close:
            out.append(b.volume)
        elif b.close < prev_close:
            out.append(-b.volume)
        else:
            out.append(b.volume)  # treat no-change as +1 by convention
        prev_close = b.close
    return out


def amihud(bars: list[IntradayBar]) -> float | None:
    """Amihud (2002) illiquidity ratio averaged over the window."""
    vals = []
    prev = bars[0].close if bars else 0.0
    for b in bars[1:]:
        if prev <= 0 or b.volume <= 0:
            prev = b.close
            continue
        ret = (b.close - prev) / prev
        denom = b.volume * b.close
        if denom > 0:
            vals.append(abs(ret) / denom)
        prev = b.close
    if not vals:
        return None
    return sum(vals) / len(vals)


def kyles_lambda(bars: list[IntradayBar]) -> float | None:
    """OLS slope of price_change ~ signed_volume."""
    if len(bars) < 5:
        return None
    sv = _signed_volume(bars)
    pc: list[float] = []
    prev = bars[0].close
    for b in bars[1:]:
        pc.append(b.close - prev)
        prev = b.close
    sv = sv[1:]  # align to price changes (drop first)
    if len(sv) != len(pc) or not pc:
        return None
    mean_sv = sum(sv) / len(sv)
    mean_pc = sum(pc) / len(pc)
    num = sum((sv[i] - mean_sv) * (pc[i] - mean_pc) for i in range(len(sv)))
    den = sum((sv[i] - mean_sv) ** 2 for i in range(len(sv)))
    if den <= 0:
        return None
    return num / den


def realized_vol_pct(bars: list[IntradayBar], bars_per_year: int = 525_600) -> float | None:
    """Annualized RV from log returns. Default bars_per_year = 1-min × 365.25 × 24 × 60."""
    if len(bars) < 2:
        return None
    rets: list[float] = []
    prev = bars[0].close
    for b in bars[1:]:
        if prev <= 0 or b.close <= 0:
            prev = b.close
            continue
        rets.append(math.log(b.close / prev))
        prev = b.close
    if not rets:
        return None
    sum_sq = sum(r * r for r in rets)
    return math.sqrt(sum_sq) * math.sqrt(bars_per_year / max(1, len(rets))) * 100.0


def vwap(bars: list[IntradayBar]) -> float | None:
    num = 0.0
    den = 0.0
    for b in bars:
        if b.volume <= 0:
            continue
        typical = (b.high + b.low + b.close) / 3.0
        num += typical * b.volume
        den += b.volume
    if den <= 0:
        return None
    return num / den


def value_area(
    bars: list[IntradayBar], coverage: float = 0.70, n_buckets: int = 30
) -> tuple[float | None, float | None, float | None]:
    """Volume profile : POC + value-area-low + value-area-high.

    Buckets typical-price across n_buckets bins, finds the bin with the
    highest summed volume (POC), then expands symmetrically until
    `coverage` of total volume is captured.
    """
    if not bars:
        return None, None, None
    typical = [(b.high + b.low + b.close) / 3.0 for b in bars]
    vols = [b.volume for b in bars]
    if sum(vols) <= 0:
        return None, None, None

    lo = min(typical)
    hi = max(typical)
    if hi <= lo:
        return typical[0], typical[0], typical[0]
    bucket_w = (hi - lo) / n_buckets
    bucket_vol = [0.0] * n_buckets
    bucket_mid = [lo + bucket_w * (i + 0.5) for i in range(n_buckets)]
    for tp, v in zip(typical, vols, strict=False):
        idx = min(n_buckets - 1, max(0, int((tp - lo) / bucket_w)))
        bucket_vol[idx] += v

    total_vol = sum(bucket_vol)
    if total_vol <= 0:
        return None, None, None

    # POC = bin with the most volume
    poc_idx = max(range(n_buckets), key=lambda i: bucket_vol[i])
    poc = bucket_mid[poc_idx]

    # Expand symmetrically from POC until coverage reached
    captured = bucket_vol[poc_idx]
    target = total_vol * coverage
    lo_idx = poc_idx
    hi_idx = poc_idx
    while captured < target and (lo_idx > 0 or hi_idx < n_buckets - 1):
        next_lo = bucket_vol[lo_idx - 1] if lo_idx > 0 else -1.0
        next_hi = bucket_vol[hi_idx + 1] if hi_idx < n_buckets - 1 else -1.0
        if next_lo >= next_hi and next_lo >= 0:
            lo_idx -= 1
            captured += next_lo
        elif next_hi >= 0:
            hi_idx += 1
            captured += next_hi
        else:
            break
    return poc, bucket_mid[lo_idx], bucket_mid[hi_idx]


async def assess_microstructure(
    session: AsyncSession,
    asset: str,
    *,
    window_minutes: int = 240,
) -> MicrostructureReading:
    """Pull recent bars and assemble all metrics in one shot."""
    cutoff = datetime.now(UTC) - timedelta(minutes=window_minutes)
    rows = list(
        (
            await session.execute(
                select(PolygonIntradayBar)
                .where(
                    PolygonIntradayBar.asset == asset,
                    PolygonIntradayBar.bar_ts >= cutoff,
                )
                .order_by(PolygonIntradayBar.bar_ts.asc())
            )
        )
        .scalars()
        .all()
    )
    bars = [
        IntradayBar(
            ts=r.bar_ts,
            open=float(r.open),
            high=float(r.high),
            low=float(r.low),
            close=float(r.close),
            volume=float(r.volume or 0),
        )
        for r in rows
    ]

    illiq = amihud(bars)
    kl = kyles_lambda(bars)
    rv = realized_vol_pct(bars)
    vw = vwap(bars)
    poc, val, vah = value_area(bars)

    return MicrostructureReading(
        asset=asset,
        n_bars=len(bars),
        window_minutes=window_minutes,
        amihud_illiquidity=illiq,
        kyles_lambda=kl,
        realized_vol_pct=rv,
        vwap=vw,
        poc=poc,
        value_area_low=val,
        value_area_high=vah,
    )


def render_microstructure_block(r: MicrostructureReading) -> tuple[str, list[str]]:
    """Markdown block + sources for data_pool.py."""
    if r.n_bars == 0:
        md = f"## Microstructure ({r.asset}, last {r.window_minutes}min)\n- (no bars in window — market closed)"
        return md, []

    def f(v: float | None, fmt: str = "{:.5f}") -> str:
        return "n/a" if v is None else fmt.format(v)

    illiq_str = (
        f"{r.amihud_illiquidity * 1e6:.4f} (×1e6)" if r.amihud_illiquidity is not None else "n/a"
    )
    lines = [
        f"## Microstructure ({r.asset}, last {r.window_minutes}min, {r.n_bars} bars)",
        f"- Amihud illiquidity      = {illiq_str}",
        f"- Kyle's lambda           = {f(r.kyles_lambda, '{:.3e}')}  (price impact per signed unit)",
        f"- Realized vol annualized = {f(r.realized_vol_pct, '{:.2f}%')}",
        f"- VWAP                    = {f(r.vwap)}",
        f"- POC (price of control)  = {f(r.poc)}",
        f"- Value area low / high   = {f(r.value_area_low)} / {f(r.value_area_high)}",
    ]
    sources = [f"polygon_intraday:{r.asset}@last{r.window_minutes}min"]
    return "\n".join(lines), sources
