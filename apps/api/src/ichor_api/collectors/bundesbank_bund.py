"""Bundesbank Bund 10Y daily yield collector (ADR-090 P0 step-1).

Replaces the monthly `FRED:IRLTLT01DEM156N` (30-day staleness in
intraday Pass-2) with the daily Bundesbank SDMX series :

    https://api.statistiken.bundesbank.de/rest/data/BBSIS/
        D.I.ZAR.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A
        ?format=csvdata

Source : Bundesbank Statistical Time Series database, public + free,
no API key required. Researcher blueprint (round 28) empirically
validated 2026-05-13 = 3.13% PROZENT (% direct, NOT basis points).

Two-format parser :
* **Primary** : SDMX-CSV (`?format=csvdata`) — columns include
  `TIME_PERIOD` (YYYY-MM-DD) + `OBS_VALUE` (yield in %).
* **Fallback** : SDMX-ML XML (when the server ignores `?format=` and
  returns XML anyway). Walks `<generic:Obs>` elements pulling
  `<generic:ObsDimension value="..."/>` (date) and
  `<generic:ObsValue value="..."/>` (yield).

ADR-009 Voie D compliant : Bundesbank is a public sovereign source,
no metered API, zero Anthropic SDK touched.

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

BUND_10Y_URL = (
    "https://api.statistiken.bundesbank.de/rest/data/BBSIS/"
    "D.I.ZAR.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A"
    "?format=csvdata"
)

# SDMX-ML namespaces (used by the XML fallback parser).
_NS_GENERIC = "{http://www.sdmx.org/resources/sdmxml/schemas/v2_1/data/generic}"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; IchorCollector/1.0; +https://github.com/fxeliott/ichor)",
    "Accept": "application/vnd.sdmx.data+csv,application/xml,*/*",
}

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class BundYieldObservation:
    """One parsed daily Bund 10Y yield observation.

    `yield_pct` is PROZENT (% direct, NOT basis points). Bundesbank
    flow `BBSIS` exposes the unit attribute `BBK_UNIT=PROZENT`.
    """

    observation_date: date
    yield_pct: float
    source_url: str
    fetched_at: datetime


def parse_bund_csv(text: str, *, source_url: str = BUND_10Y_URL) -> list[BundYieldObservation]:
    """Parse SDMX-CSV response. Returns [] when shape unexpected.

    SDMX-CSV columns vary slightly by server version but always
    include `TIME_PERIOD` and `OBS_VALUE`. Empty `OBS_VALUE` cells
    (non-trading days) are skipped. Malformed rows are skipped (NOT
    raised) so a single corrupt cell doesn't break the whole import.
    """
    fetched = datetime.now(UTC)
    out: list[BundYieldObservation] = []
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        date_str = (row.get("TIME_PERIOD") or "").strip()
        value_str = (row.get("OBS_VALUE") or "").strip()
        if not _ISO_DATE_RE.match(date_str) or not value_str:
            continue
        try:
            out.append(
                BundYieldObservation(
                    observation_date=date.fromisoformat(date_str),
                    yield_pct=float(value_str),
                    source_url=source_url,
                    fetched_at=fetched,
                )
            )
        except (ValueError, TypeError):
            # Malformed value (non-numeric, out-of-range date) — skip.
            continue
    return out


def parse_bund_xml(text: str, *, source_url: str = BUND_10Y_URL) -> list[BundYieldObservation]:
    """Parse SDMX-ML XML fallback (when server ignores ?format=csvdata).

    Walks `<generic:Obs>` elements. Each one contains :
    * `<generic:ObsDimension value="2026-05-13"/>` (TIME_PERIOD)
    * `<generic:ObsValue value="3.13"/>` (OBS_VALUE)

    Returns [] on parse error or empty document. Same skip-malformed
    discipline as the CSV parser.
    """
    fetched = datetime.now(UTC)
    out: list[BundYieldObservation] = []
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        log.warning("bundesbank_bund.xml_parse_failed", error=str(exc))
        return out

    # SDMX-ML is hierarchical : <DataSet><Series><Obs>...</Obs></Series></DataSet>.
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
                BundYieldObservation(
                    observation_date=date.fromisoformat(date_str),
                    yield_pct=float(value_str),
                    source_url=source_url,
                    fetched_at=fetched,
                )
            )
        except (ValueError, TypeError):
            continue
    return out


def parse_bund_response(
    body: str | bytes, *, content_type: str = "", source_url: str = BUND_10Y_URL
) -> list[BundYieldObservation]:
    """Auto-detect CSV vs XML and dispatch to the right parser.

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
        return parse_bund_csv(body, source_url=source_url)
    if "xml" in ct or body.startswith("<"):
        return parse_bund_xml(body, source_url=source_url)
    # Default — try CSV first, fall back to XML if zero rows parsed.
    csv_out = parse_bund_csv(body, source_url=source_url)
    if csv_out:
        return csv_out
    return parse_bund_xml(body, source_url=source_url)


async def fetch_bund_yields(
    *,
    client: httpx.AsyncClient | None = None,
    timeout: float = 30.0,
) -> list[BundYieldObservation]:
    """Fetch and parse the full Bund 10Y daily series from Bundesbank.

    Bundesbank rate limits are not publicly documented but the daily
    cron fires once per day — well within reasonable budgets. Returns
    [] on any HTTP error (caller decides retry policy ; for now the
    daily cron will simply skip the day and try again tomorrow).
    """
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=timeout, headers=_HEADERS)
    try:
        try:
            r = await client.get(BUND_10Y_URL, timeout=timeout)
            r.raise_for_status()
            content_type = r.headers.get("content-type", "")
            return parse_bund_response(
                r.content, content_type=content_type, source_url=BUND_10Y_URL
            )
        except httpx.HTTPError as e:
            log.warning("bundesbank_bund.fetch_failed", error=str(e), error_type=type(e).__name__)
            return []
    finally:
        if own_client and client is not None:
            await client.aclose()


__all__ = [
    "BUND_10Y_URL",
    "BundYieldObservation",
    "fetch_bund_yields",
    "parse_bund_csv",
    "parse_bund_response",
    "parse_bund_xml",
]
