"""Polygon.io Starter — 1-min OHLCV collector.

Polygon Starter ($29/mo) covers all 8 Phase-1 assets at 1-minute
granularity with end-of-day delay (no realtime feed). Endpoint :

    GET /v2/aggs/ticker/{ticker}/range/1/minute/{from}/{to}
        ?adjusted=true&sort=asc&limit=50000

Ticker conventions in Polygon's (Massive 2026) namespace :
  C:EURUSD          forex pairs
  C:XAUUSD          spot metals (gold, silver — Currencies namespace, NOT crypto)
  X:BTCUSD          crypto pairs (X: prefix, distinct from forex)
  I:NDX / I:SPX     indices
  AAPL / SPY        equities (not used here)

Source: massive.com/blog/real-time-forex-data-plans (Currencies plan covers
forex pairs + XAU/XAG via the C: prefix). The X: prefix is reserved for
cryptocurrencies. Earlier versions of this collector mistakenly mapped
XAU_USD to "X:XAUUSD" — fixed 2026-05-03.

The collector is pure-Python (httpx). The persistence layer lives in
`collectors/persistence.py` (added separately).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import httpx

POLYGON_BASE_URL = "https://api.polygon.io"


# Polygon ticker code per Phase-1 asset. Mapping is explicit because
# the namespace prefix (C: / X: / I:) drives endpoint selection on
# Polygon's side.
ASSET_TO_TICKER: dict[str, str] = {
    "EUR_USD": "C:EURUSD",
    "GBP_USD": "C:GBPUSD",
    "USD_JPY": "C:USDJPY",
    "AUD_USD": "C:AUDUSD",
    "USD_CAD": "C:USDCAD",
    "XAU_USD": "C:XAUUSD",
    "NAS100_USD": "I:NDX",
    # SPX500_USD : aliased to SPY (NYSE Arca ETF) until Polygon Indices
    # Starter plan ($49/mo, 2026-05 pricing) is budgeted. SPY tracks
    # cash I:SPX with <0.1% MTD tracking error (NAV spread tight,
    # 0.0945% annual expense ratio) — imperceptible for Pass-2's
    # qualitative macro framework (ISM/NFP/CPI/GEX/HY OAS drivers, not
    # absolute close levels — cf packages/ichor_brain/passes/asset.py:
    # 143-154). Polygon Stocks Starter ($29/mo, already paid) covers
    # SPY. ADR-089 (PROPOSED). To revert when Indices plan budgeted :
    # change "SPY" back to "I:SPX" — single-line revert.
    "SPX500_USD": "SPY",
    # ── Cross-asset risk-on/off proxy (not a Phase-1 trading asset) ──
    "BTC_USD": "X:BTCUSD",
    # ── DXY (US Dollar Index, ICE) — aliased to UUP (NYSE Arca ETF :
    # Invesco DB US Dollar Index Bullish Fund, CUSIP 46141D203, inception
    # 2007-02-20, expense ratio 0.79% per FY2025 SEC Form 424B3) until
    # Polygon Indices Starter plan ($49/mo Starter 15-min delayed, $99/mo
    # Advanced real-time) is budgeted. UUP tracks the Deutsche Bank Long
    # USD Currency Portfolio Index — Excess Return TM, replicated via
    # long DX futures contracts on ICE Futures US (the actual DXY USDX®
    # futures contract), which itself tracks the DXY ICE basket (EUR
    # 57.6% / JPY 13.6% / GBP 11.9% / CAD 9.1% / SEK 4.2% / CHF 3.6%
    # per Federal Reserve H.10 / FactSet methodology, Fed-Reserve-Bank
    # of New York / ICE Data Indices).
    #
    # TRACKING-ERROR HONESTY STAMP (Pattern #15 R59 r172 self-catch on
    # over-claimed correlation magnitude) : UUP↔DXY log-returns
    # correlation ~0.94 (practitioner-grade, NOT peer-reviewed
    # academic study found this session). Material tracking drift
    # from (a) futures-roll cost, (b) 0.79% ER, (c) Treasury income
    # offset, (d) NAV-vs-NAV intraday spread. Direction sign IS
    # invariant : UUP rises when USD rises = same direction as DXY
    # (prospectus verbatim « long positions in DX Contracts with a
    # view to tracking changes, whether positive or negative »). So
    # the existing _REFERENCE_CORR priors at correlations.py:102-109
    # (DXY-EUR_USD -0.95, DXY-USD_JPY +0.55, etc.) remain
    # DIRECTIONALLY valid with UUP-as-proxy ; the MAGNITUDE of
    # realized ρ will be diluted by ~6% (1-0.94) vs hypothetical
    # I:DXY ground-truth. Pattern #15 honesty surface : NOT a
    # peer-reviewed magnitude — see `_REFERENCE_CORR:91-95` stamp
    # convention for similar honest annotation.
    #
    # Pre-r172 the mapping was "I:DXY" → HTTP 403 on Stocks Starter
    # plan ($29/mo, already paid) → DXY row in polygon_intraday was
    # permanently empty → `correlations.py:198` `len(common) < 30`
    # skip kept DXY-row matrix cells at None (cold-start by
    # construction). Mirrors ADR-089 r27 SPY proxy precedent for
    # SPX500_USD : reversible 1-line revert to "I:DXY" when Indices
    # plan budgeted ; zero new spend (Voie D rule 16 honored).
    #
    # MARKET-HOURS CAVEAT (acknowledged ADR-089 r27 :83 « NYSE RTH
    # only ») : UUP trades NYSE Arca 9:30-16:00 ET only (~6.5h/day,
    # ~21 trading days/30 calendar days = ~136 bars/30d available
    # at 1-min ingestion, ~6.5h/day at 1-hour buckets =~137
    # hour-buckets/30d). Above the `_hourly_returns` `len(rows) <
    # 30` skip threshold by ~4.5×. Correlation with FX pairs (24/5
    # trading) is restricted to NYSE-hour intersection = ~137
    # overlapping hours/30d ; reflects NY-session co-movement
    # specifically (NOT Tokyo/London hour ρ). Honest scope ; matches
    # SPY-SPX precedent.
    #
    # KNOWN LIMITATION (alert recalibration deferred r172b+) : the
    # DXY_BREAKOUT_UP / DXY_BREAKOUT_DOWN alerts in
    # `alerts/catalog.py:73-76` use thresholds 105 / 100 (DXY index
    # levels). Post-r172 the metric resolver sees UUP-scale prices
    # ($25-30 typical) so the thresholds never cross — alerts stay
    # silent (identical to pre-r172 outcome, where they were silent
    # because polygon_intraday had zero DXY rows). A future r172b+
    # ships either (a) recalibrated UUP-scale thresholds (UUP ≈
    # $26.5 ↔ DXY 100 ; UUP ≈ $27.83 ↔ DXY 105) OR (b)
    # `services/uup_to_dxy_proxy.py` empirical multiplier layer
    # mirroring the deferred `spy_to_spx_proxy.py` in ADR-089.
    # ADR-099 §Impl(r172) documents the decision matrix.
    "DXY": "UUP",  # was "I:DXY" — 403 on Stocks Starter plan ; ADR-089-mirror
    # ── FX peg pairs — drive FX_PEG_BREAK (catalog metric='fx_peg_dev',
    # threshold 1% above, crisis_mode=True) :
    #   USD/HKD : Hong Kong Convertibility Undertaking ±0.05 around 7.80
    #   USD/CNH : PBOC managed band ±2% from daily fix (offshore yuan)
    # Collector pulls 1-min bars ; the alert hook computes deviation
    # from the canonical peg level (USDHKD 7.80) or a rolling proxy
    # (USDCNH 30d mean as fix-substitute).
    "USD_HKD": "C:USDHKD",
    "USD_CNH": "C:USDCNH",
}


@dataclass(frozen=True)
class PolygonBar:
    """One 1-min OHLCV bar parsed from a Polygon /v2/aggs response."""

    asset: str
    ticker: str
    bar_ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int | None
    vwap: float | None
    transactions: int | None


def _epoch_ms_to_dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000.0, tz=UTC)


def _safe_float(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _safe_int(v: Any) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def parse_aggs_response(asset: str, ticker: str, body: dict[str, Any]) -> list[PolygonBar]:
    """Convert a Polygon /v2/aggs JSON body into PolygonBar dataclasses.

    Polygon shape :
        {"status": "OK", "ticker": "...", "results": [{"t": <ms>, "o": ..., "h": ..., "l": ..., "c": ..., "v": ..., "vw": ..., "n": ...}, ...]}

    Discards rows missing any of OHLC. Volume / vwap / transactions are
    optional (some non-FX tickers omit them).
    """
    results = body.get("results") or []
    out: list[PolygonBar] = []
    for r in results:
        try:
            o = float(r["o"])
            h = float(r["h"])
            lo = float(r["l"])
            c = float(r["c"])
        except (KeyError, TypeError, ValueError):
            continue
        ts_ms = r.get("t")
        if not isinstance(ts_ms, int):
            continue
        # OHLC envelope normalization — Polygon is generally clean but
        # we keep the same defensive guard the Phase-0 collector uses
        # (some sources emit low > close by ulps).
        lo_n = min(o, h, lo, c)
        hi_n = max(o, h, lo, c)
        out.append(
            PolygonBar(
                asset=asset,
                ticker=ticker,
                bar_ts=_epoch_ms_to_dt(ts_ms),
                open=o,
                high=hi_n,
                low=lo_n,
                close=c,
                volume=_safe_int(r.get("v")),
                vwap=_safe_float(r.get("vw")),
                transactions=_safe_int(r.get("n")),
            )
        )
    return out


async def fetch_aggs(
    asset: str,
    *,
    api_key: str,
    from_date: date,
    to_date: date,
    multiplier: int = 1,
    timespan: str = "minute",
    limit: int = 50_000,
    client: httpx.AsyncClient | None = None,
) -> list[PolygonBar]:
    """Fetch and parse aggregate bars for one asset over a date window.

    Uses an injected `httpx.AsyncClient` when provided (lets the caller
    pool connections across many assets); otherwise opens a one-shot
    client.
    """
    ticker = ASSET_TO_TICKER.get(asset)
    if ticker is None:
        raise ValueError(f"unknown asset code for Polygon: {asset!r}")

    url = (
        f"{POLYGON_BASE_URL}/v2/aggs/ticker/{ticker}/range/"
        f"{multiplier}/{timespan}/{from_date.isoformat()}/{to_date.isoformat()}"
    )
    params = {
        "adjusted": "true",
        "sort": "asc",
        "limit": str(limit),
        "apiKey": api_key,
    }

    own_client = client is None
    cli = client or httpx.AsyncClient(timeout=30.0)
    try:
        r = await cli.get(url, params=params)
        r.raise_for_status()
        body = r.json()
    finally:
        if own_client:
            await cli.aclose()

    return parse_aggs_response(asset, ticker, body)


def supported_assets() -> tuple[str, ...]:
    return tuple(sorted(ASSET_TO_TICKER.keys()))
