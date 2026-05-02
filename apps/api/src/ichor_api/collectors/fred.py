"""FRED collector — pulls St. Louis Fed economic data series.

Strategy: poll the latest observation for each series we care about, then
write to a `fred_observations` time-series table (TimescaleDB).

Free tier: ~120 req/min (per AUDIT_V3 §7). With 30 series × 24 polls/day
= 720 calls/day = trivial.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import structlog

log = structlog.get_logger(__name__)

FRED_BASE = "https://api.stlouisfed.org/fred"

# Series Ichor cares about (per ARCHITECTURE_FINALE + AUDIT_V3)
SERIES_TO_POLL: tuple[str, ...] = (
    # Credit
    "BAMLH0A0HYM2",      # HY OAS spread
    "BAMLC0A0CMTRIV",    # IG OAS spread
    # Vol
    "VIXCLS",            # VIX
    # Rates
    "SOFR",              # secured overnight financing
    "DFF",               # Federal funds effective
    "DGS2", "DGS10",     # Treasury 2y and 10y
    # Macro
    "CPIAUCSL",          # CPI all urban
    "PCEPI",             # PCE price index
    "PAYEMS",            # NFP total
    "UNRATE",            # Unemployment rate
    "GDPC1",             # Real GDP
    "INDPRO",            # Industrial production
    # Money
    "M2SL",              # M2
    "WALCL",             # Fed balance sheet
    "RRPONTSYD",         # Reverse repo overnight
    "WTREGEN",           # Treasury General Account
    # FX
    "DTWEXBGS",          # Trade-weighted dollar (broad)
    # Commodities
    "DCOILWTICO",        # WTI crude
    "GOLDAMGBD228NLBM",  # Gold London PM fix
)


@dataclass
class FredObservation:
    series_id: str
    observation_date: str  # ISO date "2026-05-02"
    value: float | None
    fetched_at: datetime


async def fetch_latest(series_id: str, api_key: str, *, client: httpx.AsyncClient) -> FredObservation | None:
    """One series, latest observation. Returns None if unavailable."""
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 1,
    }
    try:
        r = await client.get(f"{FRED_BASE}/series/observations", params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        obs = data.get("observations", [])
        if not obs:
            return None
        o = obs[0]
        val_str = o.get("value", ".")
        # FRED uses "." for missing
        value = None if val_str == "." else float(val_str)
        return FredObservation(
            series_id=series_id,
            observation_date=o["date"],
            value=value,
            fetched_at=datetime.now(timezone.utc),
        )
    except Exception as e:
        log.warning("fred.fetch_failed", series=series_id, error=str(e))
        return None


async def poll_all(api_key: str, series: tuple[str, ...] = SERIES_TO_POLL) -> list[FredObservation]:
    """Poll every series in parallel (gated by httpx connection pool)."""
    async with httpx.AsyncClient() as client:
        tasks = [fetch_latest(s, api_key, client=client) for s in series]
        results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]
