"""W103 (ADR-084) — tests for the SearXNG live-web-research service.

Covers : happy path (SearXNG JSON → snapshots) ; dedup (duplicate URLs +
near-duplicate titles collapsed) ; ADR-017 DROP (a result with BUY/SELL
in title/snippet is dropped) ; fail-open (httpx error → []) ; cache (2nd
call within TTL doesn't re-hit httpx) ; per-asset query map present ;
plus the `_section_web_research` data_pool section (honest-absence +
ADR-017-clean render) with `fetch_web_research` mocked.

httpx is mocked via a fake AsyncClient (no respx in this venv) — the
service owns its client via `async with httpx.AsyncClient()`, so we
monkeypatch `web_research.httpx.AsyncClient` with a fake whose `.get`
returns a canned FRED/SearXNG-shaped response. Mirrors the
MagicMock/AsyncMock house style of test_economic_event_actuals_reconciler.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
from ichor_api.services import data_pool, web_research
from ichor_api.services.adr017_filter import is_adr017_clean
from ichor_api.services.web_research import (
    WebResultSnapshot,
    clear_web_research_cache,
    fetch_web_research,
)


@pytest.fixture(autouse=True)
def _flush_cache() -> None:
    """Each test starts with an empty in-process query cache."""
    clear_web_research_cache()
    yield
    clear_web_research_cache()


# ─────────────────────── Fake httpx.AsyncClient ───────────────────────


class _FakeResponse:
    def __init__(self, payload: dict, *, raise_exc: Exception | None = None) -> None:
        self._payload = payload
        self._raise_exc = raise_exc
        self.status_code = 200

    def raise_for_status(self) -> None:
        if self._raise_exc is not None:
            raise self._raise_exc

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    """Async-context-manager stand-in for httpx.AsyncClient.

    Records every `.get` call ; returns the configured response. A class
    counter tracks how many GETs happened in total so cache-hit tests
    can assert "no second hit".
    """

    get_calls: list[dict] = []

    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    @classmethod
    def reset(cls) -> None:
        cls.get_calls = []

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def get(self, url: str, **kwargs: object) -> _FakeResponse:
        type(self).get_calls.append({"url": url, "kwargs": kwargs})
        return self._response


def _install_fake_client(monkeypatch, payload: dict, *, raise_exc: Exception | None = None) -> None:
    """Patch web_research.httpx.AsyncClient → fake returning `payload`."""
    _FakeAsyncClient.reset()
    response = _FakeResponse(payload, raise_exc=raise_exc)

    def _factory(*args: object, **kwargs: object) -> _FakeAsyncClient:
        return _FakeAsyncClient(response)

    monkeypatch.setattr(web_research.httpx, "AsyncClient", _factory)


def _searxng_payload(results: list[dict]) -> dict:
    return {"results": results, "number_of_results": len(results)}


# ─────────────────────────── happy path ───────────────────────────────


@pytest.mark.asyncio
async def test_happy_path_parses_searxng_json(monkeypatch) -> None:
    payload = _searxng_payload(
        [
            {
                "title": "ECB holds rates as inflation cools",
                "url": "https://www.reuters.com/markets/ecb-holds",
                "content": "The European Central Bank kept rates unchanged today.",
                "engine": "google",
                "publishedDate": "2026-06-02T08:00:00Z",
            },
            {
                "title": "Eurozone PMI ticks higher in June",
                "url": "https://www.ft.com/eurozone-pmi",
                "content": "Business activity expanded modestly.",
                "engine": "bing",
                "publishedDate": None,
            },
        ]
    )
    _install_fake_client(monkeypatch, payload)

    out = await fetch_web_research("EUR USD ECB Fed today", limit=6)

    assert len(out) == 2
    first = out[0]
    assert isinstance(first, WebResultSnapshot)
    assert first.title == "ECB holds rates as inflation cools"
    assert first.url == "https://www.reuters.com/markets/ecb-holds"
    assert first.source_domain == "reuters.com"  # www. stripped
    assert first.engine == "google"
    assert first.published_at == "2026-06-02T08:00:00Z"
    assert out[1].published_at is None
    # SearXNG /search?format=json endpoint hit.
    assert len(_FakeAsyncClient.get_calls) == 1
    assert _FakeAsyncClient.get_calls[0]["url"].endswith("/search")
    assert _FakeAsyncClient.get_calls[0]["kwargs"]["params"]["format"] == "json"


@pytest.mark.asyncio
async def test_limit_caps_results(monkeypatch) -> None:
    payload = _searxng_payload(
        [
            {"title": f"Headline {i}", "url": f"https://site{i}.com/a", "content": f"body {i}"}
            for i in range(10)
        ]
    )
    _install_fake_client(monkeypatch, payload)
    out = await fetch_web_research("gold price drivers today", limit=3)
    assert len(out) == 3


# ─────────────────────────────── dedup ────────────────────────────────


@pytest.mark.asyncio
async def test_dedup_drops_duplicate_urls(monkeypatch) -> None:
    payload = _searxng_payload(
        [
            {"title": "Gold rises on haven bid", "url": "https://x.com/gold", "content": "a"},
            {"title": "Different headline entirely", "url": "https://x.com/gold", "content": "b"},
            {"title": "A third unique story about yen", "url": "https://y.com/yen", "content": "c"},
        ]
    )
    _install_fake_client(monkeypatch, payload)
    out = await fetch_web_research("XAU USD today", limit=6)
    urls = [r.url for r in out]
    assert urls == ["https://x.com/gold", "https://y.com/yen"]


@pytest.mark.asyncio
async def test_dedup_drops_near_duplicate_titles(monkeypatch) -> None:
    payload = _searxng_payload(
        [
            {
                "title": "EUR USD slips as ECB holds rates steady today",
                "url": "https://a.com/1",
                "content": "story a",
            },
            {
                "title": "EUR USD slips as ECB holds rates steady",
                "url": "https://b.com/2",
                "content": "story b syndicated",
            },
        ]
    )
    _install_fake_client(monkeypatch, payload)
    out = await fetch_web_research("EUR USD ECB today", limit=6)
    # Near-dup title (Jaccard ≥ 0.85) → only the first (higher-ranked) kept.
    assert len(out) == 1
    assert out[0].url == "https://a.com/1"


# ───────────────────────── ADR-017 DROP policy ────────────────────────


@pytest.mark.asyncio
async def test_adr017_drops_dirty_snippet(monkeypatch) -> None:
    payload = _searxng_payload(
        [
            {
                "title": "Analyst note on EUR USD",
                "url": "https://dirty.com/call",
                # Trade-call vocabulary in the snippet — MUST be dropped.
                "content": "Strategists say BUY EUR with a TARGET 1.1500 and stop loss below.",
            },
            {
                "title": "Clean macro recap",
                "url": "https://clean.com/recap",
                "content": "The euro firmed against the dollar after the data.",
            },
        ]
    )
    _install_fake_client(monkeypatch, payload)
    out = await fetch_web_research("EUR USD today", limit=6)
    urls = [r.url for r in out]
    assert "https://dirty.com/call" not in urls
    assert urls == ["https://clean.com/recap"]
    # And every surfaced snapshot is ADR-017-clean.
    for r in out:
        assert is_adr017_clean(r.title)
        assert is_adr017_clean(r.snippet)


@pytest.mark.asyncio
async def test_adr017_drops_dirty_title(monkeypatch) -> None:
    payload = _searxng_payload(
        [
            {
                "title": "SELL the rally — EUR USD outlook",
                "url": "https://dirty.com/title",
                "content": "A perfectly clean factual summary of the market.",
            },
            {
                "title": "ECB decision recap",
                "url": "https://clean.com/ecb",
                "content": "Rates held; guidance unchanged.",
            },
        ]
    )
    _install_fake_client(monkeypatch, payload)
    out = await fetch_web_research("EUR USD today", limit=6)
    assert [r.url for r in out] == ["https://clean.com/ecb"]


# ───────────────────────────── fail-open ──────────────────────────────


@pytest.mark.asyncio
async def test_fail_open_on_http_error(monkeypatch) -> None:
    err = httpx.HTTPStatusError("500", request=MagicMock(), response=MagicMock(status_code=500))
    _install_fake_client(monkeypatch, {}, raise_exc=err)
    out = await fetch_web_research("EUR USD today", limit=6)
    assert out == []


@pytest.mark.asyncio
async def test_fail_open_on_transport_error(monkeypatch) -> None:
    _FakeAsyncClient.reset()

    class _BoomClient(_FakeAsyncClient):
        async def get(self, url: str, **kwargs: object) -> _FakeResponse:
            raise httpx.ConnectError("connection refused")

    def _factory(*args: object, **kwargs: object) -> _BoomClient:
        return _BoomClient(_FakeResponse({}))

    monkeypatch.setattr(web_research.httpx, "AsyncClient", _factory)
    out = await fetch_web_research("XAU USD today", limit=6)
    assert out == []


@pytest.mark.asyncio
async def test_fail_open_on_malformed_payload(monkeypatch) -> None:
    # `results` not a list → parsed as [] → returns [].
    _install_fake_client(monkeypatch, {"results": "oops", "number_of_results": 0})
    out = await fetch_web_research("EUR USD today", limit=6)
    assert out == []


@pytest.mark.asyncio
async def test_empty_query_returns_empty(monkeypatch) -> None:
    _install_fake_client(monkeypatch, _searxng_payload([{"title": "x", "url": "https://x.com"}]))
    assert await fetch_web_research("   ", limit=6) == []
    # No HTTP call for an empty query.
    assert len(_FakeAsyncClient.get_calls) == 0


# ──────────────────────────────── cache ───────────────────────────────


@pytest.mark.asyncio
async def test_cache_hit_skips_second_http_call(monkeypatch) -> None:
    payload = _searxng_payload(
        [{"title": "Cached headline", "url": "https://c.com/a", "content": "body"}]
    )
    _install_fake_client(monkeypatch, payload)

    first = await fetch_web_research("EUR USD ECB today", limit=6)
    assert len(_FakeAsyncClient.get_calls) == 1
    assert len(first) == 1

    # Second identical call within TTL → served from cache, no new GET.
    second = await fetch_web_research("eur usd ecb today", limit=6)  # case/ws-insensitive key
    assert len(_FakeAsyncClient.get_calls) == 1  # unchanged
    assert second == first


@pytest.mark.asyncio
async def test_cache_expiry_rehits(monkeypatch) -> None:
    payload = _searxng_payload([{"title": "Headline", "url": "https://c.com/a", "content": "body"}])
    _install_fake_client(monkeypatch, payload)

    await fetch_web_research("GBP USD BoE today", limit=6)
    assert len(_FakeAsyncClient.get_calls) == 1

    # Force the cache entry to look stale (older than TTL).
    key = web_research._cache_key("GBP USD BoE today", 6, None)
    fetched_at, results = web_research._CACHE[key]
    web_research._CACHE[key] = (fetched_at - web_research._CACHE_TTL_SEC - 1, results)

    await fetch_web_research("GBP USD BoE today", limit=6)
    assert len(_FakeAsyncClient.get_calls) == 2  # re-hit after expiry


# ───────────────────────── per-asset query map ────────────────────────


def test_per_asset_query_map_present() -> None:
    # The 6 ADR-083 priority assets each have ≥2 targeted queries.
    for asset in ("EUR_USD", "GBP_USD", "USD_CAD", "XAU_USD", "NAS100_USD", "SPX500_USD"):
        queries = data_pool._WEB_RESEARCH_QUERIES.get(asset)
        assert queries is not None, f"{asset} missing from _WEB_RESEARCH_QUERIES"
        assert len(queries) >= 2, f"{asset} should have ≥2 queries"
        assert all(isinstance(q, str) and q.strip() for q in queries)


def test_per_asset_queries_are_adr017_clean() -> None:
    # The query strings themselves must carry no trade-signal vocabulary.
    for asset, queries in data_pool._WEB_RESEARCH_QUERIES.items():
        for q in queries:
            assert is_adr017_clean(q), f"{asset} query {q!r} trips ADR-017"


# ─────────────────── _section_web_research (data_pool) ─────────────────

_SECTION_PATH = "ichor_api.services.web_research.fetch_web_research"


@pytest.mark.asyncio
async def test_section_honest_absence(monkeypatch) -> None:
    async def _fake(query, **kw):  # noqa: ANN001, ANN002, ANN003
        return []

    monkeypatch.setattr(_SECTION_PATH, _fake)
    md, src = await data_pool._section_web_research(None, "EUR_USD")
    assert "recherche web indisponible" in md.lower()
    assert src == []
    assert is_adr017_clean(md)


@pytest.mark.asyncio
async def test_section_renders_results_with_stamp(monkeypatch) -> None:
    snap = WebResultSnapshot(
        title="ECB holds rates steady",
        url="https://reuters.com/ecb",
        snippet="The ECB kept its policy rate unchanged.",
        engine="google",
        published_at="2026-06-02T08:00:00Z",
        source_domain="reuters.com",
    )

    async def _fake(query, **kw):  # noqa: ANN001, ANN002, ANN003
        return [snap]

    monkeypatch.setattr(_SECTION_PATH, _fake)
    md, src = await data_pool._section_web_research(None, "EUR_USD")
    assert "ECB holds rates steady" in md
    assert "reuters.com" in md
    assert "Recherche web en direct" in md
    # Source-stamp present.
    assert any(s.startswith("web_research:searxng@") for s in src)
    assert "https://reuters.com/ecb" in src
    assert is_adr017_clean(md)


@pytest.mark.asyncio
async def test_section_unknown_asset_not_applicable(monkeypatch) -> None:
    async def _fake(query, **kw):  # noqa: ANN001, ANN002, ANN003
        raise AssertionError("should not query for an asset with no map entry")

    monkeypatch.setattr(_SECTION_PATH, _fake)
    md, src = await data_pool._section_web_research(None, "ZZZ_ZZZ")
    assert "non applicable" in md
    assert src == []
    assert is_adr017_clean(md)


@pytest.mark.asyncio
async def test_section_dedups_across_queries(monkeypatch) -> None:
    # Same URL returned for both EUR_USD queries → collapsed once.
    snap = WebResultSnapshot(
        title="Shared headline",
        url="https://dup.com/x",
        snippet="body",
        engine="google",
        published_at=None,
        source_domain="dup.com",
    )

    async def _fake(query, **kw):  # noqa: ANN001, ANN002, ANN003
        return [snap]

    monkeypatch.setattr(_SECTION_PATH, _fake)
    md, src = await data_pool._section_web_research(None, "EUR_USD")
    # Rendered exactly once across the 2 EUR_USD queries (URL-dedup), and
    # the source URL appears once in the source list (the trailing
    # web_research:searxng@ stamp is a separate entry).
    assert md.count("Shared headline") == 1
    assert src.count("https://dup.com/x") == 1
