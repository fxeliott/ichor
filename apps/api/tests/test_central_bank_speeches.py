"""Pure-parsing tests for central_bank_speeches collector."""

from __future__ import annotations

from ichor_api.collectors.central_bank_speeches import (
    DEFAULT_CB_FEEDS,
    CentralBankSpeechFeed,
    parse_feed,
    _extract_speaker,
)


SAMPLE_BIS_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>BIS Central Bank Speeches</title>
    <link>https://bis.org/</link>
    <description>fixture</description>
    <item>
      <title>Christine Lagarde: Monetary policy statement</title>
      <link>https://bis.org/r/250503-lagarde.htm</link>
      <description>ECB press conference following the May meeting.</description>
      <pubDate>Wed, 03 May 2026 14:30:00 GMT</pubDate>
    </item>
    <item>
      <title>Jerome Powell: Speech at the Economic Club of NY</title>
      <link>https://bis.org/r/250503-powell.htm</link>
      <description>Powell remarks on inflation outlook.</description>
      <pubDate>Wed, 03 May 2026 18:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

SAMPLE_FEED = CentralBankSpeechFeed("bis_test", "https://example/", "BIS")


def test_parse_feed_extracts_two_items() -> None:
    out = parse_feed(SAMPLE_FEED, SAMPLE_BIS_RSS)
    assert len(out) == 2
    assert out[0].title.startswith("Christine Lagarde")
    assert out[1].title.startswith("Jerome Powell")


def test_parse_feed_extracts_speakers() -> None:
    out = parse_feed(SAMPLE_FEED, SAMPLE_BIS_RSS)
    assert out[0].speaker == "Christine Lagarde"
    assert out[1].speaker == "Jerome Powell"


def test_parse_feed_assigns_central_bank_from_feed_meta() -> None:
    out = parse_feed(SAMPLE_FEED, SAMPLE_BIS_RSS)
    assert all(s.central_bank == "BIS" for s in out)


def test_parse_feed_handles_malformed_xml() -> None:
    out = parse_feed(SAMPLE_FEED, b"<not actually xml")
    assert out == []


def test_extract_speaker_picks_name_before_colon() -> None:
    assert _extract_speaker("Lagarde: Welcome speech") == "Lagarde"
    assert _extract_speaker("Christine Lagarde: Statement") == "Christine Lagarde"


def test_extract_speaker_returns_none_when_no_colon() -> None:
    assert _extract_speaker("Just a title") is None


def test_extract_speaker_rejects_too_long_or_too_short() -> None:
    assert _extract_speaker("X: title") is None  # too short
    assert _extract_speaker(("Y" * 80) + ": title") is None  # too long


def test_default_cb_feeds_cover_main_central_banks() -> None:
    cbs = {f.central_bank for f in DEFAULT_CB_FEEDS}
    assert {"BIS", "Fed", "ECB", "BoE", "BoJ"} <= cbs
