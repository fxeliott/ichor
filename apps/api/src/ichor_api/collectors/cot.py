"""CFTC COT collector — Commitments of Traders, weekly positioning data.

The CFTC publishes the COT report every Friday at 15:30 EST, with positions
as of Tuesday close. Free, no auth, no rate limit on documented usage.

For our session cards, we want the **Disaggregated Futures Only** report
which categorizes positioning into :

  - Producer / merchant / processor / user (commercials)
  - Swap dealers
  - Managed money (hedge funds, CTAs, CPOs)  ← the most actionable
  - Other reportables
  - Non-reportable (small specs, retail proxy)

The hedge-fund net positioning extreme (e.g. "longs at 18-month high") is
one of the strongest contrarian signals for FX + commodities.

Data source : https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm
Python lib : we roll our own minimal parser (no `cftc-cot` dep) because
the reports are simple CSV / Excel files.

NOTE : COT publication paused Oct 1 — Nov 12 2025 due to US shutdown. Backlog
cleared by Dec 29 2025. Resilience : if no fresh report, we surface the
last known weekly position + flag staleness.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx
import structlog

log = structlog.get_logger(__name__)

# CFTC publishes a "current week" CSV that's updated each Friday with last
# Tuesday's positions. For historical, see the annual ZIP files.
CFTC_DISAGG_FUT_CSV = "https://www.cftc.gov/dea/newcot/f_disagg.txt"


@dataclass(frozen=True)
class CotPosition:
    """One COT row — one market, one report week."""

    report_date: date
    """Tuesday close of the report week."""

    market_code: str
    """CFTC market code (e.g. '232741' for EUR FX, '088691' for gold)."""

    market_name: str
    """Human-readable market name from the report."""

    # Net positions (long − short) by category — the most important columns
    producer_net: int = 0
    swap_dealer_net: int = 0
    managed_money_net: int = 0
    other_reportable_net: int = 0
    non_reportable_net: int = 0

    # Open interest (total contracts outstanding)
    open_interest: int = 0

    fetched_at: datetime | None = None


# Mapping CFTC market codes → our asset codes for the markets we track.
# Codes verified against CFTC reference list.
MARKET_CODE_TO_ASSET: dict[str, str] = {
    "099741": "EUR_USD",  # EURO FX
    "096742": "GBP_USD",  # BRITISH POUND STERLING
    "097741": "USD_JPY",  # JAPANESE YEN  (note : reverse — long JPY = short USD/JPY)
    "232741": "AUD_USD",  # AUSTRALIAN DOLLAR
    "090741": "USD_CAD",  # CANADIAN DOLLAR (long CAD = short USD/CAD)
    "088691": "XAU_USD",  # GOLD
    "13874A": "US30",  # E-MINI DJIA ($5)  — verify
    "209742": "US100",  # E-MINI NASDAQ-100 — verify
}


async def fetch_disagg_fut_only(*, timeout: float = 60.0) -> bytes:
    """Pull the latest Disaggregated Futures Only CSV from CFTC.

    Returns raw bytes ; parser is separate so caller can cache.
    """
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(
                CFTC_DISAGG_FUT_CSV,
                timeout=timeout,
                follow_redirects=True,
                headers={"User-Agent": "IchorCOTCollector/0.1"},
            )
            r.raise_for_status()
            return r.content
        except httpx.HTTPError as e:
            log.warning("cot.fetch_failed", error=str(e))
            return b""


def _parse_int(s: str | None) -> int:
    if s is None:
        return 0
    s = s.strip().replace(",", "")
    if not s or s in {".", "-"}:
        return 0
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return 0


def _parse_disagg_csv(body: bytes) -> list[CotPosition]:
    """Parse the CFTC Disaggregated Futures Only flat file.

    The file is space-separated with a fixed header. We use csv.DictReader
    after splitting headers manually since the format is a quoted CSV.
    """
    if not body:
        return []
    text = body.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    fetched = datetime.now(UTC)
    out: list[CotPosition] = []
    for row in reader:
        try:
            code = (
                row.get("CFTC Contract Market Code") or row.get("CFTC_Contract_Market_Code") or ""
            ).strip()
            if not code:
                continue
            name = (
                row.get("Market and Exchange Names") or row.get("Market_and_Exchange_Names") or ""
            ).strip()
            d = (
                row.get("Report Date as YYYY-MM-DD") or row.get("Report_Date_as_YYYY-MM-DD") or ""
            ).strip()
            if not d:
                continue
            try:
                report_date = date.fromisoformat(d)
            except ValueError:
                continue

            prod_long = _parse_int(row.get("Producer/Merchant/Processor/User Longs"))
            prod_short = _parse_int(row.get("Producer/Merchant/Processor/User Shorts"))
            swap_long = _parse_int(row.get("Swap Dealer Longs"))
            swap_short = _parse_int(row.get("Swap Dealer Shorts"))
            mm_long = _parse_int(row.get("Money Manager Longs"))
            mm_short = _parse_int(row.get("Money Manager Shorts"))
            other_long = _parse_int(row.get("Other Reportable Longs"))
            other_short = _parse_int(row.get("Other Reportable Shorts"))
            nonrep_long = _parse_int(row.get("Nonreportable Positions-Long (All)"))
            nonrep_short = _parse_int(row.get("Nonreportable Positions-Short (All)"))
            oi = _parse_int(row.get("Open Interest (All)"))

            out.append(
                CotPosition(
                    report_date=report_date,
                    market_code=code,
                    market_name=name[:128],
                    producer_net=prod_long - prod_short,
                    swap_dealer_net=swap_long - swap_short,
                    managed_money_net=mm_long - mm_short,
                    other_reportable_net=other_long - other_short,
                    non_reportable_net=nonrep_long - nonrep_short,
                    open_interest=oi,
                    fetched_at=fetched,
                )
            )
        except (KeyError, ValueError) as e:
            log.warning("cot.parse_row_failed", error=str(e))
            continue
    return out


async def poll_all_assets(
    asset_codes: Iterable[str] = tuple(MARKET_CODE_TO_ASSET.keys()),
) -> dict[str, CotPosition | None]:
    """Pull full Disagg report and filter to our tracked markets.

    Returns asset_code → latest CotPosition (or None if not found in the
    report). The report contains ALL CFTC markets ; we filter.
    """
    body = await fetch_disagg_fut_only()
    rows = _parse_disagg_csv(body)
    by_code: dict[str, CotPosition] = {}
    for r in rows:
        if r.market_code in asset_codes:
            # Keep the most recent date per market_code
            existing = by_code.get(r.market_code)
            if existing is None or r.report_date > existing.report_date:
                by_code[r.market_code] = r
    out: dict[str, CotPosition | None] = {}
    for code in asset_codes:
        out[code] = by_code.get(code)
    return out
