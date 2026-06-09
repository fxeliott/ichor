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

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)

# CFTC public-reporting Socrata SODA endpoint, resource `72hh-3qpy`
# (Disaggregated Futures-Only Combined). Verified live 2026-06-09: returns
# GOLD (088691) with prod_merc / swap / m_money / nonrept fields, report 2026-06-02.
#
# Why Socrata, not the legacy `f_disagg.txt` flat file: that file is HEADERLESS
# (its first line is a DATA row, not column names), so the old csv.DictReader
# parser resolved ZERO rows in prod — every tracked market logged "not in this
# week's report" and the cron exited 1, leaving cot_positions empty — while the
# unit test passed against a synthetic header row (a false-green). The TFF
# sibling already uses this Socrata path successfully; we mirror it exactly:
# clean named JSON fields + server-side `$where` filter.
CFTC_DISAGG_SODA_URL = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"
_HEADERS = {"User-Agent": "IchorCOTCollector/0.2 (Voie D; CFTC public domain)"}


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


def _to_int(value: Any) -> int:
    """Socrata returns numerics as strings — coerce safely. Empty/None/
    '.' (CFTC missing-data sentinel) → 0. Mirror of cftc_tff._to_int."""
    if value is None or value == "" or value == ".":
        return 0
    try:
        return int(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0


def parse_socrata_response(payload: Any) -> list[CotPosition]:
    """Pure parser — extract Disaggregated COT rows from Socrata JSON.

    Returns [] on any structural mismatch ; never raises. Field names verified
    live 2026-06-09 against resource `72hh-3qpy` (the swap SHORT field carries a
    DOUBLE underscore — `swap__positions_short_all` — a real CFTC schema quirk).
    """
    if not isinstance(payload, list):
        log.warning("cot.parse_payload_not_list", type=type(payload).__name__)
        return []

    fetched = datetime.now(UTC)
    out: list[CotPosition] = []
    for row in payload:
        try:
            iso = row.get("report_date_as_yyyy_mm_dd")
            if not iso:
                continue
            try:
                report_date = datetime.fromisoformat(iso.replace("Z", "+00:00")).date()
            except (TypeError, ValueError):
                try:
                    report_date = date.fromisoformat(iso[:10])
                except (TypeError, ValueError):
                    continue
            code = str(row.get("cftc_contract_market_code") or "").strip()
            if not code:
                continue

            prod_long = _to_int(row.get("prod_merc_positions_long"))
            prod_short = _to_int(row.get("prod_merc_positions_short"))
            swap_long = _to_int(row.get("swap_positions_long_all"))
            swap_short = _to_int(row.get("swap__positions_short_all"))  # sic: double underscore
            mm_long = _to_int(row.get("m_money_positions_long_all"))
            mm_short = _to_int(row.get("m_money_positions_short_all"))
            other_long = _to_int(row.get("other_rept_positions_long"))
            other_short = _to_int(row.get("other_rept_positions_short"))
            nonrep_long = _to_int(row.get("nonrept_positions_long_all"))
            nonrep_short = _to_int(row.get("nonrept_positions_short_all"))
            oi = _to_int(row.get("open_interest_all"))

            out.append(
                CotPosition(
                    report_date=report_date,
                    market_code=code,
                    market_name=str(row.get("market_and_exchange_names") or "")[:128],
                    producer_net=prod_long - prod_short,
                    swap_dealer_net=swap_long - swap_short,
                    managed_money_net=mm_long - mm_short,
                    other_reportable_net=other_long - other_short,
                    non_reportable_net=nonrep_long - nonrep_short,
                    open_interest=oi,
                    fetched_at=fetched,
                )
            )
        except (KeyError, TypeError, ValueError) as e:
            log.warning("cot.row_skip", error=str(e), row_id=row.get("id"))
            continue
    return out


async def fetch_recent(
    *,
    weeks_lookback: int = 8,
    market_codes: Iterable[str] = tuple(MARKET_CODE_TO_ASSET.keys()),
    client: httpx.AsyncClient | None = None,
) -> list[CotPosition]:
    """Fetch the last `weeks_lookback` weeks of Disaggregated COT for tracked
    markets via the Socrata `$where` server-side filter. Returns [] on any HTTP
    error (best-effort). Mirror of cftc_tff.fetch_recent.

    Only markets actually present in the disaggregated report return rows — the
    FX / equity-index codes live in the TFF report (sibling collector), so they
    legitimately yield nothing here ; GOLD (088691) is the live commodity leg.
    """
    cutoff = (datetime.now(UTC).date() - timedelta(weeks=weeks_lookback)).isoformat()
    quoted = ", ".join(f"'{c}'" for c in market_codes)
    where = (
        f"cftc_contract_market_code IN ({quoted}) "
        f"AND report_date_as_yyyy_mm_dd >= '{cutoff}T00:00:00.000'"
    )
    params: dict[str, Any] = {
        "$where": where,
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "$limit": 5000,
    }
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=20.0, headers=_HEADERS)
    try:
        try:
            assert client is not None
            r = await client.get(CFTC_DISAGG_SODA_URL, params=params)
            r.raise_for_status()
            return parse_socrata_response(r.json())
        except (httpx.HTTPError, ValueError) as e:
            log.warning("cot.fetch_failed", error=str(e))
            return []
    finally:
        if own_client and client is not None:
            await client.aclose()


async def poll_all_assets(
    asset_codes: Iterable[str] = tuple(MARKET_CODE_TO_ASSET.keys()),
) -> dict[str, CotPosition | None]:
    """Pull the Disaggregated COT report (Socrata) and filter to tracked markets.

    Returns asset_code → latest CotPosition (or None if not found in the report,
    e.g. FX / index codes that only live in the TFF report).
    """
    codes = tuple(asset_codes)
    rows = await fetch_recent(market_codes=codes)
    by_code: dict[str, CotPosition] = {}
    for r in rows:
        if r.market_code in codes:
            existing = by_code.get(r.market_code)
            if existing is None or r.report_date > existing.report_date:
                by_code[r.market_code] = r
    return {code: by_code.get(code) for code in codes}
