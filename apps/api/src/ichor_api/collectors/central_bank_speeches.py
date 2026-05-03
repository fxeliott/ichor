"""Central bank speeches aggregator — RSS feeds from BIS + individual CBs.

The Bank for International Settlements (BIS) publishes a public RSS feed
that aggregates speeches from ALL central banks worldwide :

  https://www.bis.org/doclist/cbspeeches.rss

Plus we collect direct from the most market-moving CBs : Fed (FOMC + voting
members), ECB (Lagarde + Council), BoE (Bailey + MPC), BoJ (Ueda).

Output : `CentralBankSpeech` records, persisted to the news table with
`source_kind='central_bank'` and a `cb_speaker` enrichment.

This complements the existing `rss.py` collector which already pulls some
of these feeds. Here we focus on speeches specifically (not press releases),
because speeches reveal forward-guidance shifts that drive yields.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable
from xml.etree import ElementTree as ET

from defusedxml.ElementTree import fromstring as defused_fromstring
import httpx
import structlog

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class CentralBankSpeechFeed:
    name: str
    url: str
    central_bank: str  # canonical : Fed, ECB, BoE, BoJ, BIS, etc.


DEFAULT_CB_FEEDS: tuple[CentralBankSpeechFeed, ...] = (
    CentralBankSpeechFeed(
        "bis_speeches_aggregator",
        "https://www.bis.org/doclist/cbspeeches.rss",
        "BIS",
    ),
    CentralBankSpeechFeed(
        "fed_press_speeches",
        "https://www.federalreserve.gov/feeds/speeches.xml",
        "Fed",
    ),
    CentralBankSpeechFeed(
        "ecb_press_releases",
        "https://www.ecb.europa.eu/rss/press.html",
        "ECB",
    ),
    CentralBankSpeechFeed(
        "boe_news",
        "https://www.bankofengland.co.uk/rss/news",
        "BoE",
    ),
    CentralBankSpeechFeed(
        "boj_whatsnew",
        "https://www.boj.or.jp/en/rss/whatsnew.xml",
        "BoJ",
    ),
)


@dataclass
class CentralBankSpeech:
    central_bank: str
    speaker: str | None
    title: str
    summary: str
    url: str
    published_at: datetime
    fetched_at: datetime
    source_feed: str


def _parse_date(raw: str | None) -> datetime:
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
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


def _strip_html(text: str | None) -> str:
    if not text:
        return ""
    import re
    return re.sub(r"<[^>]+>", "", text).strip()


# Heuristics : extract speaker name from BIS title format "Speaker: Title"
def _extract_speaker(title: str) -> str | None:
    if ":" in title:
        candidate = title.split(":", 1)[0].strip()
        # Sanity : speaker name is < 60 chars, contains letters
        if 3 < len(candidate) < 60 and any(c.isalpha() for c in candidate):
            return candidate
    return None


def parse_feed(feed: CentralBankSpeechFeed, body: bytes) -> list[CentralBankSpeech]:
    try:
        root = defused_fromstring(body)
    except ET.ParseError as e:
        log.warning("cb_speeches.parse_failed", source=feed.name, error=str(e))
        return []

    fetched = datetime.now(timezone.utc)
    out: list[CentralBankSpeech] = []

    # RSS 2.0 — <channel><item>
    for item in root.iterfind(".//item"):
        title = _strip_html(item.findtext("title"))
        link = (item.findtext("link") or "").strip()
        summary = _strip_html(item.findtext("description"))
        pub = _parse_date(item.findtext("pubDate"))
        if not title or not link:
            continue
        out.append(
            CentralBankSpeech(
                central_bank=feed.central_bank,
                speaker=_extract_speaker(title),
                title=title[:512],
                summary=summary[:2048],
                url=link[:1024],
                published_at=pub,
                fetched_at=fetched,
                source_feed=feed.name,
            )
        )

    # Atom fallback (Fed feeds use atom)
    ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}
    for entry in root.iterfind("a:entry", ATOM_NS):
        title = _strip_html(entry.findtext("a:title", namespaces=ATOM_NS))
        link_el = entry.find("a:link[@rel='alternate']", ATOM_NS) or entry.find("a:link", ATOM_NS)
        link = (link_el.get("href") or "").strip() if link_el is not None else ""
        summary = _strip_html(entry.findtext("a:summary", namespaces=ATOM_NS))
        pub = _parse_date(
            entry.findtext("a:published", namespaces=ATOM_NS)
            or entry.findtext("a:updated", namespaces=ATOM_NS)
        )
        if not title or not link:
            continue
        out.append(
            CentralBankSpeech(
                central_bank=feed.central_bank,
                speaker=_extract_speaker(title),
                title=title[:512],
                summary=summary[:2048],
                url=link[:1024],
                published_at=pub,
                fetched_at=fetched,
                source_feed=feed.name,
            )
        )

    return out


async def fetch_feed(
    feed: CentralBankSpeechFeed,
    *,
    client: httpx.AsyncClient,
    timeout: float = 20.0,
) -> list[CentralBankSpeech]:
    try:
        r = await client.get(
            feed.url,
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": "IchorCBSpeechCollector/0.1",
                "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.8",
            },
        )
        r.raise_for_status()
    except httpx.HTTPError as e:
        log.warning("cb_speeches.fetch_failed", source=feed.name, error=str(e))
        return []
    return parse_feed(feed, r.content)


async def poll_all(
    feeds: Iterable[CentralBankSpeechFeed] = DEFAULT_CB_FEEDS,
    *,
    concurrency: int = 4,
) -> list[CentralBankSpeech]:
    sem = asyncio.Semaphore(concurrency)

    async def _one(f: CentralBankSpeechFeed, client: httpx.AsyncClient) -> list[CentralBankSpeech]:
        async with sem:
            return await fetch_feed(f, client=client)

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*(_one(f, client) for f in feeds))

    seen_urls: set[str] = set()
    flat: list[CentralBankSpeech] = []
    for batch in results:
        for s in batch:
            if s.url in seen_urls:
                continue
            seen_urls.add(s.url)
            flat.append(s)

    flat.sort(key=lambda x: x.published_at, reverse=True)
    return flat
