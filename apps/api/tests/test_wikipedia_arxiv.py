"""Pure-parsing tests for Wikipedia Pageviews + arXiv q-fin collectors."""

from __future__ import annotations

from datetime import date, datetime

from ichor_api.collectors.arxiv_qfin import (
    WATCHED_CATEGORIES,
    parse_arxiv_response,
    supported_categories,
)
from ichor_api.collectors.wikipedia_pageviews import (
    WATCHED_ARTICLES,
    parse_pageviews_response,
    supported_articles,
)


# ── Wikipedia ────────────────────────────────────────────────────────


def test_wikipedia_parse_canonical() -> None:
    body = {
        "items": [
            {
                "project": "en.wikipedia.org",
                "article": "Recession",
                "granularity": "daily",
                "timestamp": "2026050100",
                "access": "all-access",
                "agent": "all-agents",
                "views": 12345,
            },
            {
                "project": "en.wikipedia.org",
                "article": "Recession",
                "timestamp": "2026050200",
                "views": 13456,
            },
        ]
    }
    out = parse_pageviews_response("en.wikipedia.org", "Recession", body)
    assert len(out) == 2
    assert out[0].views == 12345
    assert out[0].observation_date == date(2026, 5, 1)


def test_wikipedia_parse_skips_malformed() -> None:
    body = {
        "items": [
            {"timestamp": "bad-date", "views": 1},
            {"timestamp": "2026050100", "views": "not-a-number"},
            {"timestamp": "2026050100", "views": 100},
            "garbage-entry",
        ]
    }
    out = parse_pageviews_response("x", "y", body)
    assert len(out) == 1


def test_wikipedia_articles_macro_focused() -> None:
    arts = supported_articles()
    titles = {a for _, a in arts}
    assert "Recession" in titles
    assert "Federal_Reserve" in titles
    assert "Inflation" in titles


# ── arXiv ────────────────────────────────────────────────────────────


_SAMPLE_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
  <entry>
    <id>http://arxiv.org/abs/2603.01234v1</id>
    <updated>2026-04-30T18:00:00Z</updated>
    <published>2026-04-30T18:00:00Z</published>
    <title>VPIN-Based Microstructure Toxicity in FX</title>
    <summary>We extend the VPIN estimator to FX quote streams using
    bulk-volume classification on quote-update tick counts...</summary>
    <author><name>Alice Dupont</name></author>
    <author><name>Bob Sato</name></author>
    <category term="q-fin.TR"/>
    <category term="q-fin.ST"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2603.05678v2</id>
    <updated>2026-04-29T12:00:00Z</updated>
    <published>2026-04-29T12:00:00Z</published>
    <title>Brier-Score Online Calibration for Macro Forecasts</title>
    <summary>We propose a projected-SGD update to confluence weights...</summary>
    <author><name>Charlie Smith</name></author>
    <category term="q-fin.RM"/>
  </entry>
</feed>
"""


def test_arxiv_parse_canonical_atom() -> None:
    papers = parse_arxiv_response(_SAMPLE_ATOM)
    assert len(papers) == 2
    assert papers[0].arxiv_id == "2603.01234v1"
    assert "VPIN" in papers[0].title
    assert papers[0].primary_category in {"q-fin.TR", "q-fin.ST"}


def test_arxiv_parse_extracts_authors() -> None:
    papers = parse_arxiv_response(_SAMPLE_ATOM)
    assert len(papers[0].authors) == 2
    assert "Alice Dupont" in papers[0].authors
    assert papers[1].authors == ("Charlie Smith",)


def test_arxiv_parse_pdf_url_derived_from_abs() -> None:
    papers = parse_arxiv_response(_SAMPLE_ATOM)
    assert papers[0].pdf_url == "http://arxiv.org/pdf/2603.01234v1"


def test_arxiv_parse_malformed_xml_returns_empty() -> None:
    assert parse_arxiv_response("<not-xml>") == []
    assert parse_arxiv_response("") == []


def test_arxiv_categories_cover_trading_finance() -> None:
    cats = supported_categories()
    assert "q-fin.ST" in cats  # statistical finance
    assert "q-fin.TR" in cats  # trading/microstructure
    assert "q-fin.RM" in cats  # risk management
