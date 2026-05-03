"""RSS collector — pulls headlines from public, no-API-key feeds.

Strategy: poll a set of finance-relevant RSS/Atom feeds, dedupe by GUID,
score each item with FinBERT-tone (Phase 1+ link), and stream into the
`news_items` Redis Stream where downstream agents (briefing context
assembler, AlertEngine NEWS_REGIME_SHIFT trigger) consume them.

Free + ToS-friendly feeds only:
  - Reuters business/markets       (https://www.reuters.com/arc/outboundfeeds/...)
  - BBC business/markets           (http://feeds.bbci.co.uk/news/business/rss.xml)
  - Federal Reserve press releases (https://www.federalreserve.gov/feeds/press_all.xml)
  - ECB press releases             (https://www.ecb.europa.eu/rss/press.html)
  - Bank of England news           (https://www.bankofengland.co.uk/rss/news)
  - Treasury Direct                (https://home.treasury.gov/rss/press)
  - SEC press releases             (https://www.sec.gov/news/pressreleases.rss)

Feed list is configurable so we can add/remove without code changes.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable
from xml.etree import ElementTree as ET

import httpx
import structlog

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class FeedSource:
    name: str
    url: str
    kind: str  # "central_bank" | "news" | "regulator"


DEFAULT_FEEDS: tuple[FeedSource, ...] = (
    FeedSource(
        "fed_press_all",
        "https://www.federalreserve.gov/feeds/press_all.xml",
        "central_bank",
    ),
    FeedSource(
        "ecb_press",
        "https://www.ecb.europa.eu/rss/press.html",
        "central_bank",
    ),
    FeedSource(
        "boe_news",
        "https://www.bankofengland.co.uk/rss/news",
        "central_bank",
    ),
    # Treasury press historically had an XML feed at
    # /system/files/126/treasury-news.xml but it now serves an HTML
    # placeholder. Re-add when treasury.gov publishes a real feed URL.
    FeedSource(
        "sec_press",
        "https://www.sec.gov/news/pressreleases.rss",
        "regulator",
    ),
    FeedSource(
        "bbc_business",
        "http://feeds.bbci.co.uk/news/business/rss.xml",
        "news",
    ),
)


@dataclass
class NewsItem:
    """Normalized news item, dedup-stable via `guid_hash`."""

    source: str
    source_kind: str
    title: str
    summary: str
    url: str
    published_at: datetime
    fetched_at: datetime
    guid_hash: str
    raw_categories: list[str] = field(default_factory=list)


_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "dc": "http://purl.org/dc/elements/1.1/",
}

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str | None) -> str:
    if not text:
        return ""
    return _TAG_RE.sub("", text).strip()


def _full_text(elem: ET.Element | None) -> str:
    """Return the concatenated text of an element + all its descendants.

    Necessary because RSS feeds inline HTML (`<b>`, `<a>`, etc.) inside
    <description>; ElementTree splits those into child nodes, so .text only
    returns content up to the first child. itertext() walks the subtree.
    """
    if elem is None:
        return ""
    return _TAG_RE.sub("", "".join(elem.itertext())).strip()


def _parse_date(raw: str | None) -> datetime:
    """Parse RFC-822 (RSS) and ISO-8601 (Atom). Fallback to now on failure."""
    if not raw:
        return datetime.now(timezone.utc)
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        pass
    try:
        # Atom-style ISO 8601
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


def _hash(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8", errors="ignore"))
        h.update(b"|")
    return h.hexdigest()[:32]


def parse_feed(source: FeedSource, body: bytes) -> list[NewsItem]:
    """Parse RSS 2.0 OR Atom; return normalized items.

    Resilient to malformed feeds: on XML errors returns []. Logs the issue.
    """
    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        log.warning("rss.parse_failed", source=source.name, error=str(e))
        return []

    items: list[NewsItem] = []
    fetched = datetime.now(timezone.utc)

    # RSS 2.0 — <channel><item>
    for item in root.iterfind(".//item"):
        title = _strip_html(item.findtext("title"))
        link = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or link or title).strip()
        summary = _full_text(item.find("description"))
        pub = _parse_date(item.findtext("pubDate") or item.findtext("dc:date", namespaces=_NS))
        cats = [c.text or "" for c in item.iterfind("category") if c.text]
        if not title or not link:
            continue
        items.append(
            NewsItem(
                source=source.name,
                source_kind=source.kind,
                title=title,
                summary=summary,
                url=link,
                published_at=pub,
                fetched_at=fetched,
                guid_hash=_hash(source.name, guid),
                raw_categories=cats,
            )
        )

    # Atom — <feed><entry>
    for entry in root.iterfind("atom:entry", _NS):
        title = _strip_html(entry.findtext("atom:title", namespaces=_NS))
        link_el = entry.find("atom:link[@rel='alternate']", _NS)
        if link_el is None:
            link_el = entry.find("atom:link", _NS)
        link = (link_el.get("href") or "").strip() if link_el is not None else ""
        guid = (entry.findtext("atom:id", namespaces=_NS) or link or title).strip()
        summary_el = entry.find("atom:summary", _NS)
        if summary_el is None:
            summary_el = entry.find("atom:content", _NS)
        summary = _full_text(summary_el)
        pub = _parse_date(
            entry.findtext("atom:published", namespaces=_NS)
            or entry.findtext("atom:updated", namespaces=_NS)
        )
        cats = [c.get("term", "") for c in entry.iterfind("atom:category", _NS)]
        if not title or not link:
            continue
        items.append(
            NewsItem(
                source=source.name,
                source_kind=source.kind,
                title=title,
                summary=summary,
                url=link,
                published_at=pub,
                fetched_at=fetched,
                guid_hash=_hash(source.name, guid),
                raw_categories=cats,
            )
        )

    return items


async def fetch_feed(
    source: FeedSource,
    *,
    client: httpx.AsyncClient,
    timeout: float = 20.0,
    user_agent: str = "IchorRSSCollector/0.1 (+https://fxmilyapp.com)",
) -> list[NewsItem]:
    """Fetch + parse a single feed. Returns [] on failure (logs the cause)."""
    try:
        r = await client.get(
            source.url,
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": user_agent,
                "Accept": (
                    "application/rss+xml, application/atom+xml, "
                    "application/xml;q=0.8, */*;q=0.5"
                ),
            },
        )
        r.raise_for_status()
    except httpx.HTTPError as e:
        log.warning("rss.fetch_failed", source=source.name, error=str(e))
        return []
    return parse_feed(source, r.content)


async def poll_all(
    feeds: Iterable[FeedSource] = DEFAULT_FEEDS,
    *,
    concurrency: int = 4,
) -> list[NewsItem]:
    """Poll every feed in parallel, dedupe by guid_hash, return newest-first."""
    sem = asyncio.Semaphore(concurrency)

    async def _one(src: FeedSource, client: httpx.AsyncClient) -> list[NewsItem]:
        async with sem:
            return await fetch_feed(src, client=client)

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*(_one(s, client) for s in feeds))

    seen: set[str] = set()
    flat: list[NewsItem] = []
    for batch in results:
        for item in batch:
            if item.guid_hash in seen:
                continue
            seen.add(item.guid_hash)
            flat.append(item)

    flat.sort(key=lambda it: it.published_at, reverse=True)
    return flat
