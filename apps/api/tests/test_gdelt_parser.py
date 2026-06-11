"""Pure-parsing tests for the GDELT 2.0 collector."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ichor_api.collectors.gdelt import (
    ALL_QUERIES,
    DEFAULT_QUERIES,
    PER_ASSET_QUERIES,
    GdeltQuery,
    _parse_response,
    _parse_seendate,
)
from ichor_api.services.asset_news_affinity import matches_asset


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


# ── S03 per-asset slices ──────────────────────────────────────────────

# Label → the asset whose NEWS_KEYWORDS vocabulary it must carry. This is
# the load-bearing contract: `_section_geopolitics` matches the blob
# (title + query_label + domain + url) against NEWS_KEYWORDS, so a label
# drifting away from its asset's vocabulary silently kills the density
# the per-asset query was added to provide.
_LABEL_TO_ASSET = {
    "eurusd_eurozone": "EUR_USD",
    "gbpusd_uk_economy": "GBP_USD",
    "usdcad_boc_canada": "USD_CAD",
    "audusd_rba_china": "AUD_USD",
    "spx500_spx_us_equities": "SPX500_USD",
    "nas100_nasdaq_tech": "NAS100_USD",
}


def test_all_queries_is_global_plus_per_asset() -> None:
    assert ALL_QUERIES == DEFAULT_QUERIES + PER_ASSET_QUERIES
    labels = [q.label for q in ALL_QUERIES]
    assert len(labels) == len(set(labels)), "duplicate query labels"


def test_per_asset_queries_cover_the_uncovered_assets() -> None:
    assert set(_LABEL_TO_ASSET) == {q.label for q in PER_ASSET_QUERIES}


@pytest.mark.parametrize(("label", "asset"), sorted(_LABEL_TO_ASSET.items()))
def test_per_asset_query_labels_match_their_asset(label: str, asset: str) -> None:
    # The label alone (as part of the affinity blob) must match its asset.
    assert matches_asset(label, "", asset), f"label {label!r} no longer matches {asset}"


def test_per_asset_queries_respect_gdelt_syntax() -> None:
    for q in PER_ASSET_QUERIES:
        # OR groups must be parenthesised and non-nested (GDELT DOC 2.0).
        assert q.query.count("(") == q.query.count(")")
        assert q.query.count("(") == 1, f"{q.label}: GDELT forbids nested OR groups"
        # timespan must be >= 15min — we only use hour buckets.
        assert q.timespan.endswith("h")
