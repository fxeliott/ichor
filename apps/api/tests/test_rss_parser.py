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
