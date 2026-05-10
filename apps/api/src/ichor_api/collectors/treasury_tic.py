"""Treasury TIC Major Foreign Holders monthly collector.

The Treasury International Capital (TIC) system reports monthly holdings
of US Treasury securities by foreign country. Source-of-truth for
foreign demand dynamics — critical for USD reserve currency intelligence
and early detection of foreign repatriation episodes that telegraph
yield curve / FX repricing.

Why TIC matters for Ichor :
- Foreign holdings of Treasuries (~30 % of marketable debt) are the
  marginal price-setter on long-end yield + DXY direction.
- Country-level breakdown (Japan / China / UK / Cayman / etc.) tells us
  WHO is selling/buying — Japan's pace post-BoJ tightening differs
  fundamentally from China's geopolitical-driven trim.
- Monthly cadence with ~6-week lag : data for month M-1 published
  ~3rd week of M+1 (TIC release calendar 2026: Jan 15 / Feb 18 / Mar 18 /
  Apr 15 / May 18 / Jun 18 / Jul 14 / Aug 17).

Free path verified Voie D-compliant (ADR-009): Treasury.gov direct, no
API key, no paid tier. Hetzner curl test 2026-05-08 confirmed
mfhhis01.txt is the current historical file with latest Dec 2025 data.

License : public domain (US Treasury).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx
import structlog

log = structlog.get_logger(__name__)

# Canonical historical MFH file. tab-separated. ~100 KB.
MFH_HISTORY_URL = "https://ticdata.treasury.gov/Publish/mfhhis01.txt"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; IchorCollector/1.0; +https://github.com/fxeliott/ichor)"
    ),
    "Accept": "text/plain,*/*",
}

# Month name → numeric for the column header parsing.
_MONTH_TO_INT: dict[str, int] = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}

# Footer markers — lines that signal end-of-table; data rows above them.
_FOOTER_MARKERS: tuple[str, ...] = (
    "Department of the Treasury",
    "Source:",
    "Notes:",
    "Of which:",
    "1/",
    "2/",
)


@dataclass(frozen=True)
class TreasuryTicHolding:
    """One country × month holdings record (in billions USD)."""

    country: str
    """Canonical country label as printed in the TIC table (e.g. 'Japan',
    'China, Mainland', 'United Kingdom', 'Cayman Islands', 'Grand Total')."""

    observation_month: date
    """First-of-month date for the reporting period (e.g. Dec 2025 stored
    as date(2025, 12, 1))."""

    holdings_bn_usd: float
    """End-of-period holdings in billions of USD."""

    fetched_at: datetime


def _parse_header_periods(lines: list[str]) -> list[date] | None:
    """Find the (months row, years row) pair and return list[date] of
    period starts (one per data column).

    The TIC file lines look like:
        \\tDec\\tNov\\tOct\\tSep\\tAug\\tJul\\tJun\\tMay\\tApr\\tMar\\tFeb\\tJan\\t
        Country\\t2025\\t2025\\t2025\\t2025\\t2025\\t2025\\t2025\\t2025\\t2025\\t2025\\t2025\\t2025\\t

    The first column of the YEARS row is "Country" — that's our anchor.
    """
    for i, line in enumerate(lines[:30]):
        cells = [c.strip() for c in line.split("\t")]
        if not cells or cells[0] != "Country":
            continue
        years = cells[1:]
        # The previous non-empty line should hold the months.
        for j in range(i - 1, -1, -1):
            prev_cells = [c.strip() for c in lines[j].split("\t")]
            if any(c in _MONTH_TO_INT for c in prev_cells):
                months = [c for c in prev_cells if c]  # drop empty leading cell
                # Align by truncating to common length.
                n = min(len(months), len(years))
                periods: list[date] = []
                for m, y in zip(months[:n], years[:n], strict=False):
                    if m not in _MONTH_TO_INT:
                        continue
                    try:
                        year_int = int(y)
                    except ValueError:
                        continue
                    periods.append(date(year_int, _MONTH_TO_INT[m], 1))
                return periods or None
        return None
    return None


def _parse_data_row(line: str, periods: list[date], fetched: datetime) -> list[TreasuryTicHolding]:
    """Parse one TAB-separated country row into multiple holdings records."""
    cells = [c.strip() for c in line.split("\t")]
    if len(cells) < 2:
        return []
    country = cells[0]
    if not country or country.startswith("-"):
        return []
    out: list[TreasuryTicHolding] = []
    for i, period in enumerate(periods):
        if i + 1 >= len(cells):
            break
        raw = cells[i + 1].replace(",", "").strip()
        if not raw or raw == "-":
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        out.append(
            TreasuryTicHolding(
                country=country,
                observation_month=period,
                holdings_bn_usd=value,
                fetched_at=fetched,
            )
        )
    return out


def parse_mfh_history(text: str) -> list[TreasuryTicHolding]:
    """Pure parser — extract all (country, month) holdings from the TIC
    mfhhis01.txt body.

    Returns [] on any structural mismatch. Never raises.
    """
    lines = text.splitlines()
    periods = _parse_header_periods(lines)
    if not periods:
        log.warning("treasury_tic.header_unrecognized")
        return []
    fetched = datetime.now(UTC)
    out: list[TreasuryTicHolding] = []
    in_data = False
    for line in lines:
        # Detect data zone start: row containing "Country" anchor passed.
        if line.lstrip().startswith("Country"):
            in_data = True
            continue
        if not in_data:
            continue
        # Footer detection
        stripped = line.strip()
        if any(stripped.startswith(m) for m in _FOOTER_MARKERS):
            break
        if not stripped or stripped.startswith("-"):
            continue
        out.extend(_parse_data_row(line, periods, fetched))
    return out


async def fetch_mfh_history(
    *,
    client: httpx.AsyncClient | None = None,
    timeout: float = 30.0,
) -> list[TreasuryTicHolding]:
    """Fetch the TIC MFH history file. Returns [] on any HTTP error."""
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=timeout, headers=_HEADERS)
    try:
        try:
            r = await client.get(MFH_HISTORY_URL, timeout=timeout)
            r.raise_for_status()
            return parse_mfh_history(r.text)
        except httpx.HTTPError as e:
            log.warning("treasury_tic.fetch_failed", error=str(e))
            return []
    finally:
        if own_client:
            await client.aclose()


async def poll_all() -> list[TreasuryTicHolding]:
    """Standard collector entry point. Fetches the entire MFH history."""
    return await fetch_mfh_history()


__all__ = [
    "MFH_HISTORY_URL",
    "TreasuryTicHolding",
    "fetch_mfh_history",
    "parse_mfh_history",
    "poll_all",
]


if __name__ == "__main__":  # pragma: no cover
    rows = asyncio.run(poll_all())
    print(f"fetched {len(rows)} holdings rows")
    if rows:
        latest = max(r.observation_month for r in rows)
        recent = [r for r in rows if r.observation_month == latest]
        print(f"latest period: {latest}")
        for r in sorted(recent, key=lambda x: -x.holdings_bn_usd)[:10]:
            print(f"  {r.country:30s}  {r.holdings_bn_usd:>8.1f}  bn USD")
