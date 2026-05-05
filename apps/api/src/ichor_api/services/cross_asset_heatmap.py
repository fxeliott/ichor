"""Cross-asset heatmap — 4 rows × 4 cells of live market state.

Powers `/macro-pulse` page heatmap section. Reads FRED + market_data
hypertables and computes:
  - Risk-on row: SPX, NAS100, EUR/USD, AUD/USD (1d % change)
  - Defensive row: VIX, USD/JPY, XAU, DXY
  - Rates row: US10Y, US2Y, 10Y-2Y spread, TIPS 10Y (yield levels in %)
  - Credit row: HY OAS, IG OAS, EM OAS, MOVE (bps / index level)

Bias direction per cell maps to the indicator's "risk-on" interpretation
(e.g. SPX up = bull, VIX up = bear, US2Y rising = bear for credit).
Empty cells (no recent observation) report `value=None, bias='neutral'`.

Performance : ALL FRED series + ALL market_data assets are pulled in
exactly TWO batched IN-queries (one per table), then aggregated in
Python. This replaces the original 20-query sequential implementation
and is 5-10× faster (single round-trip per table vs. one per series).
SQLAlchemy AsyncSession concurrency limits don't apply here since
queries are still serialized within the session.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import FredObservation, MarketDataBar

Bias = Literal["bull", "bear", "neutral"]
Unit = Literal["%", "bps", "pts", "level"]


@dataclass(frozen=True)
class HeatmapCell:
    sym: str
    value: float | None
    """Numeric value : 1d-pct-change for FX/equities, yield-pct for rates,
    spread-bps for credit."""
    bias: Bias
    unit: Unit


@dataclass(frozen=True)
class HeatmapRow:
    row: str
    cells: list[HeatmapCell]


@dataclass(frozen=True)
class CrossAssetHeatmap:
    generated_at: datetime
    rows: list[HeatmapRow]
    sources: list[str]


# Sign of "risk-on bias" per series : +1 = up = bullish for risk, -1 = up
# = bearish for risk. Used to convert a delta sign into a bull/bear cell.
_RISK_SIGN: dict[str, int] = {
    "SPX": +1,
    "NAS100": +1,
    "EUR_USD": +1,
    "AUD_USD": +1,
    "VIX": -1,
    "USD_JPY": +1,  # carry favourable when up in low-vol regime
    "XAU_USD": -1,  # gold up = haven flow = risk-off
    "DXY": -1,  # USD up = risk-off
}


# Series fetched in one batched query each call.
_FRED_SERIES = (
    "VIXCLS",  # VIX level
    "DTWEXBGS",  # Broad dollar (DXY proxy)
    "DGS10",  # US 10Y yield
    "DGS2",  # US 2Y yield
    "DFII10",  # TIPS 10Y real yield
    "BAMLH0A0HYM2",  # HY OAS (pct → ×100 = bps)
    "BAMLC0A0CM",  # IG OAS
    "BAMLEMCBPIOAS",  # EM OAS
    "MOVE",  # MOVE index level
)

_MARKET_ASSETS = (
    "SPX",
    "NAS100",
    "EUR_USD",
    "AUD_USD",
    "USD_JPY",
    "XAU_USD",
)


def _bias_from_signed_value(asset: str, value: float | None) -> Bias:
    if value is None:
        return "neutral"
    sign = _RISK_SIGN.get(asset, +1)
    if abs(value) < 0.05:
        return "neutral"
    return "bull" if value * sign > 0 else "bear"


def _unique_sources(items: Iterable[str]) -> list[str]:
    seen: dict[str, None] = {}
    for it in items:
        if it not in seen:
            seen[it] = None
    return list(seen)


# ─────────────────────── batched fetchers ───────────────────────


async def _fetch_fred_latest_two(
    session: AsyncSession, *, series_ids: tuple[str, ...], lookback_days: int = 14
) -> dict[str, list[float]]:
    """One query → for each requested series, return up to 2 most-recent
    values (latest + previous trading day). Used downstream for both
    `latest level` and `pct change vs 1d ago`.

    Implementation : pull all rows in the last `lookback_days` for the
    series set, sort desc by observation_date in Python, take 2 per series.
    """
    cutoff = datetime.now(UTC).date() - timedelta(days=lookback_days)
    rows = (
        await session.execute(
            select(
                FredObservation.series_id,
                FredObservation.observation_date,
                FredObservation.value,
            )
            .where(
                FredObservation.series_id.in_(series_ids),
                FredObservation.value.is_not(None),
                FredObservation.observation_date >= cutoff,
            )
            .order_by(
                FredObservation.series_id,
                FredObservation.observation_date.desc(),
            )
        )
    ).all()
    by_series: dict[str, list[float]] = defaultdict(list)
    for sid, _date, value in rows:
        if len(by_series[sid]) >= 2:
            continue  # already have latest + 1d-ago
        by_series[sid].append(float(value))
    return dict(by_series)


async def _fetch_market_latest_two(
    session: AsyncSession,
    *,
    assets: tuple[str, ...],
    lookback_days: int = 7,
) -> dict[str, list[float]]:
    """One query → for each requested asset, return up to 2 most-recent
    closes (today + yesterday) so we can compute 1d pct change.
    """
    cutoff = datetime.now(UTC).date() - timedelta(days=lookback_days)
    rows = (
        await session.execute(
            select(
                MarketDataBar.asset,
                MarketDataBar.bar_date,
                MarketDataBar.close,
            )
            .where(
                MarketDataBar.asset.in_(assets),
                MarketDataBar.close.is_not(None),
                MarketDataBar.bar_date >= cutoff,
            )
            .order_by(
                MarketDataBar.asset,
                MarketDataBar.bar_date.desc(),
            )
        )
    ).all()
    by_asset: dict[str, list[float]] = defaultdict(list)
    for asset, _date, close in rows:
        if len(by_asset[asset]) >= 2:
            continue
        by_asset[asset].append(float(close))
    return dict(by_asset)


def _pct_change(values: list[float] | None) -> float | None:
    """[latest, prev] → (latest - prev) / prev * 100."""
    if not values or len(values) < 2 or values[1] == 0:
        return None
    return (values[0] - values[1]) / values[1] * 100.0


def _level(values: list[float] | None) -> float | None:
    """[latest, ...] → latest."""
    if not values:
        return None
    return values[0]


# ─────────────────────── orchestrator ───────────────────────


async def assess_cross_asset_heatmap(session: AsyncSession) -> CrossAssetHeatmap:
    fred = await _fetch_fred_latest_two(session, series_ids=_FRED_SERIES)
    market = await _fetch_market_latest_two(session, assets=_MARKET_ASSETS)
    sources: list[str] = []

    # ── Row 1: Risk-on (1d pct changes from market_data EOD bars) ──────
    risk_on_cells: list[HeatmapCell] = []
    for sym, asset in (
        ("SPX", "SPX"),
        ("NAS100", "NAS100"),
        ("EUR/USD", "EUR_USD"),
        ("AUD/USD", "AUD_USD"),
    ):
        v = _pct_change(market.get(asset))
        risk_on_cells.append(
            HeatmapCell(sym=sym, value=v, bias=_bias_from_signed_value(asset, v), unit="%")
        )
        if v is not None:
            sources.append(f"market_data:{asset}")

    # ── Row 2: Defensive ──────────────────────────────────────────────
    vix_pct = _pct_change(fred.get("VIXCLS"))
    if fred.get("VIXCLS"):
        sources.append("FRED:VIXCLS")
    usd_jpy_pct = _pct_change(market.get("USD_JPY"))
    if usd_jpy_pct is not None:
        sources.append("market_data:USD_JPY")
    xau_pct = _pct_change(market.get("XAU_USD"))
    if xau_pct is not None:
        sources.append("market_data:XAU_USD")
    dxy_pct = _pct_change(fred.get("DTWEXBGS"))
    if fred.get("DTWEXBGS"):
        sources.append("FRED:DTWEXBGS")

    defensive_cells = [
        HeatmapCell(
            sym="VIX",
            value=vix_pct,
            bias=_bias_from_signed_value("VIX", vix_pct),
            unit="%",
        ),
        HeatmapCell(
            sym="USD/JPY",
            value=usd_jpy_pct,
            bias=_bias_from_signed_value("USD_JPY", usd_jpy_pct),
            unit="%",
        ),
        HeatmapCell(
            sym="XAU",
            value=xau_pct,
            bias=_bias_from_signed_value("XAU_USD", xau_pct),
            unit="%",
        ),
        HeatmapCell(
            sym="DXY",
            value=dxy_pct,
            bias=_bias_from_signed_value("DXY", dxy_pct),
            unit="%",
        ),
    ]

    # ── Row 3: Rates (yield levels — bias = "bear for risk" if rising). ─
    us10y = _level(fred.get("DGS10"))
    us2y = _level(fred.get("DGS2"))
    spread_2s10s = round((us10y - us2y), 2) if us10y is not None and us2y is not None else None
    tips10y = _level(fred.get("DFII10"))
    rates_cells = [
        HeatmapCell(
            sym="US10Y",
            value=us10y,
            bias=("neutral" if us10y is None else "bear" if us10y > 4.0 else "bull"),
            unit="%",
        ),
        HeatmapCell(
            sym="US2Y",
            value=us2y,
            bias=("neutral" if us2y is None else "bear" if us2y > 4.0 else "bull"),
            unit="%",
        ),
        HeatmapCell(
            sym="10Y-2Y",
            value=spread_2s10s,
            bias=("neutral" if spread_2s10s is None else "bear" if spread_2s10s < 0 else "bull"),
            unit="%",
        ),
        HeatmapCell(
            sym="TIPS 10Y",
            value=tips10y,
            bias=("neutral" if tips10y is None else "bear" if tips10y > 1.5 else "bull"),
            unit="%",
        ),
    ]
    for sid, val in (("DGS10", us10y), ("DGS2", us2y), ("DFII10", tips10y)):
        if val is not None:
            sources.append(f"FRED:{sid}")

    # ── Row 4: Credit (spreads in bps). FRED stores OAS as percentage. ──
    hy = _level(fred.get("BAMLH0A0HYM2"))
    ig = _level(fred.get("BAMLC0A0CM"))
    em = _level(fred.get("BAMLEMCBPIOAS"))
    move = _level(fred.get("MOVE"))
    hy_bps = hy * 100.0 if hy is not None else None
    ig_bps = ig * 100.0 if ig is not None else None
    em_bps = em * 100.0 if em is not None else None
    credit_cells = [
        HeatmapCell(
            sym="HY OAS",
            value=hy_bps,
            bias=("neutral" if hy_bps is None else "bull" if hy_bps < 400 else "bear"),
            unit="bps",
        ),
        HeatmapCell(
            sym="IG OAS",
            value=ig_bps,
            bias=("neutral" if ig_bps is None else "bull" if ig_bps < 130 else "bear"),
            unit="bps",
        ),
        HeatmapCell(
            sym="EM OAS",
            value=em_bps,
            bias=("neutral" if em_bps is None else "bull" if em_bps < 350 else "bear"),
            unit="bps",
        ),
        HeatmapCell(
            sym="MOVE",
            value=move,
            bias=("neutral" if move is None else "bull" if move < 100 else "bear"),
            unit="level",
        ),
    ]
    for sid, val in (
        ("BAMLH0A0HYM2", hy),
        ("BAMLC0A0CM", ig),
        ("BAMLEMCBPIOAS", em),
        ("MOVE", move),
    ):
        if val is not None:
            sources.append(f"FRED:{sid}")

    return CrossAssetHeatmap(
        generated_at=datetime.now(UTC),
        rows=[
            HeatmapRow(row="Risk-on", cells=risk_on_cells),
            HeatmapRow(row="Defensive", cells=defensive_cells),
            HeatmapRow(row="Rates", cells=rates_cells),
            HeatmapRow(row="Credit", cells=credit_cells),
        ],
        sources=_unique_sources(sources),
    )
