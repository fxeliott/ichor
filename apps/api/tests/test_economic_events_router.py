"""Smoke tests for /v1/economic-events router.

Pure routing/validation — uses TestClient + FastAPI dependency override
to inject a fake AsyncSession that records the SQL filters applied.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from ichor_api.db import get_session
from ichor_api.main import app


class _StubResult:
    """Mimic SQLAlchemy Result.scalars().all() chain."""

    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self._rows = rows

    def scalars(self) -> _StubResult:
        return self

    def all(self) -> list[SimpleNamespace]:
        return self._rows


class _StubSession:
    """AsyncSession stub that returns a fixed row set on .execute()."""

    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self._rows = rows
        self.statements: list[object] = []

    async def execute(self, stmt: object) -> _StubResult:
        self.statements.append(stmt)
        return _StubResult(self._rows)


def _make_row(
    *,
    currency: str = "USD",
    title: str = "NFP",
    impact: str = "high",
    forecast: str | None = "180K",
    previous: str | None = "175K",
    scheduled_at: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        currency=currency,
        scheduled_at=scheduled_at or datetime(2026, 5, 8, 12, 30, tzinfo=UTC),
        is_all_day=False,
        title=title,
        impact=impact,
        forecast=forecast,
        previous=previous,
        url="https://www.forexfactory.com/calendar?day=may8.2026#fakeevent1",
        source="forex_factory",
        fetched_at=datetime.now(UTC),
    )


@pytest.fixture
def stub_session() -> _StubSession:
    rows = [
        _make_row(currency="USD", title="NFP", impact="high"),
        _make_row(currency="EUR", title="ECB Press Conference", impact="high"),
        _make_row(currency="GBP", title="Bank Holiday", impact="holiday"),
    ]
    return _StubSession(rows)


@pytest.fixture
def client(stub_session: _StubSession) -> TestClient:
    async def _override():
        yield stub_session

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_default_query_returns_all_rows(client: TestClient) -> None:
    r = client.get("/v1/economic-events")
    assert r.status_code == 200
    body = r.json()
    assert body["n_events"] == 3
    assert {e["currency"] for e in body["events"]} == {"USD", "EUR", "GBP"}
    assert body["window_back_minutes"] == 60
    assert body["window_forward_minutes"] == 60 * 24 * 7


def test_currency_filter_passes_pattern(client: TestClient) -> None:
    r = client.get("/v1/economic-events?currency=USD")
    assert r.status_code == 200


def test_currency_filter_rejects_invalid_pattern(client: TestClient) -> None:
    # 4-letter currency code → pattern fails → 422
    r = client.get("/v1/economic-events?currency=USDD")
    assert r.status_code == 422


def test_impact_filter_validates_literal(client: TestClient) -> None:
    r = client.get("/v1/economic-events?impact=high")
    assert r.status_code == 200
    r = client.get("/v1/economic-events?impact=invalid")
    assert r.status_code == 422


def test_horizon_minutes_clamps_at_max(client: TestClient) -> None:
    # 20160 = 14 days → max
    r = client.get("/v1/economic-events?horizon_minutes=20160")
    assert r.status_code == 200
    r = client.get("/v1/economic-events?horizon_minutes=20161")
    assert r.status_code == 422


def test_limit_validation(client: TestClient) -> None:
    r = client.get("/v1/economic-events?limit=200")
    assert r.status_code == 200
    r = client.get("/v1/economic-events?limit=201")
    assert r.status_code == 422
    r = client.get("/v1/economic-events?limit=0")
    assert r.status_code == 422


def test_response_shape_per_event(client: TestClient) -> None:
    r = client.get("/v1/economic-events?limit=1")
    assert r.status_code == 200
    body = r.json()
    e = body["events"][0]
    assert {"id", "currency", "title", "impact", "scheduled_at", "fetched_at"}.issubset(e.keys())
    # ISO-parse the timestamps
    datetime.fromisoformat(e["fetched_at"])
    datetime.fromisoformat(e["scheduled_at"])
