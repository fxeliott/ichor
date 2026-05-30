"""Tests — ``GET /v1/london-session/{asset}`` + the ``load_london_session`` loader.

Mirror of ``test_origin_zone_router.py`` (r184) : FastAPI TestClient +
``app.dependency_overrides[get_session]`` for service-layer mocking ; no DB hit,
no LLM call. Covers :
- 200 OK happy path with full ``LondonSessionOut`` shape + Pydantic field parity
- 404 honest absence when ``load_london_session`` returns None
- 422 on malformed asset path param (FastAPI Path constraint)
- ``Cache-Control: private, no-store`` (LIVE state)
- ``provenance`` defaults to ``practitioner_stamp``
- the loader's fetch→None-filter→compute wiring (rows with NULL OHLC dropped)
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

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


def _sample_read() -> LondonSessionRead:
    # Mirrors the Friday EUR ground-truth from the §6.2 ship: open 1.1653 →
    # close 1.16427 (−10 pip), 30 pip range, baissière.
    return LondonSessionRead(
        session_date=date(2026, 5, 29),
        open_price=1.1653,
        high=1.1670,
        low=1.1640,
        close=1.16427,
        range_abs=0.0030,
        net_change=-0.00103,
        direction="down",
        bar_count=240,
        avg_range=0.0025,
        range_ratio=1.2,
        is_today=False,
    )


class TestLondonSessionRouterHappyPath:
    def test_returns_200_with_full_shape(self, client: TestClient) -> None:
        with patch(
            "ichor_api.routers.london_session.load_london_session",
            AsyncMock(return_value=_sample_read()),
        ):
            response = client.get("/v1/london-session/EUR_USD")
        assert response.status_code == 200
        body = response.json()
        assert body["asset"] == "EUR_USD"
        assert body["session_date"] == "2026-05-29"
        assert body["is_today"] is False
        assert body["open_price"] == pytest.approx(1.1653)
        assert body["close"] == pytest.approx(1.16427)
        assert body["range_abs"] == pytest.approx(0.0030)
        assert body["net_change"] == pytest.approx(-0.00103)
        assert body["direction"] == "down"
        assert body["bar_count"] == 240
        assert body["range_ratio"] == pytest.approx(1.2)
        assert body["avg_range"] == pytest.approx(0.0025)
        assert body["provenance"] == "practitioner_stamp"
        assert "computed_at_utc" in body

    def test_cache_control_is_no_store(self, client: TestClient) -> None:
        with patch(
            "ichor_api.routers.london_session.load_london_session",
            AsyncMock(return_value=_sample_read()),
        ):
            response = client.get("/v1/london-session/EUR_USD")
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "private, no-store"

    def test_each_priority_asset_accepted(self, client: TestClient) -> None:
        for asset in ("EUR_USD", "GBP_USD", "XAU_USD", "SPX500_USD", "NAS100_USD"):
            with patch(
                "ichor_api.routers.london_session.load_london_session",
                AsyncMock(return_value=_sample_read()),
            ):
                response = client.get(f"/v1/london-session/{asset}")
            assert response.status_code == 200, f"asset={asset} failed"
            assert response.json()["asset"] == asset


class TestLondonSessionRouterHonestAbsence:
    def test_returns_404_when_loader_returns_none(self, client: TestClient) -> None:
        # FX-centric : equity-index London windows can be thin/empty → None → 404.
        with patch(
            "ichor_api.routers.london_session.load_london_session",
            AsyncMock(return_value=None),
        ):
            response = client.get("/v1/london-session/SPX500_USD")
        assert response.status_code == 404
        assert "doctrine #11" in response.json()["detail"]


class TestLondonSessionRouterValidation:
    def test_returns_422_on_lowercase(self, client: TestClient) -> None:
        assert client.get("/v1/london-session/eur_usd").status_code == 422

    def test_returns_422_on_special_chars(self, client: TestClient) -> None:
        assert client.get("/v1/london-session/EUR-USD").status_code == 422


class TestLondonSessionOutPydanticSurface:
    def test_out_is_frozen(self) -> None:
        from ichor_api.routers.london_session import LondonSessionOut

        assert LondonSessionOut.model_config.get("frozen") is True

    def test_out_forbids_extra_fields(self) -> None:
        from ichor_api.routers.london_session import LondonSessionOut

        assert LondonSessionOut.model_config.get("extra") == "forbid"


class TestLoadLondonSession:
    """The thin DB loader : fetch → drop NULL-OHLC rows → delegate to the
    pure compute. Verified without 30+ synthetic bars by patching compute and
    asserting the Bar list it receives."""

    @pytest.mark.asyncio
    async def test_filters_null_ohlc_rows_and_delegates(self) -> None:
        from ichor_api.services import london_session as svc

        t0 = datetime(2026, 5, 29, 7, 0, tzinfo=UTC)
        t1 = datetime(2026, 5, 29, 7, 1, tzinfo=UTC)
        t2 = datetime(2026, 5, 29, 7, 2, tzinfo=UTC)
        rows = [
            (t0, 1.10, 1.11, 1.09, 1.105),  # valid
            (t1, None, 1.11, 1.09, 1.105),  # NULL open → dropped
            (t2, 1.10, 1.11, 1.09, None),  # NULL close → dropped
        ]
        result_obj = MagicMock()
        result_obj.all = MagicMock(return_value=rows)
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=result_obj)

        with patch.object(svc, "compute_london_session", return_value=None) as mock_compute:
            out = await svc.load_london_session(
                mock_session, "EUR_USD", now_utc=datetime(2026, 5, 29, 13, 0, tzinfo=UTC)
            )

        assert out is None  # compute returned None (mocked)
        bars_arg = mock_compute.call_args.args[0]
        assert len(bars_arg) == 1  # the two NULL-OHLC rows were filtered out
        assert bars_arg[0].open == pytest.approx(1.10)
        assert bars_arg[0].close == pytest.approx(1.105)
