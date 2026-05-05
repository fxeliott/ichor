"""Smoke tests for the /v1/scenarios/{asset} router.

Pure routing/validation tests — the underlying empirical model is
already covered in test_session_scenarios. We assert :
  - asset slug normalization + 400 on unknown
  - session_type validation
  - response shape (3 scenarios, sums≈1, kind tags)
  - graceful neutral fallback when DailyLevels has no spot

Uses a stub AsyncSession so we don't need a real DB.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from ichor_api.main import app
from ichor_api.routers import scenarios as scenarios_router
from ichor_api.services.daily_levels import DailyLevels


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _stub_levels(asset: str = "EUR_USD", spot: float | None = 1.0855) -> DailyLevels:
    """Build a DailyLevels with all required levels populated by default."""
    return DailyLevels(
        asset=asset,
        spot=spot,
        pdh=1.0890,
        pdl=1.0815,
        pd_close=1.0840,
        asian_high=1.0865,
        asian_low=1.0825,
        weekly_high=1.0950,
        weekly_low=1.0780,
        pivot=1.0848,
        r1=1.0890,
        r2=1.0930,
        r3=1.0970,
        s1=1.0810,
        s2=1.0770,
        s3=1.0730,
        round_levels=[1.0700, 1.0800, 1.0900, 1.1000],
    )


def test_unknown_asset_returns_400(client: TestClient) -> None:
    r = client.get("/v1/scenarios/UNKNOWN")
    assert r.status_code == 400
    assert "unknown asset" in r.json()["detail"].lower()


def test_invalid_session_type_returns_422(client: TestClient) -> None:
    """FastAPI Query() with Literal validates before our handler runs → 422."""
    r = client.get("/v1/scenarios/EUR_USD?session_type=bogus")
    assert r.status_code == 422


def test_normalizes_asset_slug_dashes(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        scenarios_router,
        "assess_daily_levels",
        AsyncMock(return_value=_stub_levels("EUR_USD")),
    )
    monkeypatch.setattr(scenarios_router, "_latest_card", AsyncMock(return_value=None))
    r = client.get("/v1/scenarios/eur-usd")
    assert r.status_code == 200
    assert r.json()["asset"] == "EUR_USD"


def test_response_shape_with_full_levels(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        scenarios_router,
        "assess_daily_levels",
        AsyncMock(return_value=_stub_levels()),
    )
    monkeypatch.setattr(scenarios_router, "_latest_card", AsyncMock(return_value=None))
    r = client.get("/v1/scenarios/EUR_USD?session_type=pre_londres")
    assert r.status_code == 200
    body = r.json()

    assert body["asset"] == "EUR_USD"
    assert body["session_type"] == "pre_londres"
    assert "caller_default" in body["sources"]
    assert body.get("rationale")
    assert body["levels"]["spot"] == pytest.approx(1.0855)

    kinds = [s["kind"] for s in body["scenarios"]]
    assert kinds == ["continuation", "reversal", "sideways"]

    probs = [s["probability"] for s in body["scenarios"]]
    assert all(0.0 <= p <= 1.0 for p in probs)
    assert sum(probs) == pytest.approx(1.0, abs=0.02)

    # generated_at should ISO-parse
    datetime.fromisoformat(body["generated_at"])


def test_neutral_fallback_when_no_spot(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        scenarios_router,
        "assess_daily_levels",
        AsyncMock(return_value=_stub_levels(spot=None)),
    )
    monkeypatch.setattr(scenarios_router, "_latest_card", AsyncMock(return_value=None))
    r = client.get("/v1/scenarios/EUR_USD")
    assert r.status_code == 200
    body = r.json()
    probs = sorted(s["probability"] for s in body["scenarios"])
    # Service returns 0.34/0.33/0.33 when spot is None.
    assert probs == [pytest.approx(0.33), pytest.approx(0.33), pytest.approx(0.34)]
    assert any("Insufficient" in n for n in body["notes"])


def test_caller_overrides_regime_and_conviction(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        scenarios_router,
        "assess_daily_levels",
        AsyncMock(return_value=_stub_levels()),
    )
    monkeypatch.setattr(scenarios_router, "_latest_card", AsyncMock(return_value=None))
    r = client.get("/v1/scenarios/EUR_USD?regime=funding_stress&conviction_pct=85")
    assert r.status_code == 200
    body = r.json()
    assert body["regime"] == "funding_stress"
    assert body["conviction_pct"] == pytest.approx(85.0)


def test_conviction_pct_out_of_range_returns_422(client: TestClient) -> None:
    r = client.get("/v1/scenarios/EUR_USD?conviction_pct=150")
    assert r.status_code == 422
    r = client.get("/v1/scenarios/EUR_USD?conviction_pct=-1")
    assert r.status_code == 422
