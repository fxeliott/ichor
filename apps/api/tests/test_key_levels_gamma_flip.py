"""Tests for gamma_flip key_level computer (ADR-083 D3 phase 3, r56).

Covers : asset proxy mapping (SPY→SPX500_USD, QQQ→NAS100_USD),
3 regime zones (above-flip / transition / below-flip), defensive
None handling for missing data.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from ichor_api.services.key_levels import KeyLevel, compute_gamma_flip_levels
from ichor_api.services.key_levels.gamma_flip import (
    _GEX_ASSET_TO_ICHOR_ASSET,
    GAMMA_FLIP_TRANSITION_DELTA_PCT,
)


def _mock_session_with_rows(rows: list[tuple]) -> MagicMock:
    """Build a mock async session that returns the given rows."""
    session = MagicMock()
    result = MagicMock()
    result.all.return_value = rows
    session.execute = AsyncMock(return_value=result)
    return session


_TS = datetime(2026, 5, 15, 14, 30, 19)


# ----- Constants invariants -----------------------------------------


def test_asset_proxy_mapping_per_adr_089() -> None:
    """SPY → SPX500_USD + QQQ → NAS100_USD per ADR-089."""
    assert _GEX_ASSET_TO_ICHOR_ASSET["SPY"] == "SPX500_USD"
    assert _GEX_ASSET_TO_ICHOR_ASSET["QQQ"] == "NAS100_USD"
    assert len(_GEX_ASSET_TO_ICHOR_ASSET) == 2, "only SPY+QQQ for r56 scope"


def test_transition_delta_pct_is_sane() -> None:
    """Transition zone within ±0.5%. Drift = ADR amendment required."""
    assert GAMMA_FLIP_TRANSITION_DELTA_PCT == 0.005
    assert 0 < GAMMA_FLIP_TRANSITION_DELTA_PCT < 0.05


# ----- None paths ---------------------------------------------------


@pytest.mark.asyncio
async def test_returns_empty_list_when_no_data() -> None:
    """Empty gex_snapshots → no levels (graceful, returns [])."""
    session = _mock_session_with_rows([])
    assert await compute_gamma_flip_levels(session) == []


@pytest.mark.asyncio
async def test_unknown_asset_skipped() -> None:
    """gex asset not in mapping (e.g. IWM) → skipped silently."""
    session = _mock_session_with_rows([("IWM", 200.0, 195.0, _TS)])
    assert await compute_gamma_flip_levels(session) == []


@pytest.mark.asyncio
async def test_zero_or_negative_flip_skipped() -> None:
    """Defensive : flip <= 0 (data anomaly) → skipped."""
    session = _mock_session_with_rows([("SPY", 748.0, 0.0, _TS)])
    assert await compute_gamma_flip_levels(session) == []


@pytest.mark.asyncio
async def test_implausibly_far_flip_rejected_r67() -> None:
    """r67 defense-in-depth : a flip > 25 % from spot is corrupt
    collector data (the gex_snapshots QQQ 2026-05-15 21:30 row :
    spot 710.74 / flip 310.43 = -56%, which rendered '+128.95%'
    nonsense on the /briefing dashboard). The computer MUST NOT emit
    a KeyLevel for it — a missing level is honest, a garbage one
    erodes dashboard trust."""
    session = _mock_session_with_rows([("QQQ", 710.74, 310.4334, _TS)])
    assert await compute_gamma_flip_levels(session) == []


@pytest.mark.asyncio
async def test_plausible_flip_still_emitted_r67() -> None:
    """r67 guard must NOT over-reject : a sane flip near spot (the GOOD
    QQQ rows, e.g. spot 719.79 / flip 715.00 = -0.67%) still emits a
    KeyLevel normally."""
    levels = await compute_gamma_flip_levels(
        _mock_session_with_rows([("QQQ", 719.79, 715.0011, _TS)])
    )
    assert len(levels) == 1
    assert levels[0].asset == "NAS100_USD"
    assert levels[0].kind == "gamma_flip"
    assert levels[0].level == pytest.approx(715.0011)
    session2 = _mock_session_with_rows([("SPY", 748.0, -1.0, _TS)])
    assert await compute_gamma_flip_levels(session2) == []


# ----- 3 regime zones ----------------------------------------------


@pytest.mark.asyncio
async def test_spot_above_flip_returns_dampened_regime_keylevel() -> None:
    """Spot 1% above flip → above-flip regime (vol-dampened)."""
    session = _mock_session_with_rows([("QQQ", 720.0, 712.7, _TS)])  # ~+1%
    levels = await compute_gamma_flip_levels(session)
    assert len(levels) == 1
    kl = levels[0]
    assert isinstance(kl, KeyLevel)
    assert kl.asset == "NAS100_USD"
    assert kl.kind == "gamma_flip"
    assert kl.level == pytest.approx(712.7)
    assert kl.side == "above_long_below_short"
    assert "above flip" in kl.note.lower() or "dampened" in kl.note.lower()


@pytest.mark.asyncio
async def test_spot_below_flip_returns_amplified_regime_keylevel() -> None:
    """Spot 2% below flip → below-flip regime (vol-amplified, fragile)."""
    session = _mock_session_with_rows([("SPY", 730.0, 745.0, _TS)])  # ~-2%
    levels = await compute_gamma_flip_levels(session)
    assert len(levels) == 1
    kl = levels[0]
    assert kl.asset == "SPX500_USD"
    assert kl.kind == "gamma_flip"
    assert "below flip" in kl.note.lower() or "amplified" in kl.note.lower()
    assert "fragile" in kl.note.lower() or "trend" in kl.note.lower()


@pytest.mark.asyncio
async def test_spot_at_flip_returns_transition_zone_keylevel() -> None:
    """Spot 0.1% above flip → transition zone (within ±0.5%)."""
    session = _mock_session_with_rows([("SPY", 748.17, 748.0, _TS)])  # ~+0.02%
    levels = await compute_gamma_flip_levels(session)
    assert len(levels) == 1
    kl = levels[0]
    assert kl.asset == "SPX500_USD"
    assert "transition" in kl.note.lower()


# ----- Multi-asset batch -------------------------------------------


@pytest.mark.asyncio
async def test_returns_one_level_per_known_asset() -> None:
    """Both SPY + QQQ snapshots → 2 KeyLevels returned."""
    session = _mock_session_with_rows(
        [
            ("QQQ", 720.0, 712.7, _TS),  # above flip
            ("SPY", 730.0, 745.0, _TS),  # below flip
        ]
    )
    levels = await compute_gamma_flip_levels(session)
    assert len(levels) == 2
    assets = {kl.asset for kl in levels}
    assert assets == {"NAS100_USD", "SPX500_USD"}


# ----- Source attribution ------------------------------------------


@pytest.mark.asyncio
async def test_source_includes_flashalpha_asset_and_proxy_note() -> None:
    """Source attribution must mention flashalpha + the gex asset
    + the ichor asset proxy mapping (audit trail)."""
    session = _mock_session_with_rows([("SPY", 748.0, 745.0, _TS)])
    levels = await compute_gamma_flip_levels(session)
    kl = levels[0]
    assert "flashalpha" in kl.source
    assert "SPY" in kl.source
    assert "SPX500_USD" in kl.source  # proxy attribution
    assert "2026-05-15" in kl.source


# ----- Serialization shape ------------------------------------------


@pytest.mark.asyncio
async def test_gamma_flip_keylevel_to_dict_matches_adr_083_d3_shape() -> None:
    """ADR-083 D3 spec : `{asset, level, kind, side, source}` JSON shape."""
    session = _mock_session_with_rows([("QQQ", 720.0, 715.0, _TS)])
    levels = await compute_gamma_flip_levels(session)
    d = levels[0].to_dict()
    assert set(d.keys()) >= {"asset", "level", "kind", "side", "source"}
    assert d["asset"] == "NAS100_USD"
    assert d["kind"] == "gamma_flip"
    assert d["level"] == 715.0
