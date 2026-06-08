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
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import MarketDataBar, PolygonIntradayBar


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
    volume_is_reported: bool = True
    """Whether the venue reported real volume over the window. Polygon FX
    aggregates (C:EURUSD/C:GBPUSD) carry no consolidated volume → this is
    False, and the volume-derived metrics above are N/A by data property,
    NOT a gap. Defaults True so legacy constructors keep their behaviour
    (no spurious disclaimer); ``assess_microstructure`` sets the real value."""


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


def _volume_is_reported(bars: list[IntradayBar]) -> bool:
    """True iff the venue reported any real volume over the window.

    Polygon FX aggregates (C:EURUSD/C:GBPUSD) return bars with volume == 0
    while still carrying OHLC — so ``sum(volume) == 0`` with ``n_bars > 0``
    means "volume not reported", distinct from "market closed" (n_bars == 0).
    """
    return any(b.volume > 0 for b in bars)


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
        volume_is_reported=_volume_is_reported(bars),
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
    ]
    if not r.volume_is_reported:
        # Polygon FX aggregates carry OHLC but no consolidated volume → the
        # volume-derived metrics below read n/a as a DATA PROPERTY, not a gap.
        # Make this explicit so the brain doesn't treat it as a broken pipeline
        # (S04 « sans zone d'ombre » — no silent n/a). Index assets (SPY/I:NDX)
        # carry real share volume and never hit this branch.
        lines.append(
            "- ⚠ Volume not reported by source (Polygon FX aggregates carry no "
            "consolidated volume) — volume-derived metrics (Amihud / Kyle / VWAP "
            "/ POC / value-area) are N/A by data property, NOT a gap; realized "
            "vol below is volume-free and remains valid."
        )
    lines += [
        f"- Amihud illiquidity      = {illiq_str}",
        f"- Kyle's lambda           = {f(r.kyles_lambda, '{:.3e}')}  (price impact per signed unit)",
        f"- Realized vol annualized = {f(r.realized_vol_pct, '{:.2f}%')}",
        f"- VWAP                    = {f(r.vwap)}",
        f"- POC (price of control)  = {f(r.poc)}",
        f"- Value area low / high   = {f(r.value_area_low)} / {f(r.value_area_high)}",
    ]
    sources = [f"polygon_intraday:{r.asset}@last{r.window_minutes}min"]
    return "\n".join(lines), sources


# ════════════════════ Relative-volume / participation layer ════════════════
#
# S04 TIER-2 depth (« chaque dimension poussée au maximum, sans zone d'ombre ») :
# the microstructure block above uses volume only as a WEIGHT (Amihud / Kyle /
# VWAP / value-area). It never answers the first question a desk asks of volume —
# « is today's participation light, normal, or a spike vs its own history ? »
#
# This layer adds exactly that : relative volume (RVOL = current daily volume /
# trailing average), a volume z-score, and a non-directional participation bucket.
# It runs on DAILY ``market_data`` bars (deep history) rather than the shallow
# intraday table, and only for assets that carry real consolidated volume —
# empirically SPY (SPX500), I:NDX daily (NAS100) and GC=F gold futures (XAU) via
# yfinance. FX pairs carry zero venue volume → honest N/A by data property (the
# caller decides), never a silent gap. Direction is NOT inferred (a spike can be
# up or down) — this is participation / conviction CONTEXT for the brain,
# descriptive and ADR-017-safe by construction.

_RVOL_AVG_WINDOW = 20
"""Trailing trading-day window for the RVOL ratio baseline (classic 20-day RVOL)."""
_VOLUME_ZSCORE_WINDOW = 60
"""Trailing window for the volume z-score."""
_MIN_RVOL_HISTORY = 10
"""Below this many baseline observations the RVOL ratio is not credible → None."""
_MIN_VOLUME_ZSCORE_HISTORY = 60
"""z-score floor — mirrors ``dollar_smile_check._MIN_ZSCORE_HISTORY`` (credible sample)."""


@dataclass(frozen=True)
class RelativeVolumeReading:
    """Relative-volume / participation read for one asset over its daily history."""

    asset: str
    volume_available: bool
    """False = the venue reports no consolidated volume (FX) → every metric below
    is None and the bucket is an honest N/A, NOT a gap."""
    latest_date: date | None
    current_volume: float | None
    avg_volume: float | None
    """Trailing ``_RVOL_AVG_WINDOW``-day mean volume, excluding the current bar."""
    rvol_ratio: float | None
    """current_volume / avg_volume — > 1 = above-average participation."""
    volume_zscore: float | None
    """(current - mean) / std over ``_VOLUME_ZSCORE_WINDOW``; None until credible."""
    n_history: int
    bucket: str


def _volume_zscore(history: list[float], current: float) -> float | None:
    """z-score with min-history + zero-std defenses (mirror of dollar_smile_check)."""
    n = len(history)
    if n < _MIN_VOLUME_ZSCORE_HISTORY:
        return None
    mean = sum(history) / n
    var = sum((v - mean) ** 2 for v in history) / n
    std = math.sqrt(var)
    if std == 0:
        return None
    return (current - mean) / std


def _volume_bucket(rvol_ratio: float | None, zscore: float | None) -> str:
    """Non-directional participation label from the RVOL ratio + z-score.

    Descriptive only (ADR-017) : magnitude of participation, never a direction.
    """
    if rvol_ratio is None:
        return "insufficient-history"
    if rvol_ratio >= 2.0 or (zscore is not None and zscore >= 2.0):
        return "volume spike"
    if rvol_ratio >= 1.25:
        return "elevated participation"
    if rvol_ratio >= 0.8:
        return "average participation"
    if rvol_ratio >= 0.5:
        return "below-average participation"
    return "very light participation"


