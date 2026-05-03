"""AI-GPR Index daily collector — LLM-scored geopolitical risk.

Caldara & Iacoviello (Federal Reserve Board) maintain two indices :

  - **GPR** (classic) : monthly, since 1985, based on newspaper text searches
  - **AI-GPR** (NEW since 2024) : **daily**, since 1960, LLM-scored from
    expanded text corpus + LLM classification

The AI-GPR index is more reactive — it can spike in days vs months for
GPR. Useful for our session cards because geopolitical premium can drive
intraday gold + USD haven moves.

Data is published as CSV / Excel at :
  https://www.matteoiacoviello.com/ai_gpr.html

This collector downloads the latest CSV, returns the time series. Cached
heavily because the file is updated at most once per day.

License : academic, free for non-commercial use. Commercial inquiries
to the authors.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime, timezone

import httpx
import structlog

log = structlog.get_logger(__name__)

AI_GPR_CSV_URL = "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls"
AI_GPR_HOMEPAGE = "https://www.matteoiacoviello.com/ai_gpr.html"


@dataclass(frozen=True)
class AiGprObservation:
    """One daily AI-GPR reading."""

    observation_date: date
    """Calendar day of the reading."""

    ai_gpr: float
    """AI-GPR Index value. Higher = more geopolitical risk."""

    fetched_at: datetime


def _parse_csv(body: bytes) -> list[AiGprObservation]:
    """The recent CSV ships with header `date,GPR_DAILY,...`. We only need
    `date` + `GPR_DAILY` (or `AI_GPR` depending on file version).
    """
    text = body.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    fields = set(reader.fieldnames or [])

    # Accept either historical naming (`GPR_DAILY`) or the newer `AI_GPR`.
    value_col = (
        "AI_GPR" if "AI_GPR" in fields
        else "GPR_DAILY" if "GPR_DAILY" in fields
        else None
    )
    date_col = (
        "date" if "date" in fields
        else "DATE" if "DATE" in fields
        else None
    )
    if value_col is None or date_col is None:
        log.warning("ai_gpr.unexpected_header", header=reader.fieldnames)
        return []

    fetched = datetime.now(timezone.utc)
    out: list[AiGprObservation] = []
    for row in reader:
        try:
            d = row[date_col].strip()
            v = row[value_col].strip()
            if not d or not v or v.lower() in {"na", "nan", "."}:
                continue
            # Try ISO first, then US date
            try:
                bar_date = date.fromisoformat(d)
            except ValueError:
                bar_date = datetime.strptime(d, "%m/%d/%Y").date()
            out.append(
                AiGprObservation(
                    observation_date=bar_date,
                    ai_gpr=float(v),
                    fetched_at=fetched,
                )
            )
        except (KeyError, ValueError) as e:
            log.warning("ai_gpr.parse_row_failed", error=str(e))
            continue
    return out


async def fetch_latest(*, timeout: float = 30.0) -> list[AiGprObservation]:
    """Download the latest AI-GPR CSV and return the parsed series.

    The site occasionally renames the file ; we try the canonical URL
    first and fall back to a homepage scrape if needed.
    """
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(
                AI_GPR_CSV_URL,
                timeout=timeout,
                follow_redirects=True,
                headers={"User-Agent": "IchorAIGPRCollector/0.1"},
            )
            r.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("ai_gpr.fetch_failed", url=AI_GPR_CSV_URL, error=str(e))
            return []

    rows = _parse_csv(r.content)
    if not rows:
        log.warning("ai_gpr.empty_or_unparseable")
    rows.sort(key=lambda x: x.observation_date)
    return rows


def latest_n_days(rows: list[AiGprObservation], n: int = 30) -> list[AiGprObservation]:
    return rows[-n:] if len(rows) > n else rows


def delta_30d(rows: list[AiGprObservation]) -> float | None:
    """Z-score-style delta : current - mean(last 30) / std(last 30)."""
    import statistics
    if len(rows) < 30:
        return None
    window = [r.ai_gpr for r in rows[-30:]]
    current = window[-1]
    mean = sum(window) / len(window)
    try:
        std = statistics.stdev(window)
    except statistics.StatisticsError:
        return None
    return (current - mean) / std if std > 0 else 0.0
