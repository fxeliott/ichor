"""Pure-parsing tests for the GDELT 2.0 collector."""

from __future__ import annotations

from datetime import UTC, datetime

from ichor_api.collectors.gdelt import (
    DEFAULT_QUERIES,
    GdeltQuery,
    _parse_response,
    _parse_seendate,
)


def test_parse_seendate_valid() -> None:
    dt = _parse_seendate("20260503T093000Z")
    assert dt.year == 2026
    assert dt.month == 5
    assert dt.day == 3
    assert dt.tzinfo == UTC


def test_parse_seendate_invalid_falls_back() -> None:
    dt = _parse_seendate("not-a-date")
    assert isinstance(dt, datetime)
    assert dt.tzinfo == UTC


def test_parse_response_extracts_articles() -> None:
    payload = {
        "articles": [
            {
                "url": "https://reuters.com/x",
                "title": "Fed pauses rate hikes",
                "seendate": "20260503T093000Z",
                "domain": "reuters.com",
                "language": "English",
                "sourcecountry": "United States",
                "tone": "-2.5",
                "socialimage": "https://x/img.jpg",
            },
            {
                "url": "https://lemonde.fr/y",
                "title": "La BCE réfléchit à une baisse",
                "seendate": "20260503T101500Z",
                "domain": "lemonde.fr",
                "language": "French",
                "sourcecountry": "France",
                "tone": "1.0",
            },
        ]
    }
    arts = _parse_response("fed", payload)
    assert len(arts) == 2
    assert arts[0].url == "https://reuters.com/x"
    assert arts[0].language == "English"
    assert arts[0].tone == -2.5
    assert arts[1].language == "French"


def test_parse_response_handles_empty() -> None:
    assert _parse_response("fed", {}) == []
    assert _parse_response("fed", {"articles": []}) == []


def test_parse_response_skips_malformed_row() -> None:
    payload = {
        "articles": [
            {
                "url": "https://ok.com/a",
                "title": "OK",
                "seendate": "20260503T000000Z",
                "domain": "ok.com",
                "language": "en",
                "sourcecountry": "US",
                "tone": "0",
            },
            {"url": "https://bad.com/b", "title": "Bad", "tone": "not-a-number"},  # bad tone
            {
                "url": "https://ok.com/c",
                "title": "OK2",
                "seendate": "20260503T000000Z",
                "domain": "ok.com",
                "language": "en",
                "sourcecountry": "US",
                "tone": "0",
            },
        ]
    }
    arts = _parse_response("fed", payload)
    # The malformed one is skipped, two valid kept
    assert len(arts) == 2


def test_default_queries_cover_phase1_topics() -> None:
    labels = {q.label for q in DEFAULT_QUERIES}
    assert {"fed", "ecb", "boe", "boj", "geopolitics", "us_data", "oil", "gold"} <= labels


def test_query_has_reasonable_defaults() -> None:
    q = GdeltQuery("test", "x AND y")
    assert q.timespan == "1h"
    assert q.max_records == 25
