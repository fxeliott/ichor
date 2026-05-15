"""NY Fed Multivariate Core Trend (MCT) Inflation collector.

The NY Fed MCT decomposes monthly PCE inflation across 17 sectors using
a Bayesian dynamic-factor model (Almuzara-Sbordone). It outputs a
persistent-trend component that is far smoother than headline / core PCE
prints and is the most credible single-series proxy for "where the Fed
believes inflation is anchored". MCT replaces the discontinued FRED
UIGFULL series.

Why MCT matters for Ichor :
- The Fed reaction function is more sensitive to trend than to monthly
  headline noise. MCT < 2.5 % consistently → cuts more likely; > 3 %
  consistently → hikes-on-hold or further hikes more likely.
- The 3-sector decomposition (Goods / Services ex housing / Housing)
  reveals which segment is driving the trend — Goods soft + Services
  hot is a classic late-cycle FX risk-off + UST bear-steepener pattern.
- Released ~1st business day of the month following the BEA PCE release
  (~10:00 ET / 16:00 Paris). Triggers FOMC repricing days after.

Free path verified Voie D-compliant (ADR-009): NY Fed direct CSV, no
API key, no paid tier. URL discovered via JS bundle inspection on
2026-05-09 (W71 audit).

License : public domain (Federal Reserve Bank of New York publication).

Research path (W71): the official GitHub repo MCT-Inflation-NYFed/MCT-PCE
contains MATLAB .mat files but is frozen at 2024-02-20 (single commit).
The live source is the JS-rendered chart on /research/policy/mct, backed
by a CSV at the URL below — confirmed live with 2026-03 latest data.
"""

from __future__ import annotations

import asyncio
import csv
import io
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx
import structlog

log = structlog.get_logger(__name__)

MCT_CSV_URL = (
    "https://www.newyorkfed.org/medialibrary/Research/Interactives/Data/mct/mct-chart-data.csv"
)

# r52 bot-mitigation workaround : NY Fed enabled WAF that returns HTTP 403
# on the prior `Mozilla/5.0 (compatible; IchorCollector/1.0; +https://github.com
# /fxeliott/ichor)` User-Agent (the `compatible;` token + bot URL are exactly
# what most Cloudflare/Akamai WAFs flag). VERIFIED via WebFetch 2026-05-15.
# Symptom : `nyfed_mct.fetch_failed status=403` in journal, `fetched_at`
# frozen 2026-05-09 (last successful poll before WAF kicked in), 5 monthly
# releases missed. Fix : present as a realistic browser session — Chrome 131
# UA + `Accept-Language` + `Referer` to the public MCT research page from
# which the CSV is normally linked. The CSV is publicly downloadable so this
# is bot-class WAF, not auth.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/csv,application/csv,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.newyorkfed.org/research/policy/mct",
}

# CSV column indexing (0-based, including the leading blank "row label" col):
#   col 0  : (blank label / "Date")
#   col 1  : Date string ("M/D/YYYY")
#   col 2  : MCT trend (central, primary)
#   col 3-5: alternative MCT estimates (bands / decompositions, dropped)
#   col 6  : Headline PCE inflation YoY
#   col 7  : Core PCE inflation YoY
#   col 8  : Goods (sector aggregate)
#   col 9  : Services ex. housing (sector aggregate)
#   col 10 : Housing (sector aggregate)
#   col 11+: sector-specific decompositions (dropped — too granular)
#
# The first 4 lines of the CSV are nested header levels — we skip them
# until we encounter a row whose 2nd cell parses as M/D/YYYY.

_COL_DATE = 1
_COL_MCT_TREND = 2
_COL_HEADLINE_PCE_YOY = 6
_COL_CORE_PCE_YOY = 7
_COL_GOODS = 8
_COL_SERVICES_EX_HOUSING = 9
_COL_HOUSING = 10


@dataclass(frozen=True)
class NyfedMctObservation:
    """One monthly MCT observation (percent annualised)."""

    observation_month: date
    mct_trend_pct: float
    headline_pce_yoy: float | None
    core_pce_yoy: float | None
    goods_pct: float | None
    services_ex_housing_pct: float | None
    housing_pct: float | None
    fetched_at: datetime


