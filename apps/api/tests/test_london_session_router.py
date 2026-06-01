"""§6.2 frontend endpoint tests — ``GET /v1/london-session/{asset}``.

Covers atom-level :
- 200 OK happy path with full LondonSessionOut shape + Pydantic field parity
- 404 honest absence when the read is None (no London bars OR low-n window)
- 422 on malformed asset path param (FastAPI Path constraint)
- Cache-Control: private, no-store header (LIVE state, never cache)
- ``range_ratio`` / ``avg_range`` nullable when no prior-window baseline
- ``provenance`` defaults to ``practitioner_stamp``

Mirrors the r184 origin-zone router test : FastAPI TestClient +
``app.dependency_overrides[get_session]`` for service-layer mocking ; no DB
hit, no LLM call. Pure router-wiring verification.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from ichor_api.db import get_session
from ichor_api.routers.london_session import router as london_session_router
from ichor_api.services.london_session import LondonSessionRead


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    app.include_router(london_session_router)
    app.dependency_overrides[get_session] = lambda: AsyncMock()
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _build_sample_read(*, with_baseline: bool = True) -> LondonSessionRead:
    return LondonSessionRead(
        session_date=date(2026, 6, 1),
        open_price=1.0840,
        high=1.0875,
        low=1.0832,
        close=1.0868,
        range_abs=0.0043,
        net_change=0.0028,
        direction="up",
        bar_count=210,
        avg_range=0.0031 if with_baseline else None,
        range_ratio=1.39 if with_baseline else None,
        is_today=True,
    )


class TestLondonSessionRouterHappyPath:
    """200 OK + LondonSessionOut full shape + headers + Pydantic projection."""

    def test_returns_200_with_full_shape(self, client: TestClient) -> None:
        read = _build_sample_read()
        with patch(
            "ichor_api.routers.london_session.compute_london_session_for_asset",
            AsyncMock(return_value=read),
        ):
            response = client.get("/v1/london-session/EUR_USD")
        assert response.status_code == 200
        body = response.json()
        assert body["asset"] == "EUR_USD"
        assert body["session_date"] == "2026-06-01"
        assert body["is_today"] is True
        assert body["direction"] == "up"
        assert body["open_price"] == pytest.approx(1.0840)
        assert body["close"] == pytest.approx(1.0868)
        assert body["high"] == pytest.approx(1.0875)
        assert body["low"] == pytest.approx(1.0832)
        assert body["range_abs"] == pytest.approx(0.0043)
        assert body["net_change"] == pytest.approx(0.0028)
        assert body["bar_count"] == 210
        assert body["range_ratio"] == pytest.approx(1.39)
        assert body["avg_range"] == pytest.approx(0.0031)
        assert body["provenance"] == "practitioner_stamp"
        # computed_at_utc stamped by the router itself
        assert "computed_at_utc" in body

    def test_null_baseline_ratio_serialises_as_null(self, client: TestClient) -> None:
        """Early in the week (no prior London windows yet) avg_range and
        range_ratio are None — honest, not fabricated 1.0."""
        read = _build_sample_read(with_baseline=False)
        with patch(
            "ichor_api.routers.london_session.compute_london_session_for_asset",
            AsyncMock(return_value=read),
        ):
            response = client.get("/v1/london-session/XAU_USD")
        assert response.status_code == 200
        body = response.json()
        assert body["avg_range"] is None
        assert body["range_ratio"] is None

    def test_cache_control_is_no_store(self, client: TestClient) -> None:
        read = _build_sample_read()
        with patch(
            "ichor_api.routers.london_session.compute_london_session_for_asset",
            AsyncMock(return_value=read),
        ):
            response = client.get("/v1/london-session/EUR_USD")
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "private, no-store"

    def test_each_priority_asset_path_param_accepted(self, client: TestClient) -> None:
        read = _build_sample_read()
        for asset in ("EUR_USD", "GBP_USD", "XAU_USD", "SPX500_USD", "NAS100_USD"):
            with patch(
                "ichor_api.routers.london_session.compute_london_session_for_asset",
                AsyncMock(return_value=read),
            ):
                response = client.get(f"/v1/london-session/{asset}")
            assert response.status_code == 200, f"asset={asset} failed"
            assert response.json()["asset"] == asset


class TestLondonSessionRouterHonestAbsence:
    """404 when the read is None — doctrine #11 calibrated honesty."""

    def test_returns_404_when_read_is_none(self, client: TestClient) -> None:
        with patch(
            "ichor_api.routers.london_session.compute_london_session_for_asset",
            AsyncMock(return_value=None),
        ):
            response = client.get("/v1/london-session/EUR_USD")
        assert response.status_code == 404
        assert "doctrine #11" in response.json()["detail"]


class TestLondonSessionRouterValidation:
    """422 on malformed asset path param."""

    def test_returns_422_on_lowercase_asset(self, client: TestClient) -> None:
        response = client.get("/v1/london-session/eur_usd")
        assert response.status_code == 422

    def test_returns_422_on_special_chars(self, client: TestClient) -> None:
        response = client.get("/v1/london-session/EUR-USD")
        assert response.status_code == 422


class TestLondonSessionOutPydanticSurface:
    """The Pydantic ``LondonSessionOut`` projection is verifier-friendly."""

    def test_london_session_out_is_frozen(self) -> None:
        from ichor_api.routers.london_session import LondonSessionOut

        assert LondonSessionOut.model_config.get("frozen") is True

    def test_london_session_out_forbids_extra_fields(self) -> None:
        from ichor_api.routers.london_session import LondonSessionOut

        assert LondonSessionOut.model_config.get("extra") == "forbid"
