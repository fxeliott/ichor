"""Cleveland Fed Inflation Nowcast collector.

The Cleveland Fed publishes a daily nowcast of CPI / Core CPI / PCE /
Core PCE inflation across three horizons (MoM annualised, QoQ SAAR,
YoY). Updated ~10:00 ET every business day. Trustworthy short-horizon
inflation forecast that prefigures the official BLS CPI release on
the 2nd-3rd Wednesday of the month.

Why this matters for Ichor :
- The nowcast is published days BEFORE the BLS CPI/PCE prints. A
  large gap between the nowcast for month M and consensus prefigures
  a CPI surprise — a primary driver of UST + DXY repricing.
- Cross-validates the NY Fed MCT trend (W71) with a higher-frequency,
  point-in-time nowcast. Nowcast above MCT = "trend should drift up";
  below MCT = "trend should drift down".
- 4 measures × 3 horizons = 12 series, all in one daily run.

Free path verified Voie D-compliant (ADR-009): direct webcharts JSON
endpoints, no API key. URLs discovered via HTML data-data-config attr
inspection on 2026-05-09 (W72 audit).

License : public domain (Federal Reserve Bank of Cleveland publication).
DOI: 10.26509/frbc-infexp.

The webcharts JSON is a list of FusionCharts config snapshots, one per
revision date. Each snapshot has a `chart.subcaption` (target period
e.g. "2026-5" or "2026:Q2") and a `dataset` array of {seriesname, data}
entries. We take the latest snapshot, extract the last non-empty data
point per measure, and persist 12 rows per run.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx
import structlog

log = structlog.get_logger(__name__)

# Endpoints. The `?sc_lang=en` query string is required by the CMS routing.
_BASE = "https://www.clevelandfed.org/-/media/files/webcharts/inflationnowcasting"
NOWCAST_QUARTER_URL = f"{_BASE}/nowcast_quarter.json?sc_lang=en"
NOWCAST_MONTH_URL = f"{_BASE}/nowcast_month.json?sc_lang=en"
NOWCAST_YEAR_URL = f"{_BASE}/nowcast_year.json?sc_lang=en"

# Map between FusionCharts seriesname and Ichor canonical measure code.
_SERIES_TO_MEASURE: dict[str, str] = {
    "CPI Inflation": "CPI",
    "Core CPI Inflation": "CoreCPI",
    "PCE Inflation": "PCE",
    "Core PCE Inflation": "CorePCE",
}
# "Actual <measure>" series in month/year files are realised values, not
# nowcasts — we ignore them (they're sourced from BLS/BEA already in FRED).
_ACTUAL_PREFIX = "Actual "

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; IchorCollector/1.0; +https://github.com/fxeliott/ichor)"
    ),
    "Accept": "application/json,*/*",
}


@dataclass(frozen=True)
class ClevelandFedNowcastObservation:
    """One Cleveland Fed nowcast observation."""

    measure: str  # CPI / CoreCPI / PCE / CorePCE
    horizon: str  # mom / qoq / yoy
    target_period: date  # first day of the target month/quarter
    revision_date: date  # date the nowcast was last revised
    nowcast_value: float  # percent
    fetched_at: datetime


def _parse_quarter_subcaption(s: str) -> date | None:
    """Parse 'YYYY:QN' → first day of quarter. Returns None on mismatch."""
    m = re.fullmatch(r"\s*(\d{4}):Q([1-4])\s*", s or "")
    if not m:
        return None
    year = int(m.group(1))
    quarter = int(m.group(2))
    month = (quarter - 1) * 3 + 1
    try:
        return date(year, month, 1)
    except ValueError:
        return None


def _parse_month_subcaption(s: str) -> date | None:
    """Parse 'YYYY-M' → first day of month. Returns None on mismatch."""
    m = re.fullmatch(r"\s*(\d{4})-(\d{1,2})\s*", s or "")
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), 1)
    except ValueError:
        return None


def _parse_revision_date(s: str | None) -> date | None:
    """Parse 'YYYY-MM-DD HH:MM' (or just 'YYYY-MM-DD') → date."""
    if not s:
        return None
    m = re.match(r"\s*(\d{4})-(\d{2})-(\d{2})", s)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _parse_float(s: str | float | int | None) -> float | None:
    """Tolerant float parser. Returns None on '', None, non-numeric."""
    if s is None or s == "":
        return None
    if isinstance(s, (int, float)):
        return float(s)
    try:
        return float(str(s).strip())
    except ValueError:
        return None


def _last_non_empty_value(data_pts: list[dict]) -> float | None:
    """Walk a FusionCharts data array right-to-left and return the first
    non-empty parsed numeric value. None if all entries are empty."""
    for pt in reversed(data_pts):
        v = _parse_float(pt.get("value"))
        if v is not None:
            return v
    return None


def parse_nowcast_payload(payload: list, horizon: str) -> list[ClevelandFedNowcastObservation]:
    """Pure parser. Extracts the latest snapshot from a webcharts list and
    emits one observation per measure (4 measures = up to 4 obs per call).

    Returns [] on any structural mismatch. Never raises.
    """
    if not isinstance(payload, list) or not payload:
        return []
    snapshot = payload[-1]
    if not isinstance(snapshot, dict):
        return []
    chart = snapshot.get("chart") or {}
    subcaption = chart.get("subcaption", "")
    target = (
        _parse_quarter_subcaption(subcaption)
        if horizon == "qoq"
        else _parse_month_subcaption(subcaption)
    )
    if target is None:
        log.warning(
            "cleveland_fed_nowcast.target_unparseable",
            horizon=horizon,
            subcaption=subcaption,
        )
        return []
    revision = _parse_revision_date(chart.get("_comment"))
    if revision is None:
        # Fallback: use today's date (still records the snapshot).
        revision = datetime.now(UTC).date()

    fetched = datetime.now(UTC)
    out: list[ClevelandFedNowcastObservation] = []
    for series in snapshot.get("dataset") or []:
        seriesname = series.get("seriesname", "")
        if seriesname.startswith(_ACTUAL_PREFIX):
            continue
        measure = _SERIES_TO_MEASURE.get(seriesname)
        if measure is None:
            continue
        last_value = _last_non_empty_value(series.get("data") or [])
        if last_value is None:
            continue
        out.append(
            ClevelandFedNowcastObservation(
                measure=measure,
                horizon=horizon,
                target_period=target,
                revision_date=revision,
                nowcast_value=last_value,
                fetched_at=fetched,
            )
        )
    return out


async def fetch_horizon(
    url: str,
    horizon: str,
    *,
    client: httpx.AsyncClient | None = None,
    timeout: float = 30.0,
) -> list[ClevelandFedNowcastObservation]:
    """Fetch one horizon's webcharts JSON. Returns [] on HTTP error."""
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=timeout, headers=_HEADERS)
    try:
        try:
            r = await client.get(url, timeout=timeout)
            r.raise_for_status()
            text = r.content.decode("utf-8-sig", errors="replace")
            payload = json.loads(text)
            return parse_nowcast_payload(payload, horizon)
        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as e:
            log.warning(
                "cleveland_fed_nowcast.fetch_failed",
                horizon=horizon,
                error=str(e),
            )
            return []
    finally:
        if own_client:
            await client.aclose()


