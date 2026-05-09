"""NFIB Small Business Economic Trends (SBET) monthly collector.

The NFIB SBET report aggregates a 1986=100 composite index of US small
business sentiment (Optimism Index) plus a separate Uncertainty Index.
Released ~2nd Tuesday of each month, ~06:00 ET, covering the prior
month's survey.

Why this matters for Ichor :
- SBOI is a leading indicator of US small-business hiring + capex
  intentions. SBOI < 95 + Uncertainty > 95 = recession-precursor
  signature seen in 2007, 2019.
- Tracks the "Inflation as #1 problem" frequency — leading indicator
  of consumer-price stickiness (cf. NY Fed MCT trend in W71).

Free path verified Voie D-compliant (ADR-009): public PDF, no API
key. URL discovered by scraping the NFIB SBET hub page (W74 audit).

License : NFIB report. Derive metrics + attribute "Source: NFIB
Small Business Economic Trends". Do not rehost the PDF itself.

Strategy :
  1. Fetch the SBET hub page (HTML).
  2. Regex out the first PDF URL matching `*NFIB-SBET-Report*.pdf`.
  3. Parse the survey month from the URL filename.
  4. Download the PDF, extract page 3 text via pdfplumber.
  5. Regex SBOI + Uncertainty Index headline values.
  6. Persist (report_month, sboi, uncertainty_index, source_pdf_url).

Idempotent dedup on report_month: re-runs after the same publication
are no-ops. Daily polling between 11:00 and 15:00 UTC on the 2nd
Tuesday is the canonical timer; off-Tuesdays are no-op fast.
"""

from __future__ import annotations

import asyncio
import io
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx
import structlog

log = structlog.get_logger(__name__)

HUB_URL = "https://www.nfib.com/news/monthly_report/sbet/"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; IchorCollector/1.0; +https://github.com/fxeliott/ichor)"
    ),
    "Accept": "text/html,application/pdf,*/*",
}

# Regex to find the current SBET PDF URL on the hub page.
_PDF_HREF_RE = re.compile(
    r'href=["\'](https?://[^"\']*?(?:NFIB-)?SBET[^"\']*?\.pdf)["\']',
    re.IGNORECASE,
)

# Regex to parse survey month from filename like
# "NFIB-SBET-Report-March-2026.pdf" or "NFIB-SBET-Report-Feb.-2026.pdf".
_FILENAME_MONTH_RE = re.compile(
    r"NFIB-?SBET[^/]*?(January|February|Feb\.?|March|Mar\.?|April|Apr\.?|"
    r"May|June|Jun\.?|July|Jul\.?|August|Aug\.?|September|Sept?\.?|"
    r"October|Oct\.?|November|Nov\.?|December|Dec\.?)[^\d]*?(\d{4})",
    re.IGNORECASE,
)

# Regex to extract SBOI from page 3 headline:
# "The Small Business Optimism Index for March was 95.8, ..."
_SBOI_RE = re.compile(
    r"Optimism\s+Index\s+for\s+[A-Z][a-z]+\s+(?:was|fell\s+to|"
    r"rose\s+to|increased\s+to)\s+(\d{2,3}\.\d)",
    re.IGNORECASE,
)

# Regex to extract Uncertainty Index. Handles patterns like:
#   "The Uncertainty Index rose 4 points from February to 92, ..."
#   "Uncertainty Index fell to 88 ..."
# We allow up to 100 chars of any-non-newline between "Uncertainty Index"
# and the "to <value>" anchor (the integer-points clause varies).
_UNCERTAINTY_RE = re.compile(
    r"Uncertainty\s+Index[^\n]{0,100}?\bto\s+(\d{2,3})\b",
    re.IGNORECASE,
)

# Map written month names + abbreviations to month integer.
_MONTHS: dict[str, int] = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sept": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}


@dataclass(frozen=True)
class NfibSbetObservation:
    """One monthly NFIB SBET observation."""

    report_month: date
    sboi: float
    uncertainty_index: float | None
    source_pdf_url: str
    fetched_at: datetime


def _parse_month_token(tok: str) -> int | None:
    return _MONTHS.get(tok.strip(".").lower())


