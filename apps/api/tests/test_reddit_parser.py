"""Tests for the Reddit public-JSON collector."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from ichor_api.collectors.reddit import (
    RedditPost,
    _decode_entities,
    listing_url,
    parse_listing,
    persist_to_news_items,
    post_to_news_item_payload,
)

# ─────────────────────── _decode_entities ────────────────────


def test_decode_entities_handles_amp_lt_gt() -> None:
    assert _decode_entities("a &amp; b &lt;c&gt;") == "a & b <c>"


def test_decode_entities_handles_quot_apos() -> None:
    assert _decode_entities("&quot;hi&quot; it&#39;s") == '"hi" it\'s'


def test_decode_entities_passes_through_plain_text() -> None:
    assert _decode_entities("plain text 100%") == "plain text 100%"


# ─────────────────────────── listing_url ────────────────────────────


def test_listing_url_basic() -> None:
    assert (
        listing_url("wallstreetbets") == "https://www.reddit.com/r/wallstreetbets/hot.json?limit=50"
    )


def test_listing_url_strips_r_prefix() -> None:
    assert listing_url("r/forex") == "https://www.reddit.com/r/forex/hot.json?limit=50"


def test_listing_url_clamps_limit() -> None:
    assert "limit=100" in listing_url("forex", limit=500)
    assert "limit=1" in listing_url("forex", limit=0)


def test_listing_url_supports_sort() -> None:
    assert "/top.json" in listing_url("forex", sort="top")
    assert "/new.json" in listing_url("forex", sort="new")


# ─────────────────────────── parse_listing ────────────────────────────


def _post_dict(
    *,
    name: str = "t3_abc123",
    title: str = "Inflation prints hot",
    score: int = 1234,
    is_self: bool = True,
    created_utc: float = 1746406800.0,  # 2025-05-04 21:00 UTC
) -> dict:
    return {
        "kind": "t3",
        "data": {
            "name": name,
            "title": title,
            "selftext": "<p>body text</p>" if is_self else "",
            "permalink": f"/r/wallstreetbets/comments/{name[3:]}/slug/",
            "url": "https://i.redd.it/example.png",
            "author": "alice",
            "score": score,
            "num_comments": 42,
            "created_utc": created_utc,
            "is_self": is_self,
        },
    }


def _listing_payload(*, children: list[dict]) -> dict:
    return {"kind": "Listing", "data": {"children": children}}


def test_parse_listing_extracts_typed_posts() -> None:
    body = json.dumps(_listing_payload(children=[_post_dict()]))
    posts = parse_listing(body, subreddit="wallstreetbets")
    assert len(posts) == 1
    p = posts[0]
    assert isinstance(p, RedditPost)
    assert p.name == "t3_abc123"
    assert p.title == "Inflation prints hot"
    assert p.url.startswith("https://www.reddit.com/r/wallstreetbets/comments/")
    assert p.score == 1234
    assert p.subreddit == "wallstreetbets"
    assert p.kind == "self"


def test_parse_listing_sorts_by_score_descending() -> None:
    body = json.dumps(
        _listing_payload(
            children=[
                _post_dict(name="t3_low", score=10),
                _post_dict(name="t3_high", score=9999),
                _post_dict(name="t3_mid", score=500),
            ]
        )
    )
    posts = parse_listing(body, subreddit="forex")
    scores = [p.score for p in posts]
    assert scores == sorted(scores, reverse=True)


def test_parse_listing_drops_t1_comments() -> None:
    """Reddit listings sometimes include comment objects (kind='t1')."""
    body = json.dumps(
        _listing_payload(
            children=[
                _post_dict(name="t3_keep"),
                {"kind": "t1", "data": {"name": "t1_drop", "body": "comment"}},
            ]
        )
    )
    posts = parse_listing(body, subreddit="forex")
    assert len(posts) == 1
    assert posts[0].name == "t3_keep"


def test_parse_listing_drops_empty_title_or_name() -> None:
    body = json.dumps(
        _listing_payload(
            children=[
                _post_dict(name=""),  # missing name
                _post_dict(name="t3_keep", title=""),  # missing title
                _post_dict(name="t3_real"),
            ]
        )
    )
    posts = parse_listing(body, subreddit="forex")
    assert [p.name for p in posts] == ["t3_real"]


def test_parse_listing_drops_zero_or_missing_created_utc() -> None:
    body = json.dumps(
        _listing_payload(
            children=[
                _post_dict(name="t3_no_ts", created_utc=0),
                _post_dict(name="t3_ok"),
            ]
        )
    )
    posts = parse_listing(body, subreddit="forex")
    assert [p.name for p in posts] == ["t3_ok"]


def test_parse_listing_decodes_html_entities_in_title() -> None:
    body = json.dumps(_listing_payload(children=[_post_dict(title="AT&amp;T &lt;rallies&gt;")]))
    posts = parse_listing(body, subreddit="forex")
    assert posts[0].title == "AT&T <rallies>"


def test_parse_listing_handles_link_post_kind() -> None:
    body = json.dumps(_listing_payload(children=[_post_dict(is_self=False)]))
    posts = parse_listing(body, subreddit="forex")
    assert posts[0].kind == "link"


def test_parse_listing_accepts_pre_parsed_dict() -> None:
    payload = _listing_payload(children=[_post_dict()])
    posts = parse_listing(payload, subreddit="forex")
    assert len(posts) == 1


def test_parse_listing_returns_empty_for_invalid_json() -> None:
    assert parse_listing("not-json{", subreddit="forex") == []


def test_parse_listing_returns_empty_for_unrelated_payload() -> None:
    assert parse_listing(json.dumps({"foo": "bar"}), subreddit="forex") == []


def test_parse_listing_caps_title_at_512_and_selftext_at_2000() -> None:
    body = json.dumps(
        _listing_payload(
            children=[
                {
                    "kind": "t3",
                    "data": {
                        "name": "t3_cap",
                        "title": "x" * 600,
                        "selftext": "y" * 5000,
                        "permalink": "/r/forex/comments/cap/slug/",
                        "url": "",
                        "author": "alice",
                        "score": 1,
                        "num_comments": 0,
                        "created_utc": 1746406800.0,
                        "is_self": True,
                    },
                }
            ]
        )
    )
    posts = parse_listing(body, subreddit="forex")
    assert len(posts[0].title) == 512
    assert len(posts[0].selftext) == 2000


def test_parse_listing_uses_permalink_for_url() -> None:
    body = json.dumps(_listing_payload(children=[_post_dict()]))
    posts = parse_listing(body, subreddit="wallstreetbets")
    assert posts[0].url.startswith("https://www.reddit.com/r/wallstreetbets/")


def test_parse_listing_falls_back_to_url_when_no_permalink() -> None:
    body = json.dumps(
        _listing_payload(
            children=[
                {
                    "kind": "t3",
                    "data": {
                        "name": "t3_link",
                        "title": "External link",
                        "selftext": "",
                        "permalink": "",
                        "url": "https://example.com/article",
                        "author": "alice",
                        "score": 100,
                        "num_comments": 5,
                        "created_utc": 1746406800.0,
                        "is_self": False,
                    },
                }
            ]
        )
    )
    posts = parse_listing(body, subreddit="forex")
    assert posts[0].url == "https://example.com/article"


# ─────────────────────── post_to_news_item_payload ────────────────────


def _post(**overrides: object) -> RedditPost:
    base = {
        "subreddit": "wallstreetbets",
        "name": "t3_abc",
        "title": "Macro is wild",
        "selftext": "Body",
        "url": "https://www.reddit.com/r/wallstreetbets/comments/abc/slug/",
        "author": "alice",
        "score": 1500,
        "num_comments": 10,
        "created_at": datetime(2026, 5, 4, 12, 0, tzinfo=UTC),
        "kind": "self",
    }
    base.update(overrides)
    return RedditPost(**base)  # type: ignore[arg-type]


def test_payload_basic_fields() -> None:
    p = post_to_news_item_payload(_post())
    assert p["source"] == "reddit:wallstreetbets"
    assert p["source_kind"] == "social"
    assert p["title"] == "Macro is wild"
    assert p["url"].startswith("https://www.reddit.com/")
    assert p["raw_categories"] == ["self", "alice"]
    assert isinstance(p["guid_hash"], str) and len(p["guid_hash"]) == 32


def test_payload_guid_hash_stable_for_same_name() -> None:
    a = post_to_news_item_payload(_post(name="t3_xyz"))
    b = post_to_news_item_payload(_post(name="t3_xyz", title="different title"))
    assert a["guid_hash"] == b["guid_hash"]


def test_payload_guid_hash_different_for_different_name() -> None:
    a = post_to_news_item_payload(_post(name="t3_aaa"))
    b = post_to_news_item_payload(_post(name="t3_bbb"))
    assert a["guid_hash"] != b["guid_hash"]


def test_payload_summary_capped_at_1024() -> None:
    p = post_to_news_item_payload(_post(selftext="z" * 5000))
    assert isinstance(p["summary"], str)
    assert len(p["summary"]) == 1024


def test_payload_summary_none_for_link_post() -> None:
    p = post_to_news_item_payload(_post(selftext="", kind="link"))
    assert p["summary"] is None


# ────────────────────────── persist_to_news_items ────────────────────


class _StubResult:
    def __init__(self, rows: list[tuple[str, str]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[str, str]]:
        return self._rows


class _StubSession:
    def __init__(self, existing: list[tuple[str, str]] | None = None) -> None:
        self._existing = existing or []
        self.added: list[object] = []
        self.flushed = 0

    async def execute(self, stmt: object) -> _StubResult:
        return _StubResult(self._existing)

    def add(self, row: object) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        self.flushed += 1


@pytest.mark.asyncio
async def test_persist_inserts_all_when_no_existing() -> None:
    session = _StubSession(existing=[])
    posts = [_post(name=f"t3_{i}") for i in range(5)]
    inserted = await persist_to_news_items(session, posts)
    assert inserted == 5
    assert len(session.added) == 5
    assert session.flushed == 1


@pytest.mark.asyncio
async def test_persist_skips_existing_pairs() -> None:
    posts = [_post(name="t3_dup"), _post(name="t3_new")]
    payload_dup = post_to_news_item_payload(posts[0])
    session = _StubSession(
        existing=[(payload_dup["source"], payload_dup["guid_hash"])]  # type: ignore[list-item]
    )
    inserted = await persist_to_news_items(session, posts)
    assert inserted == 1
    assert len(session.added) == 1


@pytest.mark.asyncio
async def test_persist_empty_list_short_circuits() -> None:
    session = _StubSession()
    inserted = await persist_to_news_items(session, [])
    assert inserted == 0
    assert session.added == []
    assert session.flushed == 0
