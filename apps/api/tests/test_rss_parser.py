"""Pure-parsing tests for the RSS collector.

No HTTP — feed XML is hand-crafted. Validates:
  - RSS 2.0 + Atom both parse cleanly.
  - Items dedupe by guid_hash.
  - Malformed XML downgrades to [] without raising.
  - HTML stripping leaves clean summaries.
  - Date parsing handles RFC-822 + ISO-8601 + missing field.
"""

from __future__ import annotations

import pytest
from ichor_api.collectors.rss import (
    DEFAULT_FEEDS,
    FeedSource,
    NewsItem,
    _parse_date,
    parse_feed,
)

SOURCE_RSS = FeedSource(name="rss_test", url="https://example.test/rss", kind="news")
SOURCE_ATOM = FeedSource(name="atom_test", url="https://example.test/atom", kind="news")


RSS_BODY = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test feed</title>
    <link>https://example.test/</link>
    <description>fixture</description>
    <item>
      <title>Fed pauses rate hikes</title>
      <link>https://example.test/news/1</link>
      <description>The Federal Reserve <b>paused</b> after a 525bp cycle.</description>
      <guid isPermaLink="false">id-1</guid>
      <pubDate>Wed, 01 May 2026 14:30:00 GMT</pubDate>
      <category>Macro</category>
      <category>Fed</category>
    </item>
    <item>
      <title>ECB hints at June cut</title>
      <link>https://example.test/news/2</link>
      <description>Lagarde signaled a possible easing.</description>
      <guid>id-2</guid>
      <pubDate>Wed, 01 May 2026 09:15:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


ATOM_BODY = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Atom test</title>
  <link href="https://example.test/atom"/>
  <updated>2026-05-01T14:30:00Z</updated>
  <id>urn:test:atom</id>
  <entry>
    <title>BoE on hold</title>
    <link rel="alternate" href="https://example.test/atom/1"/>
    <id>urn:test:atom:1</id>
    <updated>2026-05-01T14:30:00Z</updated>
    <published>2026-05-01T14:30:00Z</published>
    <summary>Bank of England left rates unchanged.</summary>
    <category term="Macro"/>
  </entry>
</feed>
"""


def test_parse_rss_extracts_items() -> None:
    items = parse_feed(SOURCE_RSS, RSS_BODY)
    assert len(items) == 2
    titles = {it.title for it in items}
    assert "Fed pauses rate hikes" in titles
    assert "ECB hints at June cut" in titles


def test_parse_rss_strips_html_from_summary() -> None:
    items = parse_feed(SOURCE_RSS, RSS_BODY)
    fed = next(it for it in items if "Fed" in it.title)
    assert "<b>" not in fed.summary
    assert "paused" in fed.summary


def test_parse_rss_categories() -> None:
    items = parse_feed(SOURCE_RSS, RSS_BODY)
    fed = next(it for it in items if "Fed" in it.title)
    assert "Macro" in fed.raw_categories
    assert "Fed" in fed.raw_categories


def test_parse_rss_pubdate_rfc822() -> None:
    items = parse_feed(SOURCE_RSS, RSS_BODY)
    fed = next(it for it in items if "Fed" in it.title)
    assert fed.published_at.year == 2026
    assert fed.published_at.month == 5
    assert fed.published_at.day == 1
    assert fed.published_at.hour == 14
    assert fed.published_at.tzinfo is not None


def test_parse_atom_extracts_items() -> None:
    items = parse_feed(SOURCE_ATOM, ATOM_BODY)
    assert len(items) == 1
    boe = items[0]
    assert boe.title == "BoE on hold"
    assert boe.url == "https://example.test/atom/1"
    assert boe.summary.startswith("Bank of England")


def test_parse_atom_isodate() -> None:
    items = parse_feed(SOURCE_ATOM, ATOM_BODY)
    assert items[0].published_at.year == 2026
    assert items[0].published_at.tzinfo is not None


def test_parse_malformed_returns_empty() -> None:
    """Malformed XML should not raise — collector keeps running."""
    items = parse_feed(SOURCE_RSS, b"<not really xml")
    assert items == []


def test_guid_hash_deterministic_per_source() -> None:
    """Same guid + same source produces same hash (key invariant for dedup)."""
    items_a = parse_feed(SOURCE_RSS, RSS_BODY)
    items_b = parse_feed(SOURCE_RSS, RSS_BODY)
    hashes_a = {i.guid_hash for i in items_a}
    hashes_b = {i.guid_hash for i in items_b}
    assert hashes_a == hashes_b


def test_guid_hash_changes_across_sources() -> None:
    """Same guid in different feeds must produce different hashes (no cross-feed collision)."""
    item_a = parse_feed(SOURCE_RSS, RSS_BODY)[0]
    other = FeedSource(name="other", url="https://other.test/rss", kind="news")
    item_b = parse_feed(other, RSS_BODY)[0]
    assert item_a.guid_hash != item_b.guid_hash


def test_default_feeds_is_non_empty_and_unique() -> None:
    """At least one feed of each kind so failure of one source doesn't blackout."""
    assert len(DEFAULT_FEEDS) >= 3
    names = [f.name for f in DEFAULT_FEEDS]
    assert len(set(names)) == len(names)
    kinds = {f.kind for f in DEFAULT_FEEDS}
    assert "central_bank" in kinds
    assert "news" in kinds


