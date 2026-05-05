"""BoE IADB (Interactive Database) collector — UK rate + GBP-relevant series.

The BoE IADB exposes CSV downloads via a stable URL pattern:
  https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp
  ?Datefrom=DD/MMM/YYYY&Dateto=DD/MMM/YYYY&SeriesCodes={A;B;C}
  &CSVF=TN&UsingCodes=Y&Filter=N

Free, no API key. Series codes Ichor needs:
  - IUDBEDR    Bank Rate (BoE policy rate)
  - IUMASOIA   SONIA reference rate
  - IUDSV03    Sterling 3-month gilt yield
  - IUDLNPY    M4 broad money YoY
  - IUDPSPB    Public sector net borrowing
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import httpx

BOE_BASE = "https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp"

SERIES_TO_POLL: tuple[str, ...] = (
    "IUDBEDR",
    "IUMASOIA",
    "IUDSV03",
    "IUDLNPY",
    "IUDPSPB",
)


@dataclass(frozen=True)
class BoeObservation:
    series_code: str
    observation_date: date
    value: float | None
    fetched_at: datetime


def _parse_date(s: str) -> date | None:
    s = (s or "").strip()
    if not s:
        return None
    # BoE often uses "DD MMM YYYY" or "DD/MMM/YYYY"
    for fmt in ("%d %b %Y", "%d/%b/%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _safe_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_iadb_csv(text: str) -> list[BoeObservation]:
    """Parse the BoE IADB CSV.

    Format: first column = DATE, subsequent columns = series codes.
    """
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if len(rows) < 2:
        return []
    header = [c.strip().upper() for c in rows[0]]
    fetched = datetime.now(UTC)
    out: list[BoeObservation] = []
    # Identify series columns (every column except the first which is the date).
    series_cols = [(idx, code) for idx, code in enumerate(header) if idx > 0 and code]
    for r in rows[1:]:
        if not r:
            continue
        d = _parse_date(r[0]) if r else None
        if d is None:
            continue
        for idx, code in series_cols:
            if idx >= len(r):
                continue
            v = _safe_float(r[idx])
            out.append(
                BoeObservation(
                    series_code=code,
                    observation_date=d,
                    value=v,
                    fetched_at=fetched,
                )
            )
    return out


async def fetch_series(
    series_codes: tuple[str, ...] = SERIES_TO_POLL,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    timeout_s: float = 30.0,
) -> list[BoeObservation]:
    """Download IADB CSV for the given codes + date range."""
    today = date.today()
    if date_to is None:
        date_to = today
    if date_from is None:
        date_from = date(today.year - 1, today.month, today.day)
    params = {
        "Datefrom": date_from.strftime("%d/%b/%Y"),
        "Dateto": date_to.strftime("%d/%b/%Y"),
        "SeriesCodes": ";".join(series_codes),
        "CSVF": "TN",
        "UsingCodes": "Y",
        "Filter": "N",
    }
    headers = {"Accept": "text/csv,*/*", "User-Agent": "IchorBoeCollector/0.1"}
    try:
        async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
            r = await client.get(BOE_BASE, params=params, headers=headers)
            r.raise_for_status()
            return parse_iadb_csv(r.text)
    except httpx.HTTPError:
        return []
