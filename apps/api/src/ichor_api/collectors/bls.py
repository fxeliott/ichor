"""BLS collector — Bureau of Labor Statistics public data API.

BLS publishes monthly employment + inflation series (CPI, PPI, NFP details
beyond FRED's `PAYEMS`). Free tier: 25 queries/day with no API key, 500/day
with a registered key — we use the free no-key endpoint and cache hard.

Endpoint: https://api.bls.gov/publicAPI/v2/timeseries/data/{series_id}
Format:   JSON; one observation per period (month).

Series Ichor cares about (no FRED overlap):
  - CES0500000003   Avg hourly earnings, total private (wage inflation)
  - CES0500000010   Total nonfarm hours all employees (productivity)
  - LNS14000000     U-3 unemployment rate (matches FRED UNRATE — kept for
                    cross-source verification)
  - CIU2010000000000A  Employment Cost Index (quarterly, key Fed input)
  - WPSFD41         Producer Price Index, finished goods
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx

BLS_BASE = "https://api.bls.gov/publicAPI/v2/timeseries/data"

SERIES_TO_POLL: tuple[str, ...] = (
    "CES0500000003",
    "CES0500000010",
    "LNS14000000",
    "CIU2010000000000A",
    "WPSFD41",
)


@dataclass(frozen=True)
class BlsObservation:
    series_id: str
    period: str  # "M01"..."M12" or "Q01"..."Q04"
    period_year: int
    value: float | None
    observation_date: date
    fetched_at: datetime


def _period_to_date(year: int, period: str) -> date | None:
    """Convert BLS period ('M03', 'Q02', 'A01') to a representative date."""
    p = (period or "").strip().upper()
    try:
        if p.startswith("M"):
            month = int(p[1:])
            if 1 <= month <= 12:
                return date(year, month, 1)
        elif p.startswith("Q"):
            q = int(p[1:])
            month = {1: 1, 2: 4, 3: 7, 4: 10}.get(q)
            if month:
                return date(year, month, 1)
        elif p.startswith("A"):
            return date(year, 1, 1)
    except ValueError:
        return None
    return None


def parse_bls_response(body: dict, series_id: str) -> list[BlsObservation]:
    """Convert a BLS JSON body for one series into observations."""
    series_blocks = (body.get("Results") or {}).get("series") or []
    if not series_blocks:
        return []
    target = next((s for s in series_blocks if s.get("seriesID") == series_id), None)
    if target is None:
        return []
    fetched = datetime.now(UTC)
    out: list[BlsObservation] = []
    for d in target.get("data") or []:
        try:
            year = int(d.get("year"))
        except (TypeError, ValueError):
            continue
        period = str(d.get("period") or "")
        obs_date = _period_to_date(year, period)
        if obs_date is None:
            continue
        v: float | None
        try:
            v = float(d.get("value")) if d.get("value") not in (None, "", ".") else None
        except (TypeError, ValueError):
            v = None
        out.append(
            BlsObservation(
                series_id=series_id,
                period=period,
                period_year=year,
                value=v,
                observation_date=obs_date,
                fetched_at=fetched,
            )
        )
    return out


async def fetch_series(
    series_id: str,
    *,
    api_key: str = "",
    timeout_s: float = 20.0,
) -> list[BlsObservation]:
    """Fetch the BLS series. Returns observations newest-first."""
    headers = {"Content-Type": "application/json"}
    payload: dict[str, object] = {"seriesid": [series_id]}
    if api_key:
        payload["registrationkey"] = api_key
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.post(BLS_BASE, json=payload, headers=headers)
            r.raise_for_status()
            return parse_bls_response(r.json(), series_id)
    except httpx.HTTPError:
        return []
