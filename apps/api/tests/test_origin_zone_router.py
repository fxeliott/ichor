"""r184 frontend endpoint tests — ``GET /v1/origin-zone/{asset}``.

Covers atom-level :
- 200 OK happy path with full OriginZoneOut shape + Pydantic field parity
- 404 honest absence when classifier returns None (no bars OR low-n)
- 422 on malformed asset path param (FastAPI Path constraint)
- Cache-Control: private, no-store header (LIVE state, never cache)
- ``range_observed`` pre-compute correctness
- ``provenance`` field defaults to ``practitioner_stamp`` (Pattern #20)

Mirrors the r161 + r167 router test pattern : FastAPI TestClient +
``app.dependency_overrides[get_session]`` for service-layer mocking ;
no DB hit, no LLM call. Pure pure-fn router wiring verification.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from ichor_api.db import get_session
from ichor_api.routers.origin_zone import router as origin_zone_router
from ichor_api.services.previous_session_origin_zone import OriginZoneSnapshot


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    app.include_router(origin_zone_router)
    app.dependency_overrides[get_session] = lambda: AsyncMock()
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _build_sample_snapshot() -> OriginZoneSnapshot:
    return OriginZoneSnapshot(
        session_zone="ny",
        high_price=1.0875,
        low_price=1.0851,
        direction="up",
        bar_count=420,
        start_utc=datetime(2026, 5, 27, 13, 0, tzinfo=UTC),
        end_utc=datetime(2026, 5, 27, 20, 59, tzinfo=UTC),
    )


class TestOriginZoneRouterHappyPath:
    """200 OK + OriginZoneOut full shape + headers + Pydantic projection."""

    def test_returns_200_with_full_shape_on_populated_snapshot(self, client: TestClient) -> None:
        snapshot = _build_sample_snapshot()
        with patch(
            "ichor_api.routers.origin_zone.compute_previous_session_origin_zone",
            AsyncMock(return_value=snapshot),
        ):
            response = client.get("/v1/origin-zone/EUR_USD")
        assert response.status_code == 200
        body = response.json()
        assert body["asset"] == "EUR_USD"
        assert body["session_zone"] == "ny"
        assert body["direction"] == "up"
        assert body["high_price"] == pytest.approx(1.0875)
        assert body["low_price"] == pytest.approx(1.0851)
        # range_observed pre-computed by _project_snapshot for frontend
        # convenience
        assert body["range_observed"] == pytest.approx(0.0024, abs=1e-6)
        assert body["bar_count"] == 420
        assert body["provenance"] == "practitioner_stamp"
        # computed_at_utc stamped by the router itself
        assert "computed_at_utc" in body

    def test_cache_control_is_no_store(self, client: TestClient) -> None:
        """LIVE state — Cache-Control: private, no-store header set
        per ``<FreshDataBanner>`` r140 + r161 verdict endpoint pattern."""
        snapshot = _build_sample_snapshot()
        with patch(
            "ichor_api.routers.origin_zone.compute_previous_session_origin_zone",
            AsyncMock(return_value=snapshot),
        ):
            response = client.get("/v1/origin-zone/EUR_USD")
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "private, no-store"

    def test_each_priority_asset_path_param_accepted(self, client: TestClient) -> None:
        """All 5 priority assets EUR_USD/GBP_USD/XAU_USD/SPX500_USD/NAS100_USD
        match the Path regex ``^[A-Z0-9]{3,8}_[A-Z]{3,8}$``."""
        snapshot = _build_sample_snapshot()
        for asset in (
            "EUR_USD",
            "GBP_USD",
            "XAU_USD",
            "SPX500_USD",
            "NAS100_USD",
        ):
            with patch(
                "ichor_api.routers.origin_zone.compute_previous_session_origin_zone",
                AsyncMock(return_value=snapshot),
            ):
                response = client.get(f"/v1/origin-zone/{asset}")
            assert response.status_code == 200, f"asset={asset} failed"
            assert response.json()["asset"] == asset


class TestOriginZoneRouterHonestAbsence:
    """404 when classifier returns None — doctrine #11 calibrated honesty."""

    def test_returns_404_when_classifier_returns_none(self, client: TestClient) -> None:
        """No bars in window OR dominant zone bar_count < 30 → 404."""
        with patch(
            "ichor_api.routers.origin_zone.compute_previous_session_origin_zone",
            AsyncMock(return_value=None),
        ):
            response = client.get("/v1/origin-zone/EUR_USD")
        assert response.status_code == 404
        detail = response.json()["detail"]
        assert "Cohen 1988" in detail
        assert "doctrine #11" in detail


class TestOriginZoneRouterValidation:
    """422 on malformed asset path param."""

    def test_returns_422_on_lowercase_asset(self, client: TestClient) -> None:
        """Path regex is uppercase-only by design (asset codes are
        always upper). Lowercase rejected at validation layer."""
        response = client.get("/v1/origin-zone/eur_usd")
        assert response.status_code == 422

    def test_returns_422_on_special_chars(self, client: TestClient) -> None:
        """Path regex rejects special chars (e.g., spaces, slashes)."""
        response = client.get("/v1/origin-zone/EUR-USD")
        assert response.status_code == 422


class TestOriginZoneOutPydanticSurface:
    """The Pydantic ``OriginZoneOut`` projection itself is verifier-
    friendly (frozen, extra=forbid, ge constraints)."""

    def test_origin_zone_out_is_frozen(self) -> None:
        """Mirror of r174 OriginZoneSnapshot frozen dataclass + r161
        SessionVerdict frozen Pydantic discipline."""
        from ichor_api.routers.origin_zone import OriginZoneOut

        assert OriginZoneOut.model_config.get("frozen") is True

    def test_origin_zone_out_forbids_extra_fields(self) -> None:
        """``extra='forbid'`` ensures forward-compat for r185+ frontend
        lockstep CI guard."""
        from ichor_api.routers.origin_zone import OriginZoneOut

        assert OriginZoneOut.model_config.get("extra") == "forbid"