def classify_relative_volume(
    daily_volumes: list[float],
    *,
    asset: str,
    latest_date: date | None,
    volume_available: bool = True,
) -> RelativeVolumeReading:
    """Pure RVOL + volume z-score + participation bucket.

    ``daily_volumes`` is the ascending series of positive daily volumes, last
    element = the current (most recent) bar. Pure-stdlib, no I/O ; degenerate
    inputs return ``None`` metrics with an honest bucket, never raise.
    """
    if not volume_available:
        return RelativeVolumeReading(
            asset=asset,
            volume_available=False,
            latest_date=latest_date,
            current_volume=None,
            avg_volume=None,
            rvol_ratio=None,
            volume_zscore=None,
            n_history=0,
            bucket="n/a — no venue volume",
        )
    if not daily_volumes:
        return RelativeVolumeReading(
            asset=asset,
            volume_available=True,
            latest_date=latest_date,
            current_volume=None,
            avg_volume=None,
            rvol_ratio=None,
            volume_zscore=None,
            n_history=0,
            bucket="absent",
        )
    current = daily_volumes[-1]
    history = daily_volumes[:-1]
    n_history = len(history)

    avg_window = history[-_RVOL_AVG_WINDOW:]
    avg_volume = sum(avg_window) / len(avg_window) if len(avg_window) >= _MIN_RVOL_HISTORY else None
    rvol_ratio = (current / avg_volume) if (avg_volume and avg_volume > 0) else None

    z_window = history[-_VOLUME_ZSCORE_WINDOW:]
    volume_zscore = _volume_zscore(z_window, current)

    return RelativeVolumeReading(
        asset=asset,
        volume_available=True,
        latest_date=latest_date,
        current_volume=current,
        avg_volume=avg_volume,
        rvol_ratio=rvol_ratio,
        volume_zscore=volume_zscore,
        n_history=n_history,
        bucket=_volume_bucket(rvol_ratio, volume_zscore),
    )


async def assess_relative_volume(
    session: AsyncSession,
    asset: str,
    *,
    lookback_days: int = 400,
) -> RelativeVolumeReading:
    """Pull daily volume from ``market_data`` and compute the relative-volume read.

    Dedups ``(asset, bar_date)`` across sources by keeping the largest positive
    volume, and drops days with no/zero volume (non-trading days or volume-less
    sources). ``lookback_days`` ~400 covers ``_VOLUME_ZSCORE_WINDOW`` with margin.
    Intended for volume-bearing assets only — the FX honest-N/A path is the
    caller's zero-DB ``volume_available=False`` branch.
    """
    cutoff = (datetime.now(UTC) - timedelta(days=lookback_days)).date()
    rows = list(
        (
            await session.execute(
                select(MarketDataBar.bar_date, MarketDataBar.volume)
                .where(
                    MarketDataBar.asset == asset,
                    MarketDataBar.bar_date >= cutoff,
                )
                .order_by(MarketDataBar.bar_date.asc())
            )
        ).all()
    )
    by_date: dict[date, float] = {}
    for bar_date, vol in rows:
        if vol is None or vol <= 0:
            continue
        v = float(vol)
        prev = by_date.get(bar_date)
        if prev is None or v > prev:
            by_date[bar_date] = v
    if not by_date:
        return classify_relative_volume([], asset=asset, latest_date=None, volume_available=True)
    ordered = sorted(by_date)
    volumes = [by_date[d] for d in ordered]
    return classify_relative_volume(
        volumes, asset=asset, latest_date=ordered[-1], volume_available=True
    )


def render_relative_volume_block(r: RelativeVolumeReading) -> tuple[str, list[str]]:
    """Markdown block + sources for data_pool.py (descriptive, ADR-017-safe)."""
    title = f"## Relative volume / participation ({r.asset})"
    if not r.volume_available:
        md = (
            f"{title}\n"
            f"- Relative daily volume N/A — {r.asset} carries no consolidated venue "
            "volume (FX). Participation is read via the microstructure block's "
            "order-flow proxies (Amihud / Kyle / signed-volume) instead — N/A here "
            "by data property, NOT a gap."
        )
        return md, []
    if r.current_volume is None or r.latest_date is None:
        md = (
            f"{title}\n- ⚠ market_data:{r.asset}:volume ABSENT : no positive daily volume persisted"
        )
        return md, []
    src = [f"market_data:{r.asset}:volume@{r.latest_date.isoformat()}"]
    if r.rvol_ratio is None or r.avg_volume is None:
        md = (
            f"{title}\n"
            f"- volume {r.current_volume:,.0f} on {r.latest_date} — insufficient history "
            f"(n={r.n_history}, need ≥{_MIN_RVOL_HISTORY}) to compute relative volume; warming up."
        )
        return md, src
    z_str = f"{r.volume_zscore:+.1f}" if r.volume_zscore is not None else "n/a"
    md = (
        f"{title}\n"
        f"- Latest daily bar {r.latest_date}: volume {r.current_volume:,.0f} vs "
        f"{_RVOL_AVG_WINDOW}-day avg {r.avg_volume:,.0f} → RVOL {r.rvol_ratio:.2f}× (z {z_str})\n"
        f"- Participation: {r.bucket}\n"
        "- Note: compares the latest daily bar; an in-progress session day reads partial volume."
    )
    return md, src