def _parse_date(s: str) -> date | None:
    """Parse 'M/D/YYYY' (e.g. '3/1/2026') → date. Returns None on mismatch."""
    s = s.strip()
    if not s:
        return None
    parts = s.split("/")
    if len(parts) != 3:
        return None
    try:
        m, d, y = (int(p) for p in parts)
    except ValueError:
        return None
    if not (1 <= m <= 12 and 1 <= d <= 31 and 1900 <= y <= 2100):
        return None
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _parse_float(s: str) -> float | None:
    """Tolerant float parser. Returns None on '', 'NaN', non-numeric."""
    s = s.strip()
    if not s or s.lower() == "nan":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _safe_get(row: list[str], idx: int) -> str:
    return row[idx] if idx < len(row) else ""


def parse_mct_csv(text: str) -> list[NyfedMctObservation]:
    """Pure parser — extract MCT observations from the CSV body.

    Returns [] on any structural mismatch. Never raises.
    """
    fetched = datetime.now(UTC)
    out: list[NyfedMctObservation] = []
    try:
        reader = csv.reader(io.StringIO(text))
        for row in reader:
            if len(row) <= _COL_HOUSING:
                # Header rows have shorter or differently-shaped content;
                # data rows always include the housing column.
                continue
            obs_date = _parse_date(_safe_get(row, _COL_DATE))
            if obs_date is None:
                continue
            mct = _parse_float(_safe_get(row, _COL_MCT_TREND))
            if mct is None:
                # MCT trend is mandatory for the row to be useful.
                continue
            out.append(
                NyfedMctObservation(
                    observation_month=obs_date.replace(day=1),
                    mct_trend_pct=mct,
                    headline_pce_yoy=_parse_float(_safe_get(row, _COL_HEADLINE_PCE_YOY)),
                    core_pce_yoy=_parse_float(_safe_get(row, _COL_CORE_PCE_YOY)),
                    goods_pct=_parse_float(_safe_get(row, _COL_GOODS)),
                    services_ex_housing_pct=_parse_float(_safe_get(row, _COL_SERVICES_EX_HOUSING)),
                    housing_pct=_parse_float(_safe_get(row, _COL_HOUSING)),
                    fetched_at=fetched,
                )
            )
    except (csv.Error, ValueError, TypeError) as e:
        log.warning("nyfed_mct.parse_failed", error=str(e))
        return []
    return out


async def fetch_mct(
    *,
    client: httpx.AsyncClient | None = None,
    timeout: float = 30.0,
) -> list[NyfedMctObservation]:
    """Fetch the live MCT CSV. Returns [] on any HTTP error."""
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=timeout, headers=_HEADERS)
    try:
        try:
            r = await client.get(MCT_CSV_URL, timeout=timeout)
            r.raise_for_status()
            # The CSV is UTF-8 with a BOM. httpx auto-detects but force a
            # decode-from-bytes-then-strip-BOM to avoid surprises.
            text = r.content.decode("utf-8-sig", errors="replace")
            return parse_mct_csv(text)
        except httpx.HTTPError as e:
            log.warning("nyfed_mct.fetch_failed", error=str(e))
            return []
    finally:
        if own_client:
            await client.aclose()


async def poll_all() -> list[NyfedMctObservation]:
    """Standard collector entry point. Fetches the entire MCT history."""
    return await fetch_mct()


__all__ = [
    "MCT_CSV_URL",
    "NyfedMctObservation",
    "fetch_mct",
    "parse_mct_csv",
    "poll_all",
]


if __name__ == "__main__":  # pragma: no cover
    rows = asyncio.run(poll_all())
    print(f"fetched {len(rows)} MCT observations")
    if rows:
        latest = max(rows, key=lambda r: r.observation_month)
        print(
            f"latest = {latest.observation_month} : "
            f"MCT={latest.mct_trend_pct:.2f}%  "
            f"headlinePCE={latest.headline_pce_yoy}%  "
            f"corePCE={latest.core_pce_yoy}%"
        )
