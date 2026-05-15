"""FINRA short interest + short sale volume collector.

Two distinct datasets per https://developer.finra.org/catalog:
  - Equity Short Interest (semi-monthly, settlement-date)
  - Daily Short Sale Volume (off-exchange ATS/non-ATS aggregated by symbol)

r53 update : the FINRA Data API at `api.finra.org/data/group/.../regShoDaily`
requires an OAuth token for `compareFilters` queries (developer.finra.org
catalog) ; without `finra_api_token` set, every fetch returns 401 silently
swallowed -> 0 rows -> ExitStatus=1. This was the root cause of
`finra_short` being silent-dead since collector inception (per r52
wave-2 subagent M finding).

The FREE public alternative is the FINRA CDN flat-file at
`https://cdn.finra.org/equity/regsho/daily/CNMSshvol{YYYYMMDD}.txt` —
pipe-delimited daily file, ALL US equity symbols (~10 000 rows, ~500 KB).
Verified r53 2026-05-15 from Hetzner : returns HTTP 200 on business
days, HTTP 403 on weekends/holidays (no file published).
Format header :
  Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market

We filter to Ichor's tracked universe client-side. No token, no rate
limit (CDN-cached). Voie D respect : no paid API.

Cf https://quant-trading.co/how-to-download-data-from-the-finra-api/
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)

FINRA_BASE = "https://api.finra.org/data/group"

# r53 : Public CDN flat-file alternative (no OAuth). Akamai-fronted, large
# (~500 KB/day, all US equity symbols). Filtered client-side to Ichor's
# tracked universe. URL date format : YYYYMMDD.
FINRA_FLATFILE_BASE = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{date}.txt"
# How many days back to walk if the most recent date is 403/404 (weekend
# or holiday). Covers max 4-day Easter weekend + buffer.
FINRA_FLATFILE_MAX_LOOKBACK_DAYS = 7
# Realistic browser UA — even though the CDN doesn't typically gate, we
# follow the pattern from r52 nyfed_mct fix (anti-WAF defense in depth).
_FLATFILE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/plain,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


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


# ─── r53 : public flat-file path (no OAuth, free) ────────────────────────


def _parse_flatfile(text: str, symbols_filter: frozenset[str]) -> list[DailyShortVolumeRecord]:
    """Parse a FINRA Reg SHO daily flat-file body. Filter to symbols.

    Format is pipe-delimited ;  header row :
        Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market
    Data rows :
        20260514|SPY|319623.012649|406|610811.274367|B,Q,N

    Trailing footer row may exist (e.g. "FileFormat=..." or empty line) ;
    we skip rows with non-numeric date or not in symbols_filter.
    Volumes from FINRA are floats (typically ".0" but sometimes fractional
    when ATS reports partial shares) — `_safe_int` handles via float()
    intermediate.
    """
    fetched = datetime.now(UTC)
    out: list[DailyShortVolumeRecord] = []
    lines = text.splitlines()
    if not lines:
        return out

    # Skip header line, parse rest. Tolerant of footer rows.
    for raw in lines[1:]:
        cells = raw.split("|")
        if len(cells) < 5:
            continue
        sym = (cells[1] or "").strip().upper()
        if sym not in symbols_filter:
            continue
        td = _parse_date(cells[0])
        if td is None:
            continue
        short_vol = _safe_int(cells[2])
        short_exempt = _safe_int(cells[3])
        total_vol = _safe_int(cells[4])
        out.append(
            DailyShortVolumeRecord(
                symbol=sym,
                trade_date=td,
                short_volume=short_vol,
                short_exempt_volume=short_exempt,
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


async def fetch_daily_short_volume_flatfile(
    symbols: tuple[str, ...],
    *,
    trade_date: date | None = None,
    timeout_s: float = 30.0,
    max_lookback_days: int = FINRA_FLATFILE_MAX_LOOKBACK_DAYS,
) -> list[DailyShortVolumeRecord]:
    """Fetch the FINRA Reg SHO daily public flat-file for the most recent
    business day not exceeding `trade_date` (default = yesterday).

    Walks back up to `max_lookback_days` days if 403/404 (weekend/holiday).
    Returns empty list if no business-day file found in the window — caller
    treats this as soft-skip (e.g. long holiday weekend), NOT as failure.

    Voie D respect : no API token, no auth. Free CDN-cached endpoint.
    """
    if trade_date is None:
        # Yesterday by default — today's file isn't published until
        # FINRA processes overnight (T+1).
        trade_date = date.today() - timedelta(days=1)

    symbols_filter = frozenset(s.upper() for s in symbols)
    candidate = trade_date

    async with httpx.AsyncClient(timeout=timeout_s, headers=_FLATFILE_HEADERS) as client:
        for _ in range(max_lookback_days + 1):
            url = FINRA_FLATFILE_BASE.format(date=candidate.strftime("%Y%m%d"))
            try:
                r = await client.get(url)
                if r.status_code == 200 and r.text:
                    return _parse_flatfile(r.text, symbols_filter)
                if r.status_code in (403, 404):
                    # Weekend / holiday — file not published.
                    candidate = candidate - timedelta(days=1)
                    continue
                # Other status (5xx, 429) — log and walk back too.
                log.warning(
                    "finra_short.flatfile_unexpected_status",
                    url=url,
                    status=r.status_code,
                )
                candidate = candidate - timedelta(days=1)
            except httpx.HTTPError as exc:
                log.warning("finra_short.flatfile_fetch_error", url=url, error=str(exc))
                candidate = candidate - timedelta(days=1)

    log.warning(
        "finra_short.flatfile_no_business_day_found",
        trade_date=trade_date.isoformat(),
        max_lookback_days=max_lookback_days,
    )
    return []
