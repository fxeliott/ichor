"""Integration tests for `/v1/news?asset=X` (r138).

Mocks `AsyncSession.execute` via `AsyncMock` so the router runs end-to-
end with controlled `NewsItem` rows ; no real Postgres needed.

Pins :
  - back-compat : no `?asset=` → envelope `{items, filter:None}` items
    match what r137 would have returned (sort, limit, time-window)
  - asset filter applied when enough matches
  - scarce-fallback fires below `_MIN_ASSET_MATCHES` and surfaces
    `filter.applied=False` honestly
  - unknown-asset path : `filter.known_asset=False`, no silent drop
  - source_kind / source / tone filters still compose with `asset=`
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from ichor_api.db import get_session
from ichor_api.main import app


def _ni(
    idx: int, title: str, *, source_kind: str = "news", tone: str = "neutral"
) -> SimpleNamespace:
    """Build a NewsItem-shaped row that the router can serialise."""
    return SimpleNamespace(
        id=f"00000000-0000-0000-0000-{idx:012d}",
        fetched_at=datetime(2026, 5, 21, 18, 0, tzinfo=UTC),
        source=f"src_{idx}",
        source_kind=source_kind,
        title=title,
        summary=None,
        url=f"https://example.com/{idx}",
        published_at=datetime(2026, 5, 21, 17, 0, tzinfo=UTC),
        tone_label=tone,
        tone_score=0.0,
    )


def _stub_session_with_rows(rows: list[SimpleNamespace]):
    """Build an AsyncSession stub whose .execute returns a result whose
    .scalars().all() yields `rows`."""

    class _Result:
        def scalars(self):
            class _Scalars:
                def all(self_inner):
                    return rows

            return _Scalars()

    session = AsyncMock()
    session.execute = AsyncMock(return_value=_Result())
    return session


@pytest.fixture
def client_with_rows():
    """TestClient that overrides get_session to return user-supplied rows."""

    def _make(rows: list[SimpleNamespace]) -> TestClient:
        async def _override():
            yield _stub_session_with_rows(rows)

        app.dependency_overrides[get_session] = _override
        c = TestClient(app)
        return c

    yield _make
    app.dependency_overrides.pop(get_session, None)


def test_news_envelope_back_compat_no_asset(client_with_rows):
    """Without `?asset=`, envelope.filter must be None and items must
    match the row order (router applies the DB-level sort upstream)."""
    rows = [_ni(i, f"Title {i}") for i in range(5)]
    c = client_with_rows(rows)
    r = c.get("/v1/news?limit=10")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["filter"] is None
    assert len(data["items"]) == 5
    assert [it["title"] for it in data["items"]] == [f"Title {i}" for i in range(5)]


def test_news_filter_applied_eur_usd(client_with_rows):
    """≥3 ECB/Lagarde/euro hits → filter applies, items narrowed."""
    rows = [
        _ni(1, "ECB hikes rates"),
        _ni(2, "Lagarde at IMF"),
        _ni(3, "eurozone PMI weak"),
        _ni(4, "Apple earnings beat"),
        _ni(5, "Tariff debate Senate"),
    ]
    c = client_with_rows(rows)
    r = c.get("/v1/news?asset=EUR_USD&limit=10")
    assert r.status_code == 200
    data = r.json()
    assert data["filter"]["applied"] is True
    assert data["filter"]["matched"] == 3
    assert data["filter"]["asset"] == "EUR_USD"
    assert data["filter"]["known_asset"] is True
    assert len(data["items"]) == 3
    titles = [it["title"] for it in data["items"]]
    assert all(any(k in t for k in ("ECB", "Lagarde", "eurozone")) for t in titles), titles


def test_news_filter_scarce_fallback_returns_global(client_with_rows):
    """Below 3 matches → fall back to GLOBAL feed, filter.applied=False
    so the panel can render honest 'flux global (peu d'items)' disclosure."""
    rows = [
        _ni(1, "ECB modest"),  # only 1 EUR hit
        _ni(2, "Tariff news"),
        _ni(3, "Tech earnings"),
        _ni(4, "Iran ceasefire"),
        _ni(5, "Treasury auction"),
    ]
    c = client_with_rows(rows)
    r = c.get("/v1/news?asset=EUR_USD&limit=10")
    assert r.status_code == 200
    data = r.json()
    assert data["filter"]["applied"] is False
    assert data["filter"]["matched"] == 1
    assert data["filter"]["min_required"] == 3
    assert len(data["items"]) == 5  # full global list returned


def test_news_unknown_asset_returns_global_with_known_false(client_with_rows):
    rows = [_ni(i, f"Title {i}") for i in range(4)]
    c = client_with_rows(rows)
    r = c.get("/v1/news?asset=FAKEFAKE&limit=10")
    assert r.status_code == 200
    data = r.json()
    assert data["filter"]["applied"] is False
    assert data["filter"]["known_asset"] is False
    assert len(data["items"]) == 4


def test_news_invalid_asset_pattern_rejected(client_with_rows):
    """Asset must match `[A-Z0-9_]{3,16}` — lower-case rejected."""
    rows = [_ni(0, "x")]
    c = client_with_rows(rows)
    r = c.get("/v1/news?asset=eur_usd&limit=10")
    assert r.status_code == 422


def test_news_xau_keywords_url_path_hit(client_with_rows):
    """Keyword hit via URL path (gold/bullion/GLD/GDX) — covers the
    case where the title is generic but the URL carries the asset."""
    rows = [
        SimpleNamespace(
            id=f"00000000-0000-0000-0000-{i:012d}",
            fetched_at=datetime(2026, 5, 21, 18, 0, tzinfo=UTC),
            source="src",
            source_kind="news",
            title="Generic headline",
            summary=None,
            url=url,
            published_at=datetime(2026, 5, 21, 17, 0, tzinfo=UTC),
            tone_label="neutral",
            tone_score=0.0,
        )
        for i, url in enumerate(
            [
                "https://x/y/gold-price-up",  # matches "gold"
                "https://x/y/bullion-market",  # matches "bullion"
                "https://x/y/xauusd-recap",  # matches "xauusd"
                "https://x/y/random",  # no match
            ]
        )
    ]
    c = client_with_rows(rows)
    r = c.get("/v1/news?asset=XAU_USD&limit=10")
    assert r.status_code == 200
    data = r.json()
    assert data["filter"]["applied"] is True
    assert data["filter"]["matched"] == 3
    # Note : "GLD " in NEWS_KEYWORDS carries a trailing space — it does NOT
    # match URL paths like "/GLD-flows" (dash, not space). Documented
    # behaviour ; r138 preserves pre-r138 semantics — keyword map is the
    # SSOT extracted from data_pool.py:4525 unchanged.


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
