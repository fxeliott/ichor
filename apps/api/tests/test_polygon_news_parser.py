"""Pure-parsing tests for the Polygon News collector."""

from __future__ import annotations

from datetime import UTC, datetime

from ichor_api.collectors.polygon_news import (
    PolygonNewsItem,
    parse_news_response,
    relevant_to_ichor_universe,
)


def _ok_body(*results: dict) -> dict:
    return {"results": list(results), "status": "OK"}


def test_parse_minimal_valid_item() -> None:
    body = _ok_body(
        {
            "id": "abc123",
            "title": "  Fed signals patient stance on rates  ",
            "article_url": "https://reuters.com/x",
            "published_utc": "2026-05-03T14:00:00Z",
            "publisher": {"name": "Reuters"},
        }
    )
    items = parse_news_response(body)
    assert len(items) == 1
    it = items[0]
    assert it.id == "abc123"
    assert it.title == "Fed signals patient stance on rates"  # stripped
    assert it.url == "https://reuters.com/x"
    assert it.published_at == datetime(2026, 5, 3, 14, 0, 0, tzinfo=UTC)
    assert it.publisher_name == "Reuters"
    assert it.tickers == ()
    assert it.keywords == ()


def test_parse_full_item_with_tickers_and_insights() -> None:
    body = _ok_body(
        {
            "id": "xyz",
            "title": "NVDA Q1 beats expectations",
            "article_url": "https://wsj.com/nvda",
            "published_utc": "2026-05-03T18:30:00Z",
            "publisher": {
                "name": "WSJ",
                "homepage_url": "https://www.wsj.com",
                "logo_url": "...",
            },
            "description": "Nvidia reported revenue of...",
            "tickers": ["NVDA", "AMD", "MSFT"],
            "keywords": ["earnings", "ai", "semiconductors"],
            "image_url": "https://...",
            "insights": [{"sentiment": "positive", "ticker": "NVDA"}],
        }
    )
    items = parse_news_response(body)
    assert len(items) == 1
    it = items[0]
    assert it.tickers == ("NVDA", "AMD", "MSFT")
    assert it.keywords == ("earnings", "ai", "semiconductors")
    assert it.publisher_url == "https://www.wsj.com"
    assert it.description.startswith("Nvidia reported")
    assert len(it.insights) == 1
    assert it.insights[0]["ticker"] == "NVDA"


def test_parse_drops_rows_missing_required_fields() -> None:
    body = _ok_body(
        {
            "id": "ok1",
            "title": "Has all",
            "article_url": "u1",
            "published_utc": "2026-05-03T14:00:00Z",
            "publisher": {"name": "X"},
        },
        {
            "id": "no_title",
            "article_url": "u2",
            "published_utc": "2026-05-03T14:00:00Z",
        },  # missing title
        {"id": "no_url", "title": "X", "published_utc": "2026-05-03T14:00:00Z"},  # missing url
        {"title": "no_id", "article_url": "u3", "published_utc": "2026-05-03T14:00:00Z"},
        {"id": "no_published", "title": "X", "article_url": "u4"},
        {"id": "bad_date", "title": "X", "article_url": "u5", "published_utc": "not-a-date"},
    )
    items = parse_news_response(body)
    assert [i.id for i in items] == ["ok1"]


def test_parse_handles_empty_or_missing_results() -> None:
    assert parse_news_response({}) == []
    assert parse_news_response({"results": []}) == []
    assert parse_news_response({"results": None}) == []


def test_parse_defensive_against_non_list_tickers() -> None:
    body = _ok_body(
        {
            "id": "id",
            "title": "T",
            "article_url": "u",
            "published_utc": "2026-05-03T14:00:00Z",
            "publisher": {"name": "X"},
            "tickers": "should_be_a_list",  # broken upstream
            "keywords": None,
        }
    )
    items = parse_news_response(body)
    assert items[0].tickers == ()
    assert items[0].keywords == ()


def test_relevant_keeps_macro_items_without_tickers() -> None:
    """No tickers = macro/geo news → kept."""
    item = PolygonNewsItem(
        id="x",
        title="ECB Lagarde dovish",
        url="u",
        published_at=datetime(2026, 5, 3, tzinfo=UTC),
        publisher_name="Reuters",
        publisher_url=None,
        description=None,
        tickers=(),
        keywords=(),
        image_url=None,
    )
    assert relevant_to_ichor_universe(item) is True


def test_relevant_keeps_mega_cap_7() -> None:
    for ticker in ("AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"):
        item = PolygonNewsItem(
            id="x",
            title="...",
            url="u",
            published_at=datetime(2026, 5, 3, tzinfo=UTC),
            publisher_name="X",
            publisher_url=None,
            description=None,
            tickers=(ticker,),
            keywords=(),
            image_url=None,
        )
        assert relevant_to_ichor_universe(item) is True, f"{ticker} should be kept"


def test_relevant_keeps_xau_proxies() -> None:
    for ticker in ("GLD", "IAU", "GDX", "SPDR"):
        item = PolygonNewsItem(
            id="x",
            title="...",
            url="u",
            published_at=datetime(2026, 5, 3, tzinfo=UTC),
            publisher_name="X",
            publisher_url=None,
            description=None,
            tickers=(ticker,),
            keywords=(),
            image_url=None,
        )
        assert relevant_to_ichor_universe(item) is True


def test_relevant_drops_unrelated_smallcap() -> None:
    item = PolygonNewsItem(
        id="x",
        title="Random small-cap merger",
        url="u",
        published_at=datetime(2026, 5, 3, tzinfo=UTC),
        publisher_name="X",
        publisher_url=None,
        description=None,
        tickers=("CWH", "PETS"),
        keywords=(),
        image_url=None,
    )
    assert relevant_to_ichor_universe(item) is False


def test_relevant_keeps_dxy_and_fx_direct() -> None:
    item = PolygonNewsItem(
        id="x",
        title="DXY breaks 105",
        url="u",
        published_at=datetime(2026, 5, 3, tzinfo=UTC),
        publisher_name="X",
        publisher_url=None,
        description=None,
        tickers=("DXY",),
        keywords=(),
        image_url=None,
    )
    assert relevant_to_ichor_universe(item) is True


def test_parse_sort_preserved() -> None:
    """Order returned by Massive (desc by published) is preserved."""
    body = _ok_body(
        {
            "id": "newest",
            "title": "T1",
            "article_url": "u1",
            "published_utc": "2026-05-03T15:00:00Z",
            "publisher": {"name": "X"},
        },
        {
            "id": "older",
            "title": "T2",
            "article_url": "u2",
            "published_utc": "2026-05-03T14:00:00Z",
            "publisher": {"name": "X"},
        },
    )
    items = parse_news_response(body)
    assert [i.id for i in items] == ["newest", "older"]
