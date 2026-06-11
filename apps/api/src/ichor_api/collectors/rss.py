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
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import httpx
import structlog

# defusedxml is a drop-in for `ElementTree.fromstring` that disables
# entity expansion attacks (billion-laughs, quadratic-blowup). The
# stdlib parser still accepts those even with externals off in 3.12.
# See HIGH/MED-1 in docs/audits/security-2026-05-03.md.
from defusedxml.ElementTree import fromstring as defused_fromstring

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
        # SECURITY: HTTPS only — http feeds are MITM-injectable and the
        # body flows into Claude's prompt context. See MED-2 in the
        # 2026-05-03 security audit.
        "https://feeds.bbci.co.uk/news/business/rss.xml",
        "news",
    ),
    # S03 "newsletters du monde" expansion — broadened the world-news +
    # CB surface. Every URL below was verified LIVE from the Hetzner
    # collector host (HTTP 200 + valid <rss>/<feed> body + multi-item)
    # on 2026-06-06 before being added; HTTPS-only (MITM safety). Dead /
    # non-RSS / 403 candidates (Treasury, IMF, FXStreet, SNB, BoC) were
    # rejected, never guessed.
    FeedSource(
        "boj_news",
        "https://www.boj.or.jp/en/rss/whatsnew.xml",
        "central_bank",
    ),
    FeedSource(
        # ForexLive rebranded to InvestingLive; the old URL 301-redirects.
        # Point at the canonical URL (no dependency on redirect-following);
        # the source NAME stays "forexlive" so guid_hash dedup history holds.
        "forexlive",
        "https://investinglive.com/feed/news",
        "news",
    ),
    FeedSource(
        "wsj_markets",
        "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
        "news",
    ),
    FeedSource(
        "marketwatch_top",
        "https://feeds.content.dowjones.io/public/rss/mw_topstories",
        "news",
    ),
    FeedSource(
        "investing_news",
        "https://www.investing.com/rss/news.rss",
        "news",
    ),
    FeedSource(
        "investing_economy",
        "https://www.investing.com/rss/news_25.rss",
        "news",
    ),
    # S03 second expansion (2026-06-11) — "interconnexion newsletters du
    # monde" depth pass. Every URL below was fetch-verified (HTTP 200 +
    # valid XML + items dated 2026-06-10/11) on 2026-06-11 before being
    # added; HTTPS-only (MITM safety, MED-2). Rejected after live checks,
    # never guessed: BLS news_release.rss (403 WAF), ReliefWeb (403 —
    # use their REST API later), Foreign Affairs (403 + paywall),
    # Treasury press (60s timeouts ×2), Reuters/AP (no public RSS since
    # 2020), Fed press_monetary (subset of press_all — per-source
    # guid_hash would duplicate every FOMC item), Eurostat news (feed
    # currently serves an empty skeleton).
    FeedSource(
        # RSS 1.0 / RDF format (rdf:RDF root, namespaced items) — parser
        # support added alongside (see the RSS 1.0 branch in parse_feed).
        "boc_press",
        "https://www.bankofcanada.ca/content_type/press-releases/feed/",
        "central_bank",
    ),
    FeedSource(
        "snb_news",
        "https://www.snb.ch/public/en/rss/news",
        "central_bank",
    ),
    FeedSource(
        "bea_releases",
        "https://apps.bea.gov/rss/rss.xml",
        "news",
    ),
    FeedSource(
        # Atom. The Daily = all StatCan releases, 08:30 ET — the USD_CAD
        # macro surface (CPI, labour, GDP, trade).
        "statcan_daily",
        "https://www150.statcan.gc.ca/n1/rss/dai-quo/0-eng.atom",
        "news",
    ),
    FeedSource(
        # UK release calendar — publication times for GBP macro prints.
        "ons_releases",
        "https://www.ons.gov.uk/releasecalendar?rss",
        "news",
    ),
    # fxstreet_news REMOVED 2026-06-11 same-day: 403 from the Hetzner host
    # with bot AND browser UAs (datacenter-IP WAF block — the feed answers
    # 200 from residential IPs). A permanently-403 entry would only pollute
    # the RSS_FEED_SILENT monitor; continuous FX flow stays covered by
    # forexlive/investinglive.
    FeedSource(
        "eia_today_in_energy",
        "https://www.eia.gov/rss/todayinenergy.xml",
        "news",
    ),
    FeedSource(
        "cnbc_economy",
        "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258",
        "news",
    ),
    FeedSource(
        "oilprice",
        "https://oilprice.com/rss/main",
        "news",
    ),
    FeedSource(
        # Geopolitical risk surface (XAU + risk sentiment) — the only
        # geopolitics-dedicated feed that survived live verification.
        "crisisgroup",
        "https://www.crisisgroup.org/rss",
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
    # RSS 1.0 (RDF) — used by Bank of Canada press releases among others.
    "rss1": "http://purl.org/rss/1.0/",
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
        return datetime.now(UTC)
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except (TypeError, ValueError):
        pass
    try:
        # Atom-style ISO 8601. fromisoformat returns a NAIVE datetime when the
        # string carries no offset (e.g. "2026-06-06T12:00:00") — coerce to UTC
        # like the RFC-822 branch, else poll_all's mixed-tz sort raises
        # "can't compare offset-naive and offset-aware datetimes".
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except ValueError:
        return datetime.now(UTC)


def _hash(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8", errors="ignore"))
        h.update(b"|")
    return h.hexdigest()[:32]


def parse_feed(source: FeedSource, body: bytes) -> list[NewsItem]:
    """Parse RSS 2.0, RSS 1.0 (RDF) OR Atom; return normalized items.

    Resilient to malformed feeds: on XML errors returns []. Logs the issue.
    """
    try:
        # defusedxml refuses entity-expansion attacks but is otherwise
        # ElementTree API-compatible.
        root = defused_fromstring(body)
    except ET.ParseError as e:
        log.warning("rss.parse_failed", source=source.name, error=str(e))
        return []

    items: list[NewsItem] = []
    fetched = datetime.now(UTC)

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

    # RSS 1.0 / RDF — <rdf:RDF><item xmlns="http://purl.org/rss/1.0/">.
    # Items are namespaced (unlike RSS 2.0) and dates live in <dc:date>
    # (ISO-8601). Bank of Canada press releases use this format.
    for item in root.iterfind(".//rss1:item", _NS):
        title = _strip_html(item.findtext("rss1:title", namespaces=_NS))
        link = (item.findtext("rss1:link", namespaces=_NS) or "").strip()
        about = item.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about") or ""
        guid = (about or link or title).strip()
        summary = _full_text(item.find("rss1:description", _NS))
        pub = _parse_date(item.findtext("dc:date", namespaces=_NS))
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
                raw_categories=[],
            )
        )

    # Atom — <feed><entry>
    for entry in root.iterfind("atom:entry", _NS):
        # _full_text, not findtext: Atom allows <title type="xhtml"> whose
        # text lives in a nested xhtml <div> (RFC 4287 §3.1.1) — findtext
        # returns the title element's OWN (empty) text and the item is
        # silently skipped (StatCan The Daily, witnessed prod 2026-06-11).
        title = _full_text(entry.find("atom:title", _NS))
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
                    "application/rss+xml, application/atom+xml, application/xml;q=0.8, */*;q=0.5"
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
