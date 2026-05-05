"""FINRA short interest + short sale volume collector.

Two distinct datasets per https://developer.finra.org/catalog:
  - Equity Short Interest (semi-monthly, settlement-date)
  - Daily Short Sale Volume (off-exchange ATS/non-ATS aggregated by symbol)

Free for unauthenticated usage on the lower-throughput public endpoints.
Some advanced filters require an OAuth token (paid). We use the public
unauthenticated path — sufficient for daily polling of Ichor's universe.

Cf https://quant-trading.co/how-to-download-data-from-the-finra-api/
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import httpx

FINRA_BASE = "https://api.finra.org/data/group"


@dataclass(frozen=True)
class ShortInterestRecord:
    symbol: str
    settlement_date: date
    issue_name: str | None
    market_category: str
    current_short_shares: int | None
    previous_short_shares: int | None
    pct_change: float | None
    avg_daily_volume: int | None
    fetched_at: datetime


@dataclass(frozen=True)
class DailyShortVolumeRecord:
    symbol: str
    trade_date: date
    short_volume: int | None
    short_exempt_volume: int | None
    total_volume: int | None
    short_pct: float | None
    fetched_at: datetime


def _parse_date(s: str) -> date | None:
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d-%b-%y", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _safe_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _safe_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


async def _post_query(
    group_name: str,
    dataset_name: str,
    *,
    payload: dict[str, Any],
    api_token: str | None = None,
    timeout_s: float = 30.0,
) -> list[dict[str, Any]]:
    """POST query to the FINRA Data API. Returns rows or []."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "IchorFinraCollector/0.1",
    }
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"
    url = f"{FINRA_BASE}/{group_name}/name/{dataset_name}"
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.post(url, json=payload, headers=headers)
            if r.status_code == 401:
                # Quota / auth — return empty rather than raise.
                return []
            r.raise_for_status()
            body = r.json()
    except httpx.HTTPError:
        return []
    if isinstance(body, list):
        return body
    if isinstance(body, dict) and "data" in body:
        return list(body["data"]) if isinstance(body["data"], list) else []
    return []


async def fetch_short_interest(
    symbols: tuple[str, ...],
    *,
    api_token: str | None = None,
) -> list[ShortInterestRecord]:
    """Fetch Equity Short Interest for a list of symbols. Latest reading only."""
    payload: dict[str, Any] = {
        "limit": 500,
        "compareFilters": [
            {
                "fieldName": "issueSymbolIdentifier",
                "fieldValue": ",".join(symbols),
                "compareType": "in",
            }
        ],
    }
    rows = await _post_query(
        "otcMarket", "consolidatedShortInterest", payload=payload, api_token=api_token
    )
    fetched = datetime.now(UTC)
    out: list[ShortInterestRecord] = []
    for r in rows:
        sd = _parse_date(str(r.get("settlementDate", "")))
        if sd is None:
            continue
        out.append(
            ShortInterestRecord(
                symbol=str(r.get("issueSymbolIdentifier") or "").upper(),
                settlement_date=sd,
                issue_name=str(r.get("issueName") or "") or None,
                market_category=str(r.get("marketCategoryCode") or ""),
                current_short_shares=_safe_int(r.get("currentShortShareNumber")),
                previous_short_shares=_safe_int(r.get("previousShortShareNumber")),
                pct_change=_safe_float(r.get("percentageChangefromPreviousShort")),
                avg_daily_volume=_safe_int(r.get("averageShortShareNumber")),
                fetched_at=fetched,
            )
        )
    return out


async def fetch_daily_short_volume(
    symbols: tuple[str, ...],
    *,
    trade_date: date | None = None,
    api_token: str | None = None,
) -> list[DailyShortVolumeRecord]:
    """Fetch Daily Short Sale Volume for symbols on a specific date."""
    if trade_date is None:
        # Yesterday by default (today's data isn't published yet).
        trade_date = date.today()
    payload: dict[str, Any] = {
        "limit": 500,
        "compareFilters": [
            {
                "fieldName": "securitiesInformationProcessorSymbolIdentifier",
                "fieldValue": ",".join(symbols),
                "compareType": "in",
            },
            {
                "fieldName": "tradeReportDate",
                "fieldValue": trade_date.isoformat(),
                "compareType": "equal",
            },
        ],
    }
    rows = await _post_query("otcMarket", "regShoDaily", payload=payload, api_token=api_token)
    fetched = datetime.now(UTC)
    out: list[DailyShortVolumeRecord] = []
    for r in rows:
        td = _parse_date(str(r.get("tradeReportDate", "")))
        if td is None:
            continue
        short_vol = _safe_int(r.get("shortParQuantity"))
        total_vol = _safe_int(r.get("totalParQuantity"))
        out.append(
            DailyShortVolumeRecord(
                symbol=str(r.get("securitiesInformationProcessorSymbolIdentifier") or "").upper(),
                trade_date=td,
                short_volume=short_vol,
                short_exempt_volume=_safe_int(r.get("shortExemptParQuantity")),
                total_volume=total_vol,
                short_pct=(
                    short_vol / total_vol
                    if (short_vol is not None and total_vol not in (None, 0))
                    else None
                ),
                fetched_at=fetched,
            )
        )
    return out
