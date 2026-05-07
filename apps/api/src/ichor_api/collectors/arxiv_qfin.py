"""arXiv q-fin papers collector.

Why this exists for Ichor :
  - q-fin papers (quantitative finance, statistical finance, risk
    management, trading) are a leading-indicator stream of academic
    research that often anticipates regime shifts in the official
    stats. A spike on a topic = the market is paying attention.
  - We poll the arXiv Atom feed on q-fin categories daily.

Endpoint (verified 2026-05-05, free no-auth) :
  http://export.arxiv.org/api/query?search_query=cat:q-fin.ST+OR+cat:q-fin.RM
    &start=0&max_results=50&sortBy=submittedDate&sortOrder=descending

Returns Atom XML. We parse the entries and persist title + url +
published date as news_items (source_kind='academic').

Source :
  - https://info.arxiv.org/help/api/index.html
  - https://arxiv.org/category_taxonomy (q-fin.* categories)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import defusedxml.ElementTree as ET  # noqa: N817 — alias kept for stdlib parity
import httpx

ARXIV_BASE = "http://export.arxiv.org/api/query"

# q-fin sub-categories. Full list :
#   q-fin.CP (Computational Finance)
#   q-fin.EC (Economics)
#   q-fin.GN (General Finance)
#   q-fin.MF (Mathematical Finance)
#   q-fin.PM (Portfolio Management)
#   q-fin.PR (Pricing of Securities)
#   q-fin.RM (Risk Management)
#   q-fin.ST (Statistical Finance)
#   q-fin.TR (Trading and Market Microstructure)
WATCHED_CATEGORIES: tuple[str, ...] = (
    "q-fin.ST",  # Statistical Finance
    "q-fin.RM",  # Risk Management
    "q-fin.TR",  # Trading & Microstructure
    "q-fin.PM",  # Portfolio Management
)

# Atom XML namespaces — arXiv API uses standard Atom + OpenSearch.
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}


@dataclass(frozen=True)
class ArxivPaper:
    """One q-fin paper entry."""

    arxiv_id: str
    title: str
    summary: str
    primary_category: str
    published_at: datetime
    updated_at: datetime
    authors: tuple[str, ...]
    pdf_url: str
    abs_url: str
    fetched_at: datetime


def _strip_xml_text(s: str | None) -> str:
    """Atom feeds ship multi-line whitespace ; collapse it."""
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip()


def _parse_iso_z(s: str | None) -> datetime:
    if not s:
        return datetime.now(UTC)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return datetime.now(UTC)


def parse_arxiv_response(xml_text: str) -> list[ArxivPaper]:
    """Parse the Atom XML. Returns 0 papers on malformed input."""
    out: list[ArxivPaper] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return out
    now = datetime.now(UTC)
    for entry in root.findall("atom:entry", _NS):
        # ID is the abs URL ; arxiv_id is the trailing path
        id_el = entry.find("atom:id", _NS)
        abs_url = (id_el.text or "").strip() if id_el is not None else ""
        # Extract arxiv_id from URL : http://arxiv.org/abs/2603.12345v1
        m = re.search(r"/abs/([^/]+)$", abs_url)
        arxiv_id = m.group(1) if m else abs_url

        title_el = entry.find("atom:title", _NS)
        summary_el = entry.find("atom:summary", _NS)
        title = _strip_xml_text(title_el.text if title_el is not None else "")
        summary = _strip_xml_text(summary_el.text if summary_el is not None else "")
        if not title:
            continue

        published_el = entry.find("atom:published", _NS)
        updated_el = entry.find("atom:updated", _NS)
        published = _parse_iso_z(published_el.text if published_el is not None else None)
        updated = _parse_iso_z(updated_el.text if updated_el is not None else None)

        # Primary category is in <arxiv:primary_category term="..."/>
        # arXiv ext namespace — fallback to first <category>
        prim_cat = ""
        for cat_el in entry.findall("atom:category", _NS):
            term = cat_el.attrib.get("term", "")
            if term.startswith("q-fin"):
                prim_cat = term
                break
        if not prim_cat:
            cat_el = entry.find("atom:category", _NS)
            if cat_el is not None:
                prim_cat = cat_el.attrib.get("term", "")

        authors = tuple(
            _strip_xml_text(a.find("atom:name", _NS).text)
            for a in entry.findall("atom:author", _NS)
            if a.find("atom:name", _NS) is not None
        )[:8]

        pdf_url = abs_url.replace("/abs/", "/pdf/") if abs_url else ""

        out.append(
            ArxivPaper(
                arxiv_id=arxiv_id,
                title=title,
                summary=summary,
                primary_category=prim_cat or "q-fin",
                published_at=published,
                updated_at=updated,
                authors=authors,
                pdf_url=pdf_url,
                abs_url=abs_url,
                fetched_at=now,
            )
        )
    return out


async def fetch_qfin_recent(
    *,
    categories: tuple[str, ...] = WATCHED_CATEGORIES,
    max_results: int = 50,
    timeout_s: float = 30.0,
) -> list[ArxivPaper]:
    """Latest papers across the q-fin categories, sorted by submission date."""
    query = "+OR+".join(f"cat:{c}" for c in categories)
    params: dict[str, Any] = {
        "search_query": query,
        "start": "0",
        "max_results": str(max_results),
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    headers = {
        "User-Agent": "IchorArxivCollector/0.1 (https://github.com/fxeliott/ichor)",
        "Accept": "application/atom+xml",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.get(ARXIV_BASE, params=params, headers=headers)
            r.raise_for_status()
            return parse_arxiv_response(r.text)
    except httpx.HTTPError:
        return []


def supported_categories() -> tuple[str, ...]:
    return WATCHED_CATEGORIES
