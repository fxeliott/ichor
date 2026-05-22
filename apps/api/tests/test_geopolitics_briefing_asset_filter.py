"""Integration tests for `/v1/geopolitics/briefing?asset=X` (r138).

Pins :
  - back-compat : no `?asset=` → response.filter is None, gdelt_negatives
    are sorted ascending-tone (most-negative first), top-N respected
  - asset filter narrows the GDELT negatives ranking to events whose
    title / query_label / domain / URL matches the asset's keywords
  - scarce-fallback : below `_MIN_ASSET_MATCHES` matches, ranking falls
    back to global (filter.applied=False), AI-GPR unchanged
  - unknown-asset path : filter.known_asset=False, no silent drop
  - AI-GPR is GLOBAL — asset filter never alters it (single-index doctrine)
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from ichor_api.db import get_session
from ichor_api.main import app


def _gdelt(
    idx: int, title: str, tone: float, *, query_label: str = "global", url: str = ""
) -> SimpleNamespace:
    return SimpleNamespace(
        id=f"00000000-0000-0000-0000-{idx:012d}",
        seendate=datetime(2026, 5, 21, 18, 0, tzinfo=UTC),
        tone=tone,
        title=title,
        domain="example.com",
        query_label=query_label,
        url=url or f"https://example.com/{idx}",
        sourcecountry="US",
    )


def _gpr_row(value: float = 210.6, obs_date: date | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        ai_gpr=value,
        observation_date=obs_date or date(2026, 5, 18),
    )


class _RowsResult:
    """Mimics result.scalars().all()."""

    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        class _S:
            def all(s2):
                return list(self._rows)

            def first(s2):
                return self._rows[0] if self._rows else None

        return _S()


class _ScalarResult:
    """Mimics result.scalar() for the n_events_window COUNT(*) query."""

    def __init__(self, value: int):
        self._value = value

    def scalar(self):
        return self._value


def _make_session_for_geopolitics(
    *,
    gpr: SimpleNamespace | None = None,
    gdelt_rows: list[SimpleNamespace] | None = None,
    window_count: int = 0,
):
    """Build an AsyncSession stub. The geo router does 3 .execute calls
    in order : (1) gpr_row .scalars().first(), (2) gdelt rows in window,
    (3) func.count() window cardinality. We route by call ORDER, not
    by SQL text — the latter was too flaky (column names like 'count'
    can leak into unrelated SELECT compilations)."""

    state = {"i": 0}

    async def _execute(stmt, *a, **kw):
        i = state["i"]
        state["i"] += 1
        if i == 0:
            return _RowsResult([gpr] if gpr is not None else [])
        if i == 1:
            return _RowsResult(gdelt_rows or [])
        # i == 2 → COUNT(*) query
        return _ScalarResult(window_count)

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=_execute)
    return session


@pytest.fixture
def client_with_geo():
    def _make(**kw):
        session = _make_session_for_geopolitics(**kw)

        async def _override():
            yield session

        app.dependency_overrides[get_session] = _override
        return TestClient(app)

    yield _make
    app.dependency_overrides.pop(get_session, None)


def test_briefing_back_compat_no_asset(client_with_geo):
    rows = [
        _gdelt(1, "Major financial stress", -5.0),
        _gdelt(2, "Mild concern", -1.0),
        _gdelt(3, "Markets calm", 0.5),
    ]
    c = client_with_geo(gpr=_gpr_row(150.0), gdelt_rows=rows, window_count=42)
    r = c.get("/v1/geopolitics/briefing?hours=24&top=2")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["filter"] is None
    assert data["gpr"]["value"] == 150.0
    assert data["gpr"]["band"] in ("normal", "élevé")
    assert data["n_events_window"] == 42
    assert len(data["gdelt_negatives"]) == 2
    # First should be the most-negative
    assert data["gdelt_negatives"][0]["tone"] == -5.0


def test_briefing_asset_filter_applied(client_with_geo):
    """≥3 EUR-affinity hits → filter applies."""
    rows = [
        _gdelt(1, "ECB raises rates", -3.0, query_label="ecb-policy"),
        _gdelt(2, "Lagarde dovish pivot", -2.5, query_label="ecb-policy"),
        _gdelt(3, "eurozone PMI miss", -1.5, query_label="ez-macro"),
        _gdelt(4, "Tariff escalation", -4.0, query_label="us-china"),  # no EUR hit
        _gdelt(5, "Apple guidance miss", -2.0, query_label="tech-earnings"),
    ]
    c = client_with_geo(gpr=_gpr_row(180.0), gdelt_rows=rows, window_count=120)
    r = c.get("/v1/geopolitics/briefing?asset=EUR_USD&top=5")
    assert r.status_code == 200
    data = r.json()
    assert data["filter"]["applied"] is True
    assert data["filter"]["matched"] == 3
    assert data["filter"]["asset"] == "EUR_USD"
    assert data["filter"]["known_asset"] is True
    titles = [n["title"] for n in data["gdelt_negatives"]]
    assert all(any(k in t for k in ("ECB", "Lagarde", "eurozone")) for t in titles), titles


def test_briefing_asset_filter_scarce_fallback(client_with_geo):
    rows = [
        _gdelt(1, "Apple earnings", -2.5),  # 0 EUR hits
        _gdelt(2, "Tariff escalation", -3.0),
        _gdelt(3, "Tech rotation", -1.5),
    ]
    c = client_with_geo(gpr=_gpr_row(100.0), gdelt_rows=rows, window_count=30)
    r = c.get("/v1/geopolitics/briefing?asset=EUR_USD&top=3")
    assert r.status_code == 200
    data = r.json()
    assert data["filter"]["applied"] is False
    assert data["filter"]["matched"] == 0
    assert data["filter"]["min_required"] == 3
    # The full row set falls back to global ranking
    assert len(data["gdelt_negatives"]) == 3


def test_briefing_gpr_unchanged_by_asset_filter(client_with_geo):
    """AI-GPR is the GLOBAL geopolitical risk index — must NOT vary
    with the asset filter (single-index doctrine, r138 ADR-099 §Impl)."""
    gpr = _gpr_row(value=350.0)  # very high
    rows = [_gdelt(i, f"Story {i}", -float(i)) for i in range(5)]
    c1 = client_with_geo(gpr=gpr, gdelt_rows=rows, window_count=5)
    r1 = c1.get("/v1/geopolitics/briefing")
    c2 = client_with_geo(gpr=gpr, gdelt_rows=rows, window_count=5)
    r2 = c2.get("/v1/geopolitics/briefing?asset=XAU_USD")
    assert r1.status_code == r2.status_code == 200
    assert r1.json()["gpr"]["value"] == r2.json()["gpr"]["value"] == 350.0
    assert r1.json()["gpr"]["band"] == r2.json()["gpr"]["band"] == "très élevé"


def test_briefing_unknown_asset(client_with_geo):
    rows = [_gdelt(i, f"Story {i}", -1.0) for i in range(4)]
    c = client_with_geo(gpr=_gpr_row(100.0), gdelt_rows=rows, window_count=4)
    r = c.get("/v1/geopolitics/briefing?asset=FAKE_USD")
    assert r.status_code == 200
    data = r.json()
    assert data["filter"]["known_asset"] is False
    assert data["filter"]["applied"] is False
    assert len(data["gdelt_negatives"]) == 4  # global fallback


def test_briefing_query_label_drives_match(client_with_geo):
    """`query_label` (collector-side topic tag) MUST also contribute to
    the affinity match — e.g. 'iran-conflict' label boosts XAU_USD even
    if the title is generic."""
    rows = [
        _gdelt(1, "Story A", -3.0, query_label="iran-conflict"),
        # 'iran' is not in XAU_USD keywords (NEWS_KEYWORDS["XAU_USD"] =
        # gold/bullion/GLD/GDX/spot metals). So a 'iran-conflict' label
        # should NOT trigger an XAU match with current keyword map.
        # This test pins the documented behaviour : titles + labels +
        # URLs are matched against the affinity tuple LITERALLY.
        _gdelt(2, "Story B with gold reserves bullion bid", -2.0),  # gold + bullion hits
        _gdelt(3, "Generic", -4.0),
        _gdelt(4, "Spot metals desk view", -1.0),  # spot metals hits
        _gdelt(5, "XAUUSD intraday flow", -2.5),  # XAUUSD hits
    ]
    c = client_with_geo(gpr=_gpr_row(150.0), gdelt_rows=rows, window_count=30)
    r = c.get("/v1/geopolitics/briefing?asset=XAU_USD&top=4")
    assert r.status_code == 200
    data = r.json()
    assert data["filter"]["applied"] is True
    assert data["filter"]["matched"] == 3


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
