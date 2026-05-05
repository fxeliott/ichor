"""EIA OpenData v2 collector — petroleum STEO + weekly stocks.

Free with registration: https://www.eia.gov/opendata/register.php
~5,000 calls/hour after registration; ~unlimited for batch v2 endpoints.

Series Ichor cares about (drives WTI / oil-correlation regimes):
  - PET.WCESTUS1.W       — Crude oil ending stocks (weekly, kbbl)
  - PET.WCRSTUS1.W       — Commercial crude inventories (weekly, kbbl)
  - PET.WTTSTUS1.W       — Total petroleum products supplied (weekly)
  - STEO.WTIPUUS.M       — STEO WTI forecast (monthly, $/bbl)
  - STEO.PAPRPUS.M       — STEO US crude production forecast
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

EIA_BASE = "https://api.eia.gov/v2"


@dataclass(frozen=True)
class EiaObservation:
    series_id: str
    period: str  # "2026-04" or "2026-04-25"
    value: float | None
    unit: str | None
    fetched_at: datetime


SERIES_TO_POLL: tuple[str, ...] = (
    "petroleum/stoc/wstk/data",  # weekly stocks endpoint
    "steo/data",  # short-term energy outlook
)


def _safe_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


async def fetch_weekly_petroleum_stocks(
    *,
    api_key: str,
    series_ids: tuple[str, ...] = ("WCESTUS1", "WCRSTUS1", "WTTSTUS1"),
    timeout_s: float = 30.0,
    last_n_obs: int = 12,
) -> list[EiaObservation]:
    """Pull weekly petroleum stocks for the listed series.

    Endpoint: /petroleum/stoc/wstk/data with `series` filter.
    """
    if not api_key:
        return []
    url = f"{EIA_BASE}/petroleum/stoc/wstk/data/"
    params: dict[str, Any] = {
        "api_key": api_key,
        "frequency": "weekly",
        "data[]": "value",
        "facets[series][]": list(series_ids),
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": last_n_obs * len(series_ids),
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            body = r.json()
    except httpx.HTTPError:
        return []

    response = body.get("response") or {}
    rows = response.get("data") or []
    fetched = datetime.now(UTC)
    out: list[EiaObservation] = []
    for row in rows:
        sid = str(row.get("series") or "")
        period = str(row.get("period") or "")
        val = _safe_float(row.get("value"))
        if not sid or not period:
            continue
        out.append(
            EiaObservation(
                series_id=sid,
                period=period,
                value=val,
                unit=row.get("units"),
                fetched_at=fetched,
            )
        )
    return out


async def fetch_steo(
    *,
    api_key: str,
    series_ids: tuple[str, ...] = ("WTIPUUS", "PAPRPUS"),
    timeout_s: float = 30.0,
    last_n_obs: int = 24,
) -> list[EiaObservation]:
    """Pull Short-Term Energy Outlook monthly forecasts."""
    if not api_key:
        return []
    url = f"{EIA_BASE}/steo/data/"
    params: dict[str, Any] = {
        "api_key": api_key,
        "frequency": "monthly",
        "data[]": "value",
        "facets[seriesId][]": list(series_ids),
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": last_n_obs * len(series_ids),
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            body = r.json()
    except httpx.HTTPError:
        return []

    response = body.get("response") or {}
    rows = response.get("data") or []
    fetched = datetime.now(UTC)
    out: list[EiaObservation] = []
    for row in rows:
        sid = str(row.get("seriesId") or row.get("series") or "")
        period = str(row.get("period") or "")
        val = _safe_float(row.get("value"))
        if not sid or not period:
            continue
        out.append(
            EiaObservation(
                series_id=sid,
                period=period,
                value=val,
                unit=row.get("units"),
                fetched_at=fetched,
            )
        )
    return out
