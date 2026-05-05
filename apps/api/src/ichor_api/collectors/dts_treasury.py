"""Treasury DTS (Daily Treasury Statement) collector.

The DTS is the daily flow-of-funds for the US federal government — net
operating cash, net debt issuance, Treasury General Account (TGA) level.
Heavily used by macro funds for liquidity timing.

Source: Treasury FiscalData API
  https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/operating_cash_balance

Free, no API key, very generous rate limits.

The TGA balance crosses with the FRED `WTREGEN` series (already in fred.py)
but FRED lags 1 day; DTS is intraday-of-EOD.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx

TREASURY_BASE = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"

OPERATING_CASH_ENDPOINT = "/v1/accounting/dts/operating_cash_balance"


@dataclass(frozen=True)
class DtsCashBalance:
    """One row from the Operating Cash Balance dataset."""

    record_date: date
    account_type: str
    """e.g. 'Treasury General Account (TGA) Closing Balance', 'Federal Reserve
    Account', 'Tax and Loan Note Accounts'."""

    closing_balance_usd_mn: Decimal | None
    """Closing balance in millions of USD."""

    fetched_at: datetime


def _parse_date(s: str) -> date | None:
    try:
        return date.fromisoformat((s or "").strip())
    except ValueError:
        return None


def _parse_decimal(s: str) -> Decimal | None:
    s = (s or "").strip()
    if not s or s == "null":
        return None
    try:
        return Decimal(s)
    except (ValueError, ArithmeticError):
        return None


def parse_dts_response(body: dict) -> list[DtsCashBalance]:
    """Extract operating-cash rows. Newest record_date first."""
    rows = body.get("data") or []
    fetched = datetime.now(UTC)
    out: list[DtsCashBalance] = []
    for r in rows:
        rec = _parse_date(r.get("record_date", ""))
        if rec is None:
            continue
        out.append(
            DtsCashBalance(
                record_date=rec,
                account_type=str(r.get("account_type") or ""),
                closing_balance_usd_mn=_parse_decimal(str(r.get("close_today_bal", ""))),
                fetched_at=fetched,
            )
        )
    out.sort(key=lambda x: x.record_date, reverse=True)
    return out


async def fetch_operating_cash(
    *,
    days: int = 30,
    timeout_s: float = 20.0,
) -> list[DtsCashBalance]:
    """Latest N days of operating cash balance rows.

    The endpoint paginates; we ask for `pagesize=days * 4` because each
    record_date typically yields 3-4 account_type rows (TGA + FRA + TLA).
    """
    # FiscalData filter syntax expects ISO date for date columns: `gte:YYYY-MM-DD`.
    # Earlier draft used `date.today().toordinal() - days` which produced an int
    # (~739000) and the API rejected it.
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    params = {
        "fields": "record_date,account_type,close_today_bal",
        "filter": f"record_date:gte:{cutoff}",
        "sort": "-record_date",
        "page[size]": str(max(days * 4, 50)),
    }
    headers = {"Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.get(
                TREASURY_BASE + OPERATING_CASH_ENDPOINT,
                params=params,
                headers=headers,
            )
            r.raise_for_status()
            return parse_dts_response(r.json())
    except httpx.HTTPError:
        return []


def latest_tga_close(rows: list[DtsCashBalance]) -> DtsCashBalance | None:
    """Pick the freshest 'Treasury General Account (TGA) Closing Balance'."""
    for r in rows:
        if "Treasury General Account" in r.account_type and "Closing Balance" in r.account_type:
            return r
    return None
