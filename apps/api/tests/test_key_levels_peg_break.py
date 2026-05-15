"""Tests for HKMA peg-break key_level computer (ADR-083 D3 phase 2, r55).

HKMA convertibility band [7.75, 7.85] around 7.80 hard peg. Computer
fires on either side approach (within ±0.03) or actual band breach.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from ichor_api.services.key_levels import KeyLevel, compute_hkma_peg_break
from ichor_api.services.key_levels.peg_break import (
    HKMA_APPROACH_DELTA,
    HKMA_PEG_CENTER,
    HKMA_STRONG_SIDE_EDGE,
    HKMA_WEAK_SIDE_EDGE,
)


def _mock_session_with_value(value: float | None, obs_date: date | None = None) -> MagicMock:
    """Build a mock async session that returns one (rate, date) row."""
    obs_date = obs_date or date(2026, 5, 8)
    session = MagicMock()
    result = MagicMock()
    if value is None:
        result.first.return_value = None
    else:
        result.first.return_value = (value, obs_date)
    session.execute = AsyncMock(return_value=result)
    return session


# ----- Constants invariants ------------------------------------------


def test_hkma_constants_match_canonical_band() -> None:
    """Pin band edges + peg center to canonical HKMA values.
    Drift here = ADR amendment required."""
    assert HKMA_WEAK_SIDE_EDGE == 7.85, "weak-side ceiling = 7.85 USD/HKD"
    assert HKMA_STRONG_SIDE_EDGE == 7.75, "strong-side floor = 7.75 USD/HKD"
    assert HKMA_PEG_CENTER == 7.80, "hard peg center = 7.80 USD/HKD"
    assert HKMA_STRONG_SIDE_EDGE < HKMA_PEG_CENTER < HKMA_WEAK_SIDE_EDGE
    assert 0 < HKMA_APPROACH_DELTA < 0.05, "approach delta sane <5 cents"


# ----- None paths ----------------------------------------------------


@pytest.mark.asyncio
async def test_returns_none_when_no_data() -> None:
    """Empty DEXHKUS table → no key level (graceful)."""
    session = _mock_session_with_value(None)
    assert await compute_hkma_peg_break(session) is None


@pytest.mark.asyncio
async def test_returns_none_in_neutral_mid_band() -> None:
    """USD/HKD = 7.80 (peg center) = neutral, no actionable signal."""
    session = _mock_session_with_value(7.80)
    assert await compute_hkma_peg_break(session) is None


@pytest.mark.asyncio
async def test_returns_none_just_outside_approach_zone() -> None:
    """USD/HKD = 7.81 = inside neutral mid-band 7.78-7.82, no signal."""
    session = _mock_session_with_value(7.81)
    assert await compute_hkma_peg_break(session) is None


# ----- Weak-side (USD strengthening, HKD bid expected) -------------


@pytest.mark.asyncio
async def test_weak_side_intervention_live_when_at_edge() -> None:
    """USD/HKD ≥ 7.85 → weak-side intervention LIVE."""
    session = _mock_session_with_value(7.8500, date(2026, 5, 8))
    kl = await compute_hkma_peg_break(session)
    assert kl is not None
    assert isinstance(kl, KeyLevel)
    assert kl.asset == "USDHKD"
    assert kl.kind == "peg_break_hkma"
    assert kl.level == 7.85
    assert kl.side == "above_risk_off_below_risk_on"
    assert "intervention LIVE" in kl.note or "intervention" in kl.note.lower()
    assert "weak-side" in kl.note.lower() or "ceiling" in kl.note.lower()


@pytest.mark.asyncio
async def test_weak_side_intervention_live_above_edge() -> None:
    """USD/HKD = 7.86 (above edge) → weak-side intervention LIVE."""
    session = _mock_session_with_value(7.8600)
    kl = await compute_hkma_peg_break(session)
    assert kl is not None
    assert "LIVE" in kl.note or "live" in kl.note.lower()


@pytest.mark.asyncio
async def test_approaching_weak_side_within_delta() -> None:
    """USD/HKD = 7.8282 (real Hetzner data 2026-05-08) → approaching weak."""
    session = _mock_session_with_value(7.8282, date(2026, 5, 8))
    kl = await compute_hkma_peg_break(session)
    assert kl is not None
    assert kl.kind == "peg_break_hkma"
    assert "approaching" in kl.note.lower()
    assert "weak" in kl.note.lower() or "7.85" in kl.note


# ----- Strong-side (USD weakening, HKD offer expected) -------------


@pytest.mark.asyncio
async def test_strong_side_intervention_live_at_edge() -> None:
    """USD/HKD ≤ 7.75 → strong-side intervention LIVE."""
    session = _mock_session_with_value(7.7500)
    kl = await compute_hkma_peg_break(session)
    assert kl is not None
    assert kl.level == 7.75
    assert kl.side == "above_risk_on_below_risk_off"
    assert "intervention" in kl.note.lower()


@pytest.mark.asyncio
async def test_approaching_strong_side_within_delta() -> None:
    """USD/HKD = 7.77 (within delta of 7.75 floor) → approaching strong."""
    session = _mock_session_with_value(7.7700)
    kl = await compute_hkma_peg_break(session)
    assert kl is not None
    assert "approaching" in kl.note.lower()
    assert "strong" in kl.note.lower() or "7.75" in kl.note


# ----- Serialization shape -----------------------------------------


@pytest.mark.asyncio
async def test_hkma_keylevel_to_dict_matches_adr_083_d3_shape() -> None:
    """ADR-083 D3 spec : {asset, level, kind, side, source} JSON shape."""
    session = _mock_session_with_value(7.8282, date(2026, 5, 8))
    kl = await compute_hkma_peg_break(session)
    assert kl is not None
    d = kl.to_dict()
    assert set(d.keys()) >= {"asset", "level", "kind", "side", "source"}
    assert d["asset"] == "USDHKD"
    assert d["kind"] == "peg_break_hkma"
    assert d["level"] == HKMA_WEAK_SIDE_EDGE
    assert "DEXHKUS" in d["source"]
    assert "2026-05-08" in d["source"]
