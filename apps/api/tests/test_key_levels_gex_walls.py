"""Tests for call_wall + put_wall computers (ADR-083 D3 r60 extension).

Reuse gamma_flip pattern : batch SPY+QQQ from gex_snapshots, returns
list[KeyLevel]. Each fires only in actionable zone (approach OR breach).
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from ichor_api.services.key_levels import (
    KeyLevel,
    compute_call_wall_levels,
    compute_put_wall_levels,
)
from ichor_api.services.key_levels.gex_walls import (
    _GEX_ASSET_TO_ICHOR_ASSET,
    WALL_APPROACH_DELTA_PCT,
)


def _mock_session_with_rows(rows: list[tuple]) -> MagicMock:
    session = MagicMock()
    result = MagicMock()
    result.all.return_value = rows
    session.execute = AsyncMock(return_value=result)
    return session


_TS = datetime(2026, 5, 15, 14, 30, 0)


# ----- Constants ---------------------------------------------------


def test_approach_delta_sane() -> None:
    assert WALL_APPROACH_DELTA_PCT == 0.005
    assert 0 < WALL_APPROACH_DELTA_PCT < 0.05


def test_asset_proxy_mapping_consistent_with_gamma_flip() -> None:
    """Same SPY/QQQ → SPX500_USD/NAS100_USD per ADR-089."""
    assert _GEX_ASSET_TO_ICHOR_ASSET["SPY"] == "SPX500_USD"
    assert _GEX_ASSET_TO_ICHOR_ASSET["QQQ"] == "NAS100_USD"


# ----- call_wall ---------------------------------------------------


@pytest.mark.asyncio
async def test_call_wall_empty_when_no_data() -> None:
    session = _mock_session_with_rows([])
    assert await compute_call_wall_levels(session) == []


@pytest.mark.asyncio
async def test_call_wall_safely_below_returns_no_signal() -> None:
    """Spot 5% below call_wall = safely below resistance, no signal."""
    session = _mock_session_with_rows([("SPY", 700.0, 750.0, 680.0, _TS)])
    assert await compute_call_wall_levels(session) == []


@pytest.mark.asyncio
async def test_call_wall_approaching_within_delta() -> None:
    """Spot within 0.5% of call_wall → APPROACHING signal."""
    session = _mock_session_with_rows(
        [("SPY", 748.17, 750.0, 680.0, _TS)]  # ~-0.24%
    )
    levels = await compute_call_wall_levels(session)
    assert len(levels) == 1
    kl = levels[0]
    assert isinstance(kl, KeyLevel)
    assert kl.asset == "SPX500_USD"
    assert kl.kind == "gex_call_wall"
    assert kl.level == 750.0
    assert "approaching" in kl.note.lower()


@pytest.mark.asyncio
async def test_call_wall_breached_above_returns_squeeze_signal() -> None:
    """Spot decisively above call_wall → RESISTANCE BREACHED."""
    session = _mock_session_with_rows(
        [("QQQ", 730.0, 720.0, 700.0, _TS)]  # +1.39% above
    )
    levels = await compute_call_wall_levels(session)
    assert len(levels) == 1
    assert "breached" in levels[0].note.lower() or "squeeze" in levels[0].note.lower()


# ----- put_wall ----------------------------------------------------


@pytest.mark.asyncio
async def test_put_wall_safely_above_returns_no_signal() -> None:
    """Spot 5% above put_wall = safely above support, no signal."""
    session = _mock_session_with_rows([("SPY", 750.0, 770.0, 700.0, _TS)])
    assert await compute_put_wall_levels(session) == []


@pytest.mark.asyncio
async def test_put_wall_approaching_within_delta() -> None:
    """Spot within 0.5% of put_wall → APPROACHING signal."""
    session = _mock_session_with_rows(
        [("QQQ", 715.5, 720.0, 715.0, _TS)]  # +0.07% above put_wall
    )
    levels = await compute_put_wall_levels(session)
    assert len(levels) == 1
    kl = levels[0]
    assert kl.asset == "NAS100_USD"
    assert kl.kind == "gex_put_wall"
    assert kl.level == 715.0
    assert "approaching" in kl.note.lower()


@pytest.mark.asyncio
async def test_put_wall_breached_below_returns_acceleration_signal() -> None:
    """Spot below put_wall → SUPPORT BREACHED, acceleration risk."""
    session = _mock_session_with_rows(
        [("SPY", 670.0, 770.0, 680.0, _TS)]  # -1.47% below put_wall
    )
    levels = await compute_put_wall_levels(session)
    assert len(levels) == 1
    assert "breached" in levels[0].note.lower() or "acceleration" in levels[0].note.lower()


# ----- Multi-asset batch ------------------------------------------


@pytest.mark.asyncio
async def test_both_assets_call_wall_returns_2_levels() -> None:
    """SPY + QQQ both approaching call_wall → 2 KeyLevels."""
    session = _mock_session_with_rows(
        [
            ("SPY", 748.17, 750.0, 680.0, _TS),
            ("QQQ", 719.79, 720.0, 715.0, _TS),
        ]
    )
    levels = await compute_call_wall_levels(session)
    assert len(levels) == 2
    assets = {kl.asset for kl in levels}
    assert assets == {"SPX500_USD", "NAS100_USD"}


# ----- Defensive --------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_asset_skipped() -> None:
    session = _mock_session_with_rows([("IWM", 200.0, 210.0, 195.0, _TS)])
    assert await compute_call_wall_levels(session) == []
    assert await compute_put_wall_levels(session) == []


@pytest.mark.asyncio
async def test_zero_or_negative_wall_skipped() -> None:
    session = _mock_session_with_rows([("SPY", 750.0, 0.0, 680.0, _TS)])
    assert await compute_call_wall_levels(session) == []
    session2 = _mock_session_with_rows([("SPY", 750.0, 770.0, 0.0, _TS)])
    assert await compute_put_wall_levels(session2) == []