async def poll_all() -> list[ClevelandFedNowcastObservation]:
    """Standard collector entry point. Fetches all 3 horizons in parallel."""
    async with httpx.AsyncClient(timeout=30.0, headers=_HEADERS) as client:
        results = await asyncio.gather(
            fetch_horizon(NOWCAST_QUARTER_URL, "qoq", client=client),
            fetch_horizon(NOWCAST_MONTH_URL, "mom", client=client),
            fetch_horizon(NOWCAST_YEAR_URL, "yoy", client=client),
            return_exceptions=False,
        )
    out: list[ClevelandFedNowcastObservation] = []
    for r in results:
        out.extend(r)
    return out


__all__ = [
    "NOWCAST_MONTH_URL",
    "NOWCAST_QUARTER_URL",
    "NOWCAST_YEAR_URL",
    "ClevelandFedNowcastObservation",
    "fetch_horizon",
    "parse_nowcast_payload",
    "poll_all",
]


if __name__ == "__main__":  # pragma: no cover
    rows = asyncio.run(poll_all())
    print(f"fetched {len(rows)} nowcast rows")
    for r in sorted(rows, key=lambda x: (x.horizon, x.measure)):
        print(
            f"  {r.horizon}  {r.measure:8s}  target={r.target_period}  "
            f"rev={r.revision_date}  value={r.nowcast_value:.3f}%"
        )
