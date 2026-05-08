"""CFTC TFF (Traders in Financial Futures) collector — weekly positioning.

The TFF report disaggregates open interest in CFTC-regulated financial
futures into 4 trader classes:

  - Dealer / Intermediary       — primary dealers + bank trading desks
                                  (typical : *short* positioning the
                                  passive supply of contracts)
  - Asset Manager / Institutional — pension + endowment + mutual funds
                                  (long-biased real-money allocations)
  - Leveraged Funds             — hedge funds + CTAs (the *active*
                                  speculative voice — momentum + macro)
  - Other Reportables           — corporate hedgers, sovereigns, family
                                  offices not fitting the 3 above
  - Non-Reportable              — small spec, residual

For Ichor it powers macro-fund positioning intelligence on the 8-asset
universe. Specifically: spot when LevFunds positioning diverges from
the spot price (Albert Edwards-style "smart money divergence") or when
Dealer carrying inventory is unsustainable (forced unwind risk).

Source : CFTC public reporting Socrata SODA endpoint, resource ID
`gpe5-46if` (TFF Futures-Only Combined). Subagent verified live
2026-05-08 with 73 fields and report dated 2026-04-28.

Voie D ADR-009: 100% gratuit, no token required (throttled but fine
for a once-per-week cron). No paid SDK.

License: CFTC public domain.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)

CFTC_TFF_SODA_URL = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"

# Whitelist of CFTC market codes Ichor actively tracks. Mapped to the
# `cftc_contract_market_code` field in the Socrata response. We filter
# server-side to keep payloads small and parsing predictable. Codes per
# CFTC market codes registry (verified subset for the 8-asset Phase 1
# universe + Treasury futures).
TRACKED_MARKET_CODES: tuple[str, ...] = (
    "099741",  # EURO FX - CHICAGO MERCANTILE EXCHANGE
    "096742",  # BRITISH POUND - CHICAGO MERCANTILE EXCHANGE
    "097741",  # JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE
    "232741",  # AUSTRALIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE
    "090741",  # CANADIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE
    "092741",  # SWISS FRANC - CHICAGO MERCANTILE EXCHANGE
    "112741",  # NZ DOLLAR - CHICAGO MERCANTILE EXCHANGE
    "13874A",  # E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE
    "209742",  # NASDAQ-100 EMINI - CHICAGO MERCANTILE EXCHANGE
    "239742",  # E-MINI RUSSELL 2000 - CHICAGO MERCANTILE EXCHANGE
    "088691",  # GOLD - COMMODITY EXCHANGE INC.
    "020601",  # 2-YR U.S. T-NOTE - CHICAGO BOARD OF TRADE
    "044601",  # 5-YR U.S. T-NOTE - CHICAGO BOARD OF TRADE
    "043602",  # 10-YR U.S. T-NOTE - CHICAGO BOARD OF TRADE
    "020604",  # 30-YR U.S. T-BOND - CHICAGO BOARD OF TRADE
)

# Map market_code -> Ichor asset_code for downstream data_pool wiring.
MARKET_TO_ASSET: dict[str, str] = {
    "099741": "EUR_USD",
    "096742": "GBP_USD",
    "097741": "USD_JPY",  # JPY positioning is inverted vs USD_JPY pair
    "232741": "AUD_USD",
    "090741": "USD_CAD",  # ditto, inverted
    "092741": "USD_CHF",  # ditto
    "112741": "NZD_USD",
    "13874A": "SPX500_USD",
    "209742": "NAS100_USD",
    "239742": "RUT2000_USD",
    "088691": "XAU_USD",
    "020601": "UST_2Y",
    "044601": "UST_5Y",
    "043602": "UST_10Y",
    "020604": "UST_30Y",
}


# Spoofed UA — Socrata accepts default Python UA but a meaningful
# identifier helps if CFTC ever audits traffic.
_HEADERS = {
    "User-Agent": "IchorCollector/1.0 (research; contact via repo)",
    "Accept": "application/json",
}


@dataclass(frozen=True)
class CftcTffObservation:
    """One TFF row : 1 market × 1 weekly report = 1 row."""

    report_date: date
    """Tuesday-close report date (publication is Friday after)."""

    market_code: str
    """CFTC contract_market_code (numeric or alphanumeric)."""

    market_name: str
    """Full market_and_exchange_names string (≤ 200 chars)."""

    commodity_name: str
    """Commodity grouping (e.g. CURRENCY, INDEX, INTEREST RATE)."""

    open_interest: int
    """Total open interest in contracts."""

    # 5 trader classes × {long, short} = 10 numeric fields.
    dealer_long: int
    dealer_short: int
    asset_mgr_long: int
    asset_mgr_short: int
    lev_money_long: int
    lev_money_short: int
    other_rept_long: int
    other_rept_short: int
    nonrept_long: int
    nonrept_short: int

    fetched_at: datetime


def _to_int(value: Any) -> int:
    """Socrata returns numerics as strings — coerce safely. Empty/None/
    '.' (CFTC missing-data sentinel) → 0."""
    if value is None or value == "" or value == ".":
        return 0
    try:
        # Some fields use thousand-separator commas, others don't.
        return int(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0


def parse_socrata_response(payload: list[dict]) -> list[CftcTffObservation]:
    """Pure parser — extract TFF rows from Socrata JSON list.

    Returns [] on any structural mismatch. Never raises.

    Each row is a flat dict with ~73 fields; we keep the 16 we care
    about and drop the rest. The report_date_as_yyyy_mm_dd field is
    an ISO datetime (e.g. '2026-04-28T00:00:00.000') — we parse to
    date.
    """
    if not isinstance(payload, list):
        log.warning("cftc_tff.parse_payload_not_list", type=type(payload).__name__)
        return []

    fetched = datetime.now(UTC)
    out: list[CftcTffObservation] = []

    for row in payload:
        try:
            iso = row.get("report_date_as_yyyy_mm_dd")
            if not iso:
                continue
            try:
                report_date = datetime.fromisoformat(iso.replace("Z", "+00:00")).date()
            except (TypeError, ValueError):
                # Try naive ISO date (e.g. "2026-04-28")
                try:
                    report_date = date.fromisoformat(iso[:10])
                except (TypeError, ValueError):
                    continue

            obs = CftcTffObservation(
                report_date=report_date,
                market_code=str(row.get("cftc_contract_market_code") or "")[:16],
                market_name=str(row.get("market_and_exchange_names") or "")[:200],
                commodity_name=str(row.get("commodity_name") or "")[:64],
                open_interest=_to_int(row.get("open_interest_all")),
                # CFTC inconsistency: Dealer + Nonrept + TotRept use the "_all"
                # suffix; AssetMgr + LevMoney + OtherRept do NOT. This is a
                # historical artifact of the COT/TFF schema lineage. Verified
                # live 2026-05-08 against publicreporting.cftc.gov resource
                # gpe5-46if (TFF Futures-Only).
                dealer_long=_to_int(row.get("dealer_positions_long_all")),
                dealer_short=_to_int(row.get("dealer_positions_short_all")),
                asset_mgr_long=_to_int(row.get("asset_mgr_positions_long")),
                asset_mgr_short=_to_int(row.get("asset_mgr_positions_short")),
                lev_money_long=_to_int(row.get("lev_money_positions_long")),
                lev_money_short=_to_int(row.get("lev_money_positions_short")),
                other_rept_long=_to_int(row.get("other_rept_positions_long")),
                other_rept_short=_to_int(row.get("other_rept_positions_short")),
                nonrept_long=_to_int(row.get("nonrept_positions_long_all")),
                nonrept_short=_to_int(row.get("nonrept_positions_short_all")),
                fetched_at=fetched,
            )
            out.append(obs)
        except (KeyError, TypeError, ValueError) as e:
            log.warning("cftc_tff.row_skip", error=str(e), row_id=row.get("id"))
            continue

    return out


async def fetch_recent(
    *,
    weeks_lookback: int = 8,
    market_codes: Iterable[str] = TRACKED_MARKET_CODES,
    client: httpx.AsyncClient | None = None,
) -> list[CftcTffObservation]:
    """Fetch the last `weeks_lookback` weeks of TFF for tracked markets.

    Returns [] on any HTTP error. Best-effort.

    Filters server-side via Socrata `$where` to limit the payload to
    relevant markets + recent reports. Socrata supports SoQL-like
    filtering; we use the canonical `IN (...)` clause + date threshold.
    """
    # Threshold = today - weeks*7 days (a bit of slack for late releases)
    cutoff = (datetime.now(UTC).date() - __import__("datetime").timedelta(weeks=weeks_lookback)).isoformat()
    quoted = ", ".join(f"'{c}'" for c in market_codes)
    where = (
        f"cftc_contract_market_code IN ({quoted}) "
        f"AND report_date_as_yyyy_mm_dd >= '{cutoff}T00:00:00.000'"
    )
    params = {
        "$where": where,
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "$limit": 5000,
    }

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=20.0, headers=_HEADERS)
    try:
        try:
            r = await client.get(CFTC_TFF_SODA_URL, params=params)
            r.raise_for_status()
            return parse_socrata_response(r.json())
        except (httpx.HTTPError, ValueError) as e:
            log.warning("cftc_tff.fetch_failed", error=str(e))
            return []
    finally:
        if own_client:
            await client.aclose()


async def poll_all(
    weeks_lookback: int = 8,
) -> list[CftcTffObservation]:
    """Standard collector entry — TFF weekly for the tracked markets."""
    return await fetch_recent(weeks_lookback=weeks_lookback)


__all__ = [
    "CFTC_TFF_SODA_URL",
    "MARKET_TO_ASSET",
    "TRACKED_MARKET_CODES",
    "CftcTffObservation",
    "fetch_recent",
    "parse_socrata_response",
    "poll_all",
]


if __name__ == "__main__":  # pragma: no cover
    rows = asyncio.run(poll_all())
    print(f"fetched {len(rows)} rows ({len(set(r.market_code for r in rows))} markets)")
    by_date: dict[date, int] = {}
    for r in rows:
        by_date[r.report_date] = by_date.get(r.report_date, 0) + 1
    for d in sorted(by_date.keys(), reverse=True)[:5]:
        print(f"  {d}: {by_date[d]} markets")
    if rows:
        latest = max(rows, key=lambda r: (r.report_date, r.market_code))
        print(
            f"\nLatest sample: {latest.market_name[:60]}\n"
            f"  date={latest.report_date}  OI={latest.open_interest:,}\n"
            f"  Dealer: long={latest.dealer_long:,} short={latest.dealer_short:,}\n"
            f"  AssetMgr: long={latest.asset_mgr_long:,} short={latest.asset_mgr_short:,}\n"
            f"  LevFunds: long={latest.lev_money_long:,} short={latest.lev_money_short:,}"
        )
