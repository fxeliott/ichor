"""Tests for vol/credit regime switch computers (ADR-083 D3 phase 4, r57).

Covers : VIX (5 bands) + SKEW (4 bands) + HY OAS (4 bands).
Each computer returns None inside NORMAL band, KeyLevel outside.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from ichor_api.services.key_levels import (
    KeyLevel,
    compute_hy_oas_percentile,
    compute_skew_regime_switch,
    compute_vix_regime_switch,
)
from ichor_api.services.key_levels.vol_regime import (
    HY_OAS_COMPLACENCY_CEILING,
    HY_OAS_CRISIS_FLOOR,
    HY_OAS_NORMAL_CEILING,
    SKEW_EXTREME_FLOOR,
    SKEW_LOW_TAIL_CEILING,
    SKEW_NORMAL_CEILING,
    VIX_CRISIS_FLOOR,
    VIX_EXTREME_COMPLACENCY,
    VIX_LOW_VOL_FLOOR,
    VIX_NORMAL_CEILING,
)


def _mock_session_one_row(value: float | None, obs_date: date | None = None) -> MagicMock:
    """Mock async session returning one (value, date) row."""
    obs_date = obs_date or date(2026, 5, 14)
    session = MagicMock()
    result = MagicMock()
    if value is None:
        result.first.return_value = None
    else:
        result.first.return_value = (value, obs_date)
    session.execute = AsyncMock(return_value=result)
    return session


# ----- Constants invariants ------------------------------------------


def test_vix_band_constants_ordered() -> None:
    """VIX bands must be strictly ordered (extreme<low<normal<crisis)."""
    assert VIX_EXTREME_COMPLACENCY < VIX_LOW_VOL_FLOOR < VIX_NORMAL_CEILING < VIX_CRISIS_FLOOR
    assert VIX_EXTREME_COMPLACENCY == 12.0
    assert VIX_LOW_VOL_FLOOR == 15.0
    assert VIX_NORMAL_CEILING == 25.0
    assert VIX_CRISIS_FLOOR == 35.0


def test_skew_band_constants_ordered() -> None:
    """SKEW bands ordered : low_tail < normal < extreme."""
    assert SKEW_LOW_TAIL_CEILING < SKEW_NORMAL_CEILING < SKEW_EXTREME_FLOOR
    assert SKEW_LOW_TAIL_CEILING == 120.0
    assert SKEW_NORMAL_CEILING == 130.0
    assert SKEW_EXTREME_FLOOR == 145.0


def test_hy_oas_band_constants_ordered() -> None:
    """HY OAS bands ordered : complacency < normal < crisis."""
    assert HY_OAS_COMPLACENCY_CEILING < HY_OAS_NORMAL_CEILING < HY_OAS_CRISIS_FLOOR
    assert HY_OAS_COMPLACENCY_CEILING == 3.0
    assert HY_OAS_NORMAL_CEILING == 5.0
    assert HY_OAS_CRISIS_FLOOR == 7.0


# ----- VIX bands -----------------------------------------------------


@pytest.mark.asyncio
async def test_vix_none_when_no_data() -> None:
    assert await compute_vix_regime_switch(_mock_session_one_row(None)) is None


@pytest.mark.asyncio
async def test_vix_normal_band_returns_none() -> None:
    """VIX 17.5 (current real Hetzner avg) = NORMAL → no signal."""
    assert await compute_vix_regime_switch(_mock_session_one_row(17.5)) is None


@pytest.mark.asyncio
async def test_vix_extreme_complacency_below_12() -> None:
    """VIX < 12 → extreme complacency signal."""
    kl = await compute_vix_regime_switch(_mock_session_one_row(10.5))
    assert kl is not None
    assert isinstance(kl, KeyLevel)
    assert kl.kind == "vix_regime_switch"
    assert "complacency" in kl.note.lower()


@pytest.mark.asyncio
async def test_vix_low_vol_band_12_to_15() -> None:
    kl = await compute_vix_regime_switch(_mock_session_one_row(13.0))
    assert kl is not None
    assert "low-vol" in kl.note.lower()


@pytest.mark.asyncio
async def test_vix_elevated_25_to_35() -> None:
    kl = await compute_vix_regime_switch(_mock_session_one_row(28.0))
    assert kl is not None
    assert "elevated" in kl.note.lower() or "risk-off" in kl.note.lower()


@pytest.mark.asyncio
async def test_vix_crisis_above_35() -> None:
    kl = await compute_vix_regime_switch(_mock_session_one_row(45.0))
    assert kl is not None
    assert "crisis" in kl.note.lower()


# ----- SKEW bands ----------------------------------------------------


@pytest.mark.asyncio
async def test_skew_none_when_no_data() -> None:
    assert await compute_skew_regime_switch(_mock_session_one_row(None)) is None


@pytest.mark.asyncio
async def test_skew_normal_band_returns_none() -> None:
    """SKEW 125 = NORMAL band 120-130 → no signal."""
    assert await compute_skew_regime_switch(_mock_session_one_row(125.0)) is None


@pytest.mark.asyncio
async def test_skew_low_tail_below_120() -> None:
    kl = await compute_skew_regime_switch(_mock_session_one_row(115.0))
    assert kl is not None
    assert kl.kind == "skew_regime_switch"
    assert "low tail" in kl.note.lower() or "call-side" in kl.note.lower()


@pytest.mark.asyncio
async def test_skew_elevated_130_to_145() -> None:
    """SKEW 139.32 (real Hetzner data 2026-05-14) → elevated tail concern."""
    kl = await compute_skew_regime_switch(_mock_session_one_row(139.32, date(2026, 5, 14)))
    assert kl is not None
    assert "elevated" in kl.note.lower()


@pytest.mark.asyncio
async def test_skew_extreme_above_145() -> None:
    kl = await compute_skew_regime_switch(_mock_session_one_row(150.0))
    assert kl is not None
    assert "extreme" in kl.note.lower()


# ----- HY OAS bands -------------------------------------------------


@pytest.mark.asyncio
async def test_hy_oas_none_when_no_data() -> None:
    assert await compute_hy_oas_percentile(_mock_session_one_row(None)) is None


@pytest.mark.asyncio
async def test_hy_oas_normal_band_returns_none() -> None:
    """HY OAS 4.0 = NORMAL band 3-5 → no signal."""
    assert await compute_hy_oas_percentile(_mock_session_one_row(4.0)) is None


@pytest.mark.asyncio
async def test_hy_oas_complacency_below_3() -> None:
    """HY OAS 2.79 (real Hetzner avg 2026-05) → complacency."""
    kl = await compute_hy_oas_percentile(_mock_session_one_row(2.79))
    assert kl is not None
    assert kl.kind == "hy_oas_percentile"
    assert "complacency" in kl.note.lower()


@pytest.mark.asyncio
async def test_hy_oas_elevated_5_to_7() -> None:
    kl = await compute_hy_oas_percentile(_mock_session_one_row(6.0))
    assert kl is not None
    assert "elevated" in kl.note.lower() or "stress" in kl.note.lower()


@pytest.mark.asyncio
async def test_hy_oas_crisis_above_7() -> None:
    kl = await compute_hy_oas_percentile(_mock_session_one_row(8.5))
    assert kl is not None
    assert "crisis" in kl.note.lower()


# ----- Serialization ---------------------------------------------


@pytest.mark.asyncio
async def test_vix_keylevel_to_dict_matches_adr_083_d3_shape() -> None:
    kl = await compute_vix_regime_switch(_mock_session_one_row(45.0))
    assert kl is not None
    d = kl.to_dict()
    assert set(d.keys()) >= {"asset", "level", "kind", "side", "source"}
    assert d["asset"] == "USD"
    assert d["kind"] == "vix_regime_switch"
    assert "VIXCLS" in d["source"]
