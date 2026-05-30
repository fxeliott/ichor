"""Unit tests for collectors/eia_petroleum.py weekly crude-stocks fetch
(ADR-107, r190 supply_demand driver).

Verifies:
  1. fetch_weekly_petroleum_stocks returns [] when api_key is empty
     (EIA has NO anonymous tier — graceful, no network attempt).
  2. parses the EIA OpenData v2 response shape (response.data rows).
  3. stamps source_url on each observation (DB NOT NULL contract).
  4. returns [] on HTTP error (graceful, never raises).
  5. skips rows missing series/period.
  6. EiaObservation is frozen (defense-in-depth).

The fetch fn creates its own AsyncClient in production ; the optional
``client`` injection (mirror ecb_estr) lets these tests run offline
with an AsyncMock — no respx / network.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from ichor_api.collectors.eia_petroleum import EiaObservation, fetch_weekly_petroleum_stocks

_EIA_PAYLOAD = {
    "response": {
        "data": [
            {"series": "WCESTUS1", "period": "2026-05-23", "value": 442000, "units": "MBBL"},
            {"series": "WCESTUS1", "period": "2026-05-16", "value": 438000, "units": "MBBL"},
            {"series": "WCRSTUS1", "period": "2026-05-23", "value": 420000, "units": "MBBL"},
        ]
    }
}


def _mock_client_returning(payload: dict) -> AsyncMock:
    """An AsyncMock httpx client whose .get() returns a response whose
    sync .json() yields ``payload`` and .raise_for_status() is a no-op."""
    response_mock = MagicMock()
    response_mock.raise_for_status = MagicMock()
    response_mock.json = MagicMock(return_value=payload)
    client = AsyncMock()
    client.get = AsyncMock(return_value=response_mock)
    return client


@pytest.mark.asyncio
async def test_returns_empty_without_api_key() -> None:
    """EIA has no anonymous tier — empty key → [] without any HTTP call."""
    out = await fetch_weekly_petroleum_stocks(api_key="")
    assert out == []


@pytest.mark.asyncio
async def test_parses_eia_response_shape() -> None:
    client = _mock_client_returning(_EIA_PAYLOAD)
    out = await fetch_weekly_petroleum_stocks(api_key="k", client=client)
    assert len(out) == 3
    assert out[0].series_id == "WCESTUS1"
    assert out[0].period == "2026-05-23"
    assert out[0].value == 442000.0
    assert out[0].unit == "MBBL"


@pytest.mark.asyncio
async def test_stamps_source_url() -> None:
    """DB ``source_url`` is NOT NULL — every weekly obs must carry it."""
    client = _mock_client_returning(_EIA_PAYLOAD)
    out = await fetch_weekly_petroleum_stocks(api_key="k", client=client)
    assert out
    assert all(o.source_url and "eia.gov" in o.source_url for o in out)


@pytest.mark.asyncio
async def test_returns_empty_on_http_error() -> None:
    """Network blip / 5xx / timeout → graceful [] (httpx.HTTPError caught)."""
    client = AsyncMock()
    client.get = AsyncMock(side_effect=httpx.RequestError("simulated"))
    out = await fetch_weekly_petroleum_stocks(api_key="k", client=client)
    assert out == []


@pytest.mark.asyncio
async def test_skips_rows_missing_series_or_period() -> None:
    payload = {
        "response": {
            "data": [
                {"series": "", "period": "2026-05-23", "value": 1.0, "units": "MBBL"},
                {"series": "WCESTUS1", "period": "", "value": 1.0, "units": "MBBL"},
                {"series": "WCESTUS1", "period": "2026-05-23", "value": 442000, "units": "MBBL"},
            ]
        }
    }
    client = _mock_client_returning(payload)
    out = await fetch_weekly_petroleum_stocks(api_key="k", client=client)
    assert len(out) == 1
    assert out[0].series_id == "WCESTUS1"


def test_observation_is_frozen() -> None:
    obs = EiaObservation(
        series_id="WCESTUS1",
        period="2026-05-23",
        value=442000.0,
        unit="MBBL",
        fetched_at=datetime(2026, 5, 23, tzinfo=UTC),
        source_url="https://api.eia.gov/v2/petroleum/stoc/wstk/data/",
    )
    with pytest.raises(Exception):  # FrozenInstanceError
        obs.value = 1.0  # type: ignore[misc]