def _parse_filename_month(url: str) -> date | None:
    """Parse the survey month from the NFIB PDF URL filename."""
    m = _FILENAME_MONTH_RE.search(url)
    if not m:
        return None
    month = _parse_month_token(m.group(1))
    if not month:
        return None
    try:
        year = int(m.group(2))
    except ValueError:
        return None
    try:
        return date(year, month, 1)
    except ValueError:
        return None


def parse_sbet_pdf_text(text: str) -> tuple[float | None, float | None]:
    """Pure parser. Returns (sboi, uncertainty_index) from raw page-3 text.

    Either may be None on regex miss. Never raises.
    """
    sboi: float | None = None
    unc: float | None = None
    m = _SBOI_RE.search(text)
    if m:
        try:
            sboi = float(m.group(1))
        except ValueError:
            pass
    m2 = _UNCERTAINTY_RE.search(text)
    if m2:
        try:
            unc = float(m2.group(1))
        except ValueError:
            pass
    return sboi, unc


async def fetch_pdf_url(client: httpx.AsyncClient) -> str | None:
    """Scrape the SBET hub page for the current PDF URL."""
    try:
        r = await client.get(HUB_URL, timeout=30.0)
        r.raise_for_status()
    except httpx.HTTPError as e:
        log.warning("nfib_sbet.hub_fetch_failed", error=str(e))
        return None
    matches = _PDF_HREF_RE.findall(r.text)
    if not matches:
        log.warning("nfib_sbet.no_pdf_link_on_hub")
        return None
    # First match is the most recent published.
    return matches[0]


async def fetch_and_parse_pdf(
    pdf_url: str, client: httpx.AsyncClient
) -> NfibSbetObservation | None:
    """Download the PDF + extract SBOI + Uncertainty Index."""
    # Late import — pdfplumber is a heavy dep, only loaded when needed.
    try:
        import pdfplumber
    except ImportError:
        log.error("nfib_sbet.pdfplumber_not_installed")
        return None

    try:
        r = await client.get(pdf_url, timeout=60.0)
        r.raise_for_status()
    except httpx.HTTPError as e:
        log.warning("nfib_sbet.pdf_fetch_failed", error=str(e), url=pdf_url)
        return None

    report_month = _parse_filename_month(pdf_url)
    if report_month is None:
        log.warning("nfib_sbet.report_month_unparseable", url=pdf_url)
        return None

    # Scan first 5 pages for the headline (page 3 is canonical but be
    # defensive against layout shifts).
    sboi: float | None = None
    unc: float | None = None
    try:
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            for page in pdf.pages[:5]:
                text = page.extract_text() or ""
                if not text:
                    continue
                page_sboi, page_unc = parse_sbet_pdf_text(text)
                if page_sboi is not None and sboi is None:
                    sboi = page_sboi
                if page_unc is not None and unc is None:
                    unc = page_unc
                if sboi is not None and unc is not None:
                    break
    except (OSError, ValueError) as e:
        log.warning("nfib_sbet.pdf_parse_failed", error=str(e))
        return None

    if sboi is None:
        log.warning("nfib_sbet.sboi_not_found", url=pdf_url)
        return None

    return NfibSbetObservation(
        report_month=report_month,
        sboi=sboi,
        uncertainty_index=unc,
        source_pdf_url=pdf_url,
        fetched_at=datetime.now(UTC),
    )


async def poll_all() -> list[NfibSbetObservation]:
    """Standard collector entry point."""
    async with httpx.AsyncClient(timeout=60.0, headers=_HEADERS) as client:
        pdf_url = await fetch_pdf_url(client)
        if pdf_url is None:
            return []
        obs = await fetch_and_parse_pdf(pdf_url, client)
        return [obs] if obs is not None else []


__all__ = [
    "HUB_URL",
    "NfibSbetObservation",
    "fetch_and_parse_pdf",
    "fetch_pdf_url",
    "parse_sbet_pdf_text",
    "poll_all",
]


if __name__ == "__main__":  # pragma: no cover
    rows = asyncio.run(poll_all())
    print(f"fetched {len(rows)} NFIB SBET rows")
    for r in rows:
        print(
            f"  {r.report_month}  SBOI={r.sboi}  "
            f"Uncertainty={r.uncertainty_index}  "
            f"src={r.source_pdf_url}"
        )
