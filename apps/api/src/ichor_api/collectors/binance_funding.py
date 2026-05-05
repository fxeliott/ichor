"""Binance Futures funding rate collector — crypto regime overlay.

Why this exists for Ichor :
  - BTC/ETH perpetual funding rates are the cleanest read on crypto
    speculative leverage. Sustained positive funding (longs paying
    shorts) flags euphoria ; sustained negative flags capitulation.
  - These regimes correlate with NAS100 / SPX risk-on/off shifts on a
    days-to-weeks horizon.

Endpoint (verified 2026-05-05) :
  GET https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=N
  Response: list of {symbol, fundingRate (str), fundingTime (ms), markPrice}

  No auth, rate limit 500/5min/IP (per official docs). Funding settles
  every 8h on USDⓈ-M perpetuals.

Source:
  - https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

BINANCE_FAPI = "https://fapi.binance.com"

# Symbols we poll. BTC + ETH cover ~85% of perp open interest ; the
# rest tracks them within a few percent so polling more is overkill
# at our daily cadence.
WATCHED_SYMBOLS: tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "SOLUSDT")


@dataclass(frozen=True)
class FundingRateRecord:
    """One funding settlement on a Binance USDⓈ-M perpetual."""

    symbol: str
    funding_time: datetime
    funding_rate: float
    """Signed rate per 8h period — positive = longs pay shorts.
    Annualized ≈ rate × 3 (settlements/day) × 365."""

    mark_price: float | None
    fetched_at: datetime


def _to_float(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def parse_funding_response(symbol: str, body: list[Any]) -> list[FundingRateRecord]:
    """Binance returns a sorted list (oldest → newest)."""
    out: list[FundingRateRecord] = []
    if not isinstance(body, list):
        return out
    now = datetime.now(UTC)
    for row in body:
        if not isinstance(row, dict):
            continue
        ft = row.get("fundingTime")
        if ft is None:
            continue
        try:
            funding_time = datetime.fromtimestamp(int(ft) / 1000.0, tz=UTC)
        except (TypeError, ValueError, OSError):
            continue
        rate = _to_float(row.get("fundingRate"))
        if rate is None:
            continue
        out.append(
            FundingRateRecord(
                symbol=symbol,
                funding_time=funding_time,
                funding_rate=rate,
                mark_price=_to_float(row.get("markPrice")),
                fetched_at=now,
            )
        )
    return out


async def fetch_funding_history(
    symbol: str,
    *,
    limit: int = 100,
    timeout_s: float = 15.0,
) -> list[FundingRateRecord]:
    """Pull last `limit` funding settlements for a symbol (max 1000)."""
    if limit < 1 or limit > 1000:
        raise ValueError(f"limit must be in [1, 1000], got {limit}")
    url = f"{BINANCE_FAPI}/fapi/v1/fundingRate"
    headers = {"User-Agent": "IchorBinanceFundingCollector/0.1"}
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.get(url, params={"symbol": symbol, "limit": limit}, headers=headers)
            r.raise_for_status()
            return parse_funding_response(symbol, r.json())
    except httpx.HTTPError:
        return []


async def poll_all(
    *,
    symbols: tuple[str, ...] = WATCHED_SYMBOLS,
    limit: int = 100,
) -> list[FundingRateRecord]:
    """Pull last `limit` settlements for each watched symbol concurrently."""
    import asyncio

    results = await asyncio.gather(
        *(fetch_funding_history(s, limit=limit) for s in symbols)
    )
    flat: list[FundingRateRecord] = []
    for batch in results:
        flat.extend(batch)
    return flat


def annualize_rate(rate_per_8h: float) -> float:
    """Convert one-period funding rate to a comparable annualized %.

    Binance USDⓈ-M settles every 8h → 3 settlements/day × 365 = 1095
    compounding periods per year. For typical small rates we use the
    linear approximation (sufficient for the regime signal).
    """
    return rate_per_8h * 3.0 * 365.0


def supported_symbols() -> tuple[str, ...]:
    return WATCHED_SYMBOLS
