"""AAII Sentiment Survey weekly collector.

The American Association of Individual Investors (AAII) publishes a
weekly bullish / neutral / bearish split that's a well-documented
contrarian indicator: extreme bullish > 50% historically precedes weak
forward returns; extreme bearish < 20% precedes strong ones.

Source: https://www.aaii.com/sentimentsurvey
Format: public CSV at https://www.aaii.com/files/surveys/sentiment.xls
        (the .xls is actually a CSV under content sniffing — verify on
        first --persist run; the path may be sentiment.csv on the
        modernized site).

Free, no API key. Polled once per week (Thursday 11:00 ET, the standard
release window).
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

AAII_CSV_URL = "https://www.aaii.com/files/surveys/sentiment.xls"


@dataclass(frozen=True)
class AaiiWeeklyReading:
    """One AAII weekly sentiment row."""

    week_ending: datetime
    bullish_pct: float  # in [0, 1]
    neutral_pct: float
    bearish_pct: float
    spread: float  # bullish - bearish, in [-1, 1]


def _parse_pct(s: str) -> float | None:
    """AAII rows can have '34.2%', '34.20%', or blank. Returns 0..1 or None."""
    s = (s or "").strip()
    if not s:
        return None
    s = s.rstrip("%").strip()
    try:
        v = float(s)
    except ValueError:
        return None
    # If looks like 0..1 already (rare but defensive), keep; else divide by 100.
    return v / 100.0 if v > 1.0 else v


def _parse_date(s: str) -> datetime | None:
    """AAII rows use M/D/YYYY or YYYY-MM-DD."""
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def parse_aaii_csv(text: str) -> list[AaiiWeeklyReading]:
    """Parse AAII CSV body. Tolerant of header row variations."""
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return []

    # Find the header row (contains "Bullish" or "bullish").
    header_idx = -1
    for i, row in enumerate(rows[:10]):
        joined = " ".join(c.lower() for c in row)
        if "bullish" in joined and "bearish" in joined:
            header_idx = i
            break
    if header_idx < 0:
        return []
    header = [h.strip().lower() for h in rows[header_idx]]

    def _col(name_substr: str) -> int:
        for i, h in enumerate(header):
            if name_substr in h:
                return i
        return -1

    date_col = _col("date") if _col("date") >= 0 else _col("week")
    bull_col = _col("bullish")
    neut_col = _col("neutral")
    bear_col = _col("bearish")
    if min(date_col, bull_col, neut_col, bear_col) < 0:
        return []

    out: list[AaiiWeeklyReading] = []
    for row in rows[header_idx + 1 :]:
        if len(row) <= max(date_col, bull_col, neut_col, bear_col):
            continue
        d = _parse_date(row[date_col])
        bull = _parse_pct(row[bull_col])
        neut = _parse_pct(row[neut_col])
        bear = _parse_pct(row[bear_col])
        if d is None or bull is None or neut is None or bear is None:
            continue
        out.append(
            AaiiWeeklyReading(
                week_ending=d,
                bullish_pct=bull,
                neutral_pct=neut,
                bearish_pct=bear,
                spread=bull - bear,
            )
        )
    return out


async def fetch_latest_aaii(*, weeks: int = 12, timeout_s: float = 30.0) -> list[AaiiWeeklyReading]:
    """Fetch the AAII history and return the most recent N weeks."""
    headers = {
        "User-Agent": "IchorAaiiCollector/0.1 (https://github.com/fxeliott/ichor)",
        "Accept": "text/csv,application/vnd.ms-excel,*/*",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
            r = await client.get(AAII_CSV_URL, headers=headers)
            r.raise_for_status()
            body = r.text
    except httpx.HTTPError:
        return []
    parsed = parse_aaii_csv(body)
    parsed.sort(key=lambda x: x.week_ending, reverse=True)
    return parsed[:weeks]


def is_extreme(spread: float, *, abs_threshold: float = 0.4) -> bool:
    """AAII contrarian extreme: |bullish - bearish| > 0.4 historically rare."""
    return abs(spread) > abs_threshold
