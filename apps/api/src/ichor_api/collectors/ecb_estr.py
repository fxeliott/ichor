"""ECB €STR (Euro Short-Term Rate) daily collector (ADR-090 P0 step-4).

Fetches the daily volume-weighted trimmed mean rate from the ECB Data
Portal SDMX flow :

    https://data-api.ecb.europa.eu/service/data/EST/
        B.EU000A2X2A25.WT
        ?startPeriod=YYYY-MM-DD

Source : ECB Data Portal — public, free, no auth required. Round-33
subagent #2 empirically validated 2026-05-12 = 1.929% (volume-weighted
trimmed mean rate, unit PC = percent direct).

Key differences from `collectors/bundesbank_bund.py` (round-32c
lessons) :

  - **Delimiter = COMMA** for SDMX-CSV ECB Data Portal v1.0.0. NOT
    semicolon like Bundesbank. Per-provider variant, MUST be set
    per-collector.
  - **No `?format=` query parameter rejected** — ECB respects content
    negotiation via the Accept header cleanly. The `?startPeriod=`
    parameter IS respected and is the canonical way to do incremental
    ingestion (saves bandwidth on daily crons).
  - Same dual CSV+XML auto-detect parser pattern (defense-in-depth
    against ECB serving XML if Accept is mis-set).

ADR-009 Voie D compliant : ECB Data Portal is a public sovereign
source, no metered API, zero Anthropic SDK touched.

ADR-017 boundary intact : pure numeric data fetch, no LLM call, no
directional output.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from xml.etree import ElementTree as ET

import httpx
import structlog

log = structlog.get_logger(__name__)

# Default URL fetches the full €STR history since inception 2019-10-01.
# Callers can pass an explicit start_period kwarg for incremental
# ingestion (saves ~1700 rows of bandwidth per daily cron fire).
ECB_ESTR_URL_BASE = "https://data-api.ecb.europa.eu/service/data/EST/B.EU000A2X2A25.WT"

# SDMX-ML namespace (used by the XML fallback parser).
_NS_GENERIC = "{http://www.sdmx.org/resources/sdmxml/schemas/v2_1/data/generic}"

# Accept header per ECB API docs : the canonical 2026 way to request
# SDMX-CSV 1.0.0 (the format with COMMA delimiter). Listing CSV first
# + XML fallback + */* tail gives the parser auto-detect a clean shot
# whatever ECB chooses to serve.
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; IchorCollector/1.0; +https://github.com/fxeliott/ichor)",
    "Accept": "application/vnd.sdmx.data+csv;version=1.0.0,application/xml,*/*",
}

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class EstrObservation:
    """One parsed daily €STR rate observation.

    `rate_pct` is PROZENT (% direct, NOT basis points). ECB Data
    Portal exposes the unit attribute `UNIT_MEASURE=PC` (percent).
    """

    observation_date: date
    rate_pct: float
    source_url: str
    fetched_at: datetime


def parse_estr_csv(text: str, *, source_url: str = ECB_ESTR_URL_BASE) -> list[EstrObservation]:
    """Parse SDMX-CSV ECB Data Portal response. Returns [] when shape
    unexpected.

    SDMX-CSV 1.0.0 from ECB uses COMMA delimiter (NOT semicolon like
    Bundesbank — per-provider variant). The canonical columns are
    `TIME_PERIOD` (YYYY-MM-DD) and `OBS_VALUE` (rate in percent).
    Empty `OBS_VALUE` cells (non-trading days) are skipped. Malformed
    rows are skipped (NOT raised) so a single corrupt cell doesn't
    break the whole import.
    """
    fetched = datetime.now(UTC)
    out: list[EstrObservation] = []
    # Strip UTF-8 BOM if present — csv.DictReader otherwise reads the
    # first column header as `﻿TIME_PERIOD` and row.get returns
    # None. Defense-in-depth even though parse_estr_response also
    # decodes via utf-8-sig.
    text = text.lstrip("﻿")
    # COMMA delimiter for ECB Data Portal SDMX-CSV 1.0.0.
    reader = csv.DictReader(io.StringIO(text), delimiter=",")
    for row in reader:
        date_str = (row.get("TIME_PERIOD") or "").strip()
        value_str = (row.get("OBS_VALUE") or "").strip()
        if not _ISO_DATE_RE.match(date_str) or not value_str:
            continue
        try:
            out.append(
                EstrObservation(
                    observation_date=date.fromisoformat(date_str),
                    rate_pct=float(value_str),
                    source_url=source_url,
                    fetched_at=fetched,
                )
            )
        except (ValueError, TypeError):
            continue
    return out


def parse_estr_xml(text: str, *, source_url: str = ECB_ESTR_URL_BASE) -> list[EstrObservation]:
    """Parse SDMX-ML XML fallback (defense-in-depth — kicks in if ECB
    serves XML despite our Accept header).

    Walks `<generic:Obs>` elements. Each one contains :
      * `<generic:ObsDimension value="2026-05-12"/>` (TIME_PERIOD)
      * `<generic:ObsValue value="1.929"/>` (OBS_VALUE)
    """
    fetched = datetime.now(UTC)
    out: list[EstrObservation] = []
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        log.warning("ecb_estr.xml_parse_failed", error=str(exc))
        return out

    for obs in root.iter(f"{_NS_GENERIC}Obs"):
        dim = obs.find(f"{_NS_GENERIC}ObsDimension")
        val = obs.find(f"{_NS_GENERIC}ObsValue")
        if dim is None or val is None:
            continue
        date_str = (dim.get("value") or "").strip()
        value_str = (val.get("value") or "").strip()
        if not _ISO_DATE_RE.match(date_str) or not value_str:
            continue
        try:
            out.append(
                EstrObservation(
                    observation_date=date.fromisoformat(date_str),
                    rate_pct=float(value_str),
                    source_url=source_url,
                    fetched_at=fetched,
                )
            )
        except (ValueError, TypeError):
            continue
    return out


def parse_estr_response(
    body: str | bytes,
    *,
    content_type: str = "",
    source_url: str = ECB_ESTR_URL_BASE,
) -> list[EstrObservation]:
    """Auto-detect CSV vs XML and dispatch.

    Detection priority :
      1. `content_type` header explicitly says CSV or XML.
      2. Body starts with `<?xml` or `<` → XML.
      3. Default → CSV.
    """
    if isinstance(body, bytes):
        body = body.decode("utf-8-sig", errors="replace")
    body = body.lstrip()

    ct = content_type.lower()
    if "csv" in ct:
        return parse_estr_csv(body, source_url=source_url)
    if "xml" in ct or body.startswith("<"):
        return parse_estr_xml(body, source_url=source_url)
    csv_out = parse_estr_csv(body, source_url=source_url)
    if csv_out:
        return csv_out
    return parse_estr_xml(body, source_url=source_url)


async def fetch_estr_rates(
    *,
    client: httpx.AsyncClient | None = None,
    timeout: float = 30.0,
    start_period: date | None = None,
) -> list[EstrObservation]:
    """Fetch and parse the €STR daily series from ECB Data Portal.

    `start_period` (optional) enables incremental ingestion — pass
    the most recent ingested date to fetch only newer rows. If None,
    fetches the full history since €STR inception (~1700 rows over
    2019-2026).

    ECB Data Portal rate limits aren't publicly documented but the
    daily cron fires once per day — well within reasonable budgets.
    Returns [] on any HTTP error (caller decides retry policy).
    """
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=timeout, headers=_HEADERS)
    url = ECB_ESTR_URL_BASE
    if start_period is not None:
        url = f"{ECB_ESTR_URL_BASE}?startPeriod={start_period:%Y-%m-%d}"
    try:
        try:
            r = await client.get(url, timeout=timeout)
            r.raise_for_status()
            content_type = r.headers.get("content-type", "")
            return parse_estr_response(r.content, content_type=content_type, source_url=url)
        except httpx.HTTPError as e:
            log.warning("ecb_estr.fetch_failed", error=str(e), error_type=type(e).__name__)
            return []
    finally:
        if own_client and client is not None:
            await client.aclose()


__all__ = [
    "ECB_ESTR_URL_BASE",
    "EstrObservation",
    "fetch_estr_rates",
    "parse_estr_csv",
    "parse_estr_response",
    "parse_estr_xml",
]