def test_default_feeds_https_only_and_s03_expansion() -> None:
    """S03 'newsletters du monde' expansion (2026-06-06): every feed is HTTPS
    (MITM safety — the body flows into the LLM prompt, MED-2 2026-05-03 audit),
    URLs are unique, kinds are valid, and the verified-live broadened world-news
    + central-bank surface is present (each URL HTTP-200 + valid RSS, checked
    from the Hetzner collector host before being added)."""
    assert all(f.url.startswith("https://") for f in DEFAULT_FEEDS), (
        "non-HTTPS feed present — http feeds are MITM-injectable"
    )
    urls = [f.url for f in DEFAULT_FEEDS]
    assert len(set(urls)) == len(urls), "duplicate feed URL"
    assert all(f.kind in {"central_bank", "news", "regulator"} for f in DEFAULT_FEEDS)
    names = {f.name for f in DEFAULT_FEEDS}
    assert {
        "boj_news",
        "forexlive",
        "wsj_markets",
        "marketwatch_top",
        "investing_news",
        "investing_economy",
    }.issubset(names), "S03 verified-live feed additions missing"
    assert len(DEFAULT_FEEDS) >= 11


RDF_BODY = b"""<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns="http://purl.org/rss/1.0/"
         xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel rdf:about="https://example.test/rdf">
    <title>BoC-style RDF feed</title>
    <link>https://example.test/</link>
  </channel>
  <item rdf:about="https://example.test/rdf/1">
    <title>Bank of Canada holds policy rate</title>
    <link>https://example.test/rdf/1</link>
    <description>The Bank held its target for the overnight rate.</description>
    <dc:date>2026-06-10T09:45:00-04:00</dc:date>
  </item>
  <item rdf:about="https://example.test/rdf/2">
    <title>Monetary Policy Report</title>
    <link>https://example.test/rdf/2</link>
    <dc:date>2026-06-10T10:30:00-04:00</dc:date>
  </item>
</rdf:RDF>
"""


def test_parse_rss1_rdf_extracts_items() -> None:
    """RSS 1.0 / RDF (Bank of Canada press releases): namespaced <item>
    elements under <rdf:RDF>, ISO dates in <dc:date>. The RSS 2.0 branch
    (`.//item`, namespace-less) cannot see these — S03 added a dedicated
    branch; this pins it."""
    src = FeedSource(name="boc_test", url="https://example.test/rdf", kind="central_bank")
    items = parse_feed(src, RDF_BODY)
    assert len(items) == 2
    boc = next(it for it in items if "policy rate" in it.title)
    assert boc.url == "https://example.test/rdf/1"
    assert boc.summary.startswith("The Bank held")
    assert boc.published_at.tzinfo is not None
    assert boc.published_at.hour == 9  # -04:00 offset preserved through parse
    # rdf:about is the dedup guid — distinct per item.
    assert len({it.guid_hash for it in items}) == 2


def test_s03_second_expansion_feeds_present() -> None:
    """S03 depth pass (2026-06-11): the fetch-verified world-newsletter
    surface — central banks (BoC RDF, SNB), official statistics (BEA,
    StatCan, ONS), FX/markets flow (FXStreet), energy (EIA, OilPrice),
    geopolitics (Crisis Group), economy (CNBC)."""
    names = {f.name for f in DEFAULT_FEEDS}
    assert {
        "boc_press",
        "snb_news",
        "bea_releases",
        "statcan_daily",
        "ons_releases",
        "fxstreet_news",
        "eia_today_in_energy",
        "cnbc_economy",
        "oilprice",
        "crisisgroup",
    }.issubset(names), "S03 second-expansion feeds missing"
    assert len(DEFAULT_FEEDS) >= 21
    # ForexLive rebrand: canonical URL, no 301 dependency; name unchanged
    # so guid_hash dedup history holds.
    fl = next(f for f in DEFAULT_FEEDS if f.name == "forexlive")
    assert fl.url == "https://investinglive.com/feed/news"


def test_parse_date_always_timezone_aware() -> None:
    """Regression (S03 feed expansion, observed live 2026-06-06): every parsed
    date MUST be tz-aware. A naive datetime from the ISO fallback crashes
    poll_all's newest-first sort with mixed-tz feeds (TypeError: can't compare
    offset-naive and offset-aware datetimes)."""
    # tz-less ISO 8601 (the bug: fromisoformat returns NAIVE here).
    assert _parse_date("2026-06-06T12:00:00").tzinfo is not None
    # Already-working forms, pinned so the fix doesn't regress them.
    assert _parse_date("Fri, 06 Jun 2026 12:00:00 GMT").tzinfo is not None
    assert _parse_date("2026-06-06T12:00:00Z").tzinfo is not None
    assert _parse_date("2026-06-06T12:00:00+02:00").tzinfo is not None
    assert _parse_date(None).tzinfo is not None
    assert _parse_date("garbage-not-a-date").tzinfo is not None


def test_skips_items_without_title_or_link() -> None:
    body = b"""<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item><guid>a</guid></item>
      <item><title>only-title</title><guid>b</guid></item>
      <item><title>complete</title><link>https://example.test/c</link><guid>c</guid></item>
    </channel></rss>
    """
    items = parse_feed(SOURCE_RSS, body)
    assert [it.title for it in items] == ["complete"]


@pytest.mark.parametrize("kind", ["news", "central_bank", "regulator"])
def test_news_item_carries_source_kind(kind: str) -> None:
    src = FeedSource(name=f"k_{kind}", url="x", kind=kind)
    items = parse_feed(src, RSS_BODY)
    assert all(isinstance(it, NewsItem) for it in items)
    assert all(it.source_kind == kind for it in items)
