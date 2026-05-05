"""Smoke tests for /v1/today aggregator router.

Mocks the underlying services (assess_vix_term, assess_risk_appetite,
assess_funding_stress, assess_calendar) and the SessionCardAudit query
so we exercise the router's serialization + filtering logic without
requiring a live DB.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from ichor_api.db import get_session
from ichor_api.main import app
from ichor_api.routers import today as today_router
from ichor_api.services.economic_calendar import CalendarEvent, CalendarReport


def _macro_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wire the three macro service mocks with realistic shapes."""
    vix = SimpleNamespace(
        vix_1m=18.4,
        vix_3m=19.8,
        ratio=0.93,
        spread=1.4,
        regime="contango",
        interpretation="calm regime — short-vol bias OK",
    )
    risk = SimpleNamespace(
        composite=0.42,
        band="risk_on",
        components=[],
    )
    fs = SimpleNamespace(
        sofr=4.92,
        iorb=4.84,
        sofr_iorb_spread=8.0,
        sofr_effr_spread=2.0,
        rrp_usage=120.5,
        hy_oas=312.0,
        stress_score=0.18,
    )
    monkeypatch.setattr(today_router, "assess_vix_term", AsyncMock(return_value=vix))
    monkeypatch.setattr(today_router, "assess_risk_appetite", AsyncMock(return_value=risk))
    monkeypatch.setattr(today_router, "assess_funding_stress", AsyncMock(return_value=fs))


def _calendar_stub(*, events: list[CalendarEvent] | None = None):
    rep = CalendarReport(
        generated_at=datetime.now(UTC),
        horizon_days=2,
        events=events or [],
    )
    return AsyncMock(return_value=rep)


class _StubResult:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def scalars(self) -> _StubResult:
        return self

    def all(self) -> list:
        return self._rows


class _StubSession:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    async def execute(self, stmt: object) -> _StubResult:
        return _StubResult(self._rows)


def _card(
    *,
    asset: str = "EUR_USD",
    bias: str = "long",
    conviction: float = 72.0,
    generated: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        asset=asset,
        bias_direction=bias,
        conviction_pct=conviction,
        magnitude_pips_low=18.0,
        magnitude_pips_high=32.0,
        regime_quadrant="goldilocks",
        generated_at=generated or datetime(2026, 5, 4, 7, 0, tzinfo=UTC),
    )


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    _macro_stubs(monkeypatch)
    monkeypatch.setattr(today_router, "assess_calendar", _calendar_stub())

    rows = [_card()]

    async def _override():
        yield _StubSession(rows)

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_today_returns_200_and_full_shape(client: TestClient) -> None:
    r = client.get("/v1/today")
    assert r.status_code == 200
    body = r.json()
    # Top-level keys
    assert {
        "generated_at",
        "macro",
        "calendar_window_days",
        "n_calendar_events",
        "calendar_events",
        "n_session_cards",
        "top_sessions",
    }.issubset(body.keys())


def test_today_macro_summary_shape(client: TestClient) -> None:
    r = client.get("/v1/today")
    macro = r.json()["macro"]
    assert macro["risk_composite"] == pytest.approx(0.42)
    assert macro["risk_band"] == "risk_on"
    assert macro["funding_stress"] == pytest.approx(0.18)
    assert macro["vix_regime"] == "contango"
    assert macro["vix_1m"] == pytest.approx(18.4)


def test_today_session_serialization(client: TestClient) -> None:
    r = client.get("/v1/today")
    body = r.json()
    assert body["n_session_cards"] == 1
    s = body["top_sessions"][0]
    assert s["asset"] == "EUR_USD"
    assert s["bias_direction"] == "long"
    assert s["conviction_pct"] == pytest.approx(72.0)
    assert s["magnitude_pips_low"] == pytest.approx(18.0)
    assert s["regime_quadrant"] == "goldilocks"


def test_today_horizon_days_validation(client: TestClient) -> None:
    r = client.get("/v1/today?horizon_days=0")
    assert r.status_code == 422
    r = client.get("/v1/today?horizon_days=15")
    assert r.status_code == 422


def test_today_top_n_validation(client: TestClient) -> None:
    r = client.get("/v1/today?top_n=0")
    assert r.status_code == 422
    r = client.get("/v1/today?top_n=9")
    assert r.status_code == 422
    r = client.get("/v1/today?top_n=8")
    assert r.status_code == 200


def test_today_calendar_filters_low_impact(monkeypatch: pytest.MonkeyPatch) -> None:
    _macro_stubs(monkeypatch)
    events = [
        CalendarEvent(
            when=date(2026, 5, 7),
            when_time_utc="13:30",
            region="US",
            label="High-impact NFP",
            impact="high",
            affected_assets=["EUR_USD"],
            note="forecast=180K",
            source="forex_factory",
        ),
        CalendarEvent(
            when=date(2026, 5, 7),
            when_time_utc="14:00",
            region="US",
            label="Low-impact filler",
            impact="low",
            affected_assets=[],
            note="",
            source="static",
        ),
        CalendarEvent(
            when=date(2026, 5, 7),
            when_time_utc="15:00",
            region="EU",
            label="Medium ECB minutes",
            impact="medium",
            affected_assets=["EUR_USD"],
            note="",
            source="static",
        ),
    ]
    monkeypatch.setattr(today_router, "assess_calendar", _calendar_stub(events=events))

    async def _override():
        yield _StubSession([])

    app.dependency_overrides[get_session] = _override
    try:
        with TestClient(app) as c:
            r = c.get("/v1/today")
            assert r.status_code == 200
            body = r.json()
            # Low-impact filtered out, medium + high kept
            assert body["n_calendar_events"] == 2
            labels = {e["label"] for e in body["calendar_events"]}
            assert "High-impact NFP" in labels
            assert "Medium ECB minutes" in labels
            assert "Low-impact filler" not in labels
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_today_top_sessions_distinct_per_asset_newest_wins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Service emits DISTINCT ON (asset) so the stub already returns one
    row per asset ; the router then sorts by generated_at desc and slices
    to top_n."""
    _macro_stubs(monkeypatch)
    monkeypatch.setattr(today_router, "assess_calendar", _calendar_stub())

    rows = [
        _card(asset="EUR_USD", generated=datetime(2026, 5, 4, 7, 0, tzinfo=UTC)),
        _card(asset="USD_JPY", generated=datetime(2026, 5, 4, 7, 30, tzinfo=UTC)),
        _card(asset="XAU_USD", generated=datetime(2026, 5, 4, 7, 15, tzinfo=UTC)),
        _card(asset="GBP_USD", generated=datetime(2026, 5, 4, 6, 45, tzinfo=UTC)),
    ]

    async def _override():
        yield _StubSession(rows)

    app.dependency_overrides[get_session] = _override
    try:
        with TestClient(app) as c:
            r = c.get("/v1/today?top_n=3")
            body = r.json()
            assert body["n_session_cards"] == 4
            assert len(body["top_sessions"]) == 3
            # Sorted newest-first ; USD_JPY (07:30) is the freshest
            assert body["top_sessions"][0]["asset"] == "USD_JPY"
    finally:
        app.dependency_overrides.pop(get_session, None)
