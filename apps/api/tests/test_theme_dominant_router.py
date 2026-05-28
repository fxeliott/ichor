"""r185 frontend endpoint tests — ``GET /v1/theme-dominant``."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from ichor_api.db import get_session
from ichor_api.routers.theme_dominant import router as theme_dominant_router
from ichor_api.services.theme_classifier import THEME_DRIVERS, ThemeRanking


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    app.include_router(theme_dominant_router)
    app.dependency_overrides[get_session] = lambda: AsyncMock()
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _build_sample_ranking() -> ThemeRanking:
    """Build a fully-populated ranking — geopolitics dominates
    (mirror Eliot Fathom transcript example) + 2 secondaries."""
    return ThemeRanking(
        top_theme="geopolitics",
        secondary_themes=["fiscal_policy", "market_interconnexions"],
        driver_strengths={
            "macroeconomic": 0.2,
            "monetary_policy": 0.2,
            "economic_data": 0.2,
            "fiscal_policy": 0.55,
            "market_interconnexions": 0.45,
            "geopolitics": 0.75,
            "price_action_flow": 0.2,
            "supply_demand": 0.2,
        },
        computed_at_utc=datetime(2026, 5, 28, 13, 0, tzinfo=UTC),
    )


class TestThemeDominantRouterHappyPath:
    """200 OK + ThemeDominantOut full shape + headers + projection."""

    def test_returns_200_with_full_shape_on_populated_ranking(self, client: TestClient) -> None:
        ranking = _build_sample_ranking()
        with patch(
            "ichor_api.routers.theme_dominant.classify_dominant_theme",
            AsyncMock(return_value=ranking),
        ):
            response = client.get("/v1/theme-dominant")
        assert response.status_code == 200
        body = response.json()
        assert body["top_theme"] == "geopolitics"
        # 0.75 × 100 rounded = 75
        assert body["top_theme_strength_pct"] == 75
        assert body["secondary_themes"] == [
            "fiscal_policy",
            "market_interconnexions",
        ]
        # All 8 drivers present in percentage dict — even baselines
        assert set(body["driver_strengths_pct"].keys()) == set(THEME_DRIVERS)
        assert body["driver_strengths_pct"]["geopolitics"] == 75
        assert body["driver_strengths_pct"]["fiscal_policy"] == 55
        assert body["driver_strengths_pct"]["supply_demand"] == 20
        assert body["provenance"] == "practitioner_stamp"

    def test_cache_control_is_no_store(self, client: TestClient) -> None:
        """LIVE state — Cache-Control: private, no-store header set
        per r161 verdict + r184 origin_zone endpoint pattern."""
        ranking = _build_sample_ranking()
        with patch(
            "ichor_api.routers.theme_dominant.classify_dominant_theme",
            AsyncMock(return_value=ranking),
        ):
            response = client.get("/v1/theme-dominant")
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "private, no-store"

    def test_endpoint_is_asset_agnostic(self, client: TestClient) -> None:
        """No path param — the theme drives the global macro regime,
        not per-asset. Same response for every /briefing/X consumer."""
        ranking = _build_sample_ranking()
        with patch(
            "ichor_api.routers.theme_dominant.classify_dominant_theme",
            AsyncMock(return_value=ranking),
        ):
            r1 = client.get("/v1/theme-dominant")
            r2 = client.get("/v1/theme-dominant")
        assert r1.status_code == 200
        assert r2.status_code == 200
        # Same response shape (the underlying classifier is deterministic
        # given identical inputs ; the AsyncMock returns the same fixture)
        assert r1.json() == r2.json()


class TestThemeDominantRouterHonestAbsence:
    """404 when classifier returns None — doctrine #11 calibrated honesty."""

    def test_returns_404_when_classifier_returns_none(self, client: TestClient) -> None:
        """No driver meets dominance threshold → 404 honest absence."""
        with patch(
            "ichor_api.routers.theme_dominant.classify_dominant_theme",
            AsyncMock(return_value=None),
        ):
            response = client.get("/v1/theme-dominant")
        assert response.status_code == 404
        detail = response.json()["detail"]
        assert "0.5 dominance threshold" in detail
        assert "doctrine #11" in detail


class TestThemeDominantOutPydanticSurface:
    """The Pydantic ``ThemeDominantOut`` projection itself is verifier-
    friendly (frozen, extra=forbid, ge/le constraints)."""

    def test_theme_dominant_out_is_frozen(self) -> None:
        from ichor_api.routers.theme_dominant import ThemeDominantOut

        assert ThemeDominantOut.model_config.get("frozen") is True

    def test_theme_dominant_out_forbids_extra_fields(self) -> None:
        from ichor_api.routers.theme_dominant import ThemeDominantOut

        assert ThemeDominantOut.model_config.get("extra") == "forbid"

    def test_top_theme_strength_pct_bounded_0_100(self) -> None:
        from ichor_api.routers.theme_dominant import ThemeDominantOut

        with pytest.raises(Exception):  # ValidationError
            ThemeDominantOut(
                top_theme="geopolitics",
                top_theme_strength_pct=150,  # > 100 rejected
                computed_at_utc=datetime(2026, 5, 28, 13, 0, tzinfo=UTC),
            )


class TestProjectRankingHelper:
    """Pure ``_project_ranking`` helper unit test — percent rounding +
    8-driver exhaustive dispatch."""

    def test_full_8_driver_dispatch_includes_baselines(self) -> None:
        """Even drivers at baseline 0.2 appear in driver_strengths_pct
        — the projection iterates THEME_DRIVERS exhaustively to keep
        the frontend rendering predictable (8 bars, never missing keys)."""
        from ichor_api.routers.theme_dominant import _project_ranking

        ranking = _build_sample_ranking()
        out = _project_ranking(ranking)
        # All 8 drivers present, even baselines (supply_demand 0.2 → 20)
        assert len(out.driver_strengths_pct) == 8
        for driver in THEME_DRIVERS:
            assert driver in out.driver_strengths_pct
            assert 0 <= out.driver_strengths_pct[driver] <= 100

    def test_rounding_consistency(self) -> None:
        """0.75 → 75 exact ; 0.55 → 55 exact ; 0.45 → 45 exact."""
        from ichor_api.routers.theme_dominant import _project_ranking

        ranking = _build_sample_ranking()
        out = _project_ranking(ranking)
        assert out.driver_strengths_pct["geopolitics"] == 75
        assert out.driver_strengths_pct["fiscal_policy"] == 55
        assert out.driver_strengths_pct["market_interconnexions"] == 45
