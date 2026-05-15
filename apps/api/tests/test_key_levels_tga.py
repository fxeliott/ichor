"""Tests for TGA key_level computer (ADR-083 D3 phase 1, r54).

Verifies threshold band logic + None handling + KeyLevel shape per
ADR-083 spec.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from ichor_api.services.key_levels import KeyLevel, compute_tga_key_level
from ichor_api.services.key_levels.tga import (
    TGA_HIGH_THRESHOLD_BN,
    TGA_LOW_THRESHOLD_BN,
)


def _mock_session_with_value(value_bn: float | None, obs_date: date | None = None) -> MagicMock:
    """Build a mock async session that returns one (value, date) row.

    NOTE : FRED WTREGEN is reported in MILLIONS of USD ; the computer
    converts to billions internally. Mock here passes the value AS IF
    already in billions for test simplicity (caller just ×1000 mentally).
    The empirical bug r54 fix : real FRED returns 838584 for ~$838B,
    not 838 ; computer must divide by 1000 (see tga.py:value_bn).
    """
    obs_date = obs_date or date(2026, 5, 13)
    session = MagicMock()
    result = MagicMock()
    if value_bn is None:
        result.first.return_value = None
    else:
        # Multiply by 1000 to simulate the real FRED units (millions $)
        # so the computer's ÷1000 conversion produces the expected
        # billion-dollar threshold comparison.
        result.first.return_value = (value_bn * 1000.0, obs_date)
    session.execute = AsyncMock(return_value=result)
    return session


def _mock_session_with_raw_millions(value_millions: float, obs_date: date) -> MagicMock:
    """Like _mock_session_with_value but value is RAW FRED millions (no
    conversion). Used to pin the FRED-units bug fix from r54."""
    session = MagicMock()
    result = MagicMock()
    result.first.return_value = (value_millions, obs_date)
    session.execute = AsyncMock(return_value=result)
    return session


# ----- None paths ----------------------------------------------------


@pytest.mark.asyncio
async def test_returns_none_when_no_data() -> None:
    """Empty WTREGEN table → no key level (graceful)."""
    session = _mock_session_with_value(None)
    assert await compute_tga_key_level(session) is None


@pytest.mark.asyncio
async def test_returns_none_in_mid_band() -> None:
    """TGA in $300-700B mid-band = neutral, no actionable level."""
    session = _mock_session_with_value(500.0)
    assert await compute_tga_key_level(session) is None


@pytest.mark.asyncio
async def test_returns_none_at_exact_low_threshold() -> None:
    """Strict inequality `< LOW` : exactly at threshold = neutral."""
    session = _mock_session_with_value(TGA_LOW_THRESHOLD_BN)
    assert await compute_tga_key_level(session) is None


@pytest.mark.asyncio
async def test_returns_none_at_exact_high_threshold() -> None:
    """Strict inequality `> HIGH` : exactly at threshold = neutral."""
    session = _mock_session_with_value(TGA_HIGH_THRESHOLD_BN)
    assert await compute_tga_key_level(session) is None


# ----- LOW threshold (liquidity injection imminent) -----------------


@pytest.mark.asyncio
async def test_low_tga_returns_liquidity_inject_signal() -> None:
    """TGA < $300B → key level with USD-bearish bias (injection imminent)."""
    session = _mock_session_with_value(150.0, date(2026, 5, 13))
    kl = await compute_tga_key_level(session)
    assert kl is not None
    assert isinstance(kl, KeyLevel)
    assert kl.asset == "USD"
    assert kl.level == 150.0
    assert kl.kind == "tga_liquidity_gate"
    assert kl.side == "above_liquidity_drain_below_inject"
    assert "WTREGEN" in kl.source
    assert "2026-05-13" in kl.source
    assert "injection imminent" in kl.note.lower()


# ----- HIGH threshold (liquidity drain expected) --------------------


@pytest.mark.asyncio
async def test_high_tga_returns_liquidity_drain_signal() -> None:
    """TGA > $700B → key level with USD-bid bias (drain expected)."""
    session = _mock_session_with_value(815.0, date(2026, 5, 13))
    kl = await compute_tga_key_level(session)
    assert kl is not None
    assert kl.asset == "USD"
    assert kl.level == 815.0
    assert kl.kind == "tga_liquidity_gate"
    assert "drain expected" in kl.note.lower()


# ----- KeyLevel serialization ---------------------------------------


@pytest.mark.asyncio
async def test_keylevel_to_dict_matches_adr_083_d3_shape() -> None:
    """ADR-083 D3 spec : `{asset, level, kind, side, source}` JSON shape."""
    session = _mock_session_with_value(150.0, date(2026, 5, 13))
    kl = await compute_tga_key_level(session)
    assert kl is not None
    d = kl.to_dict()
    assert set(d.keys()) >= {"asset", "level", "kind", "side", "source"}
    assert d["asset"] == "USD"
    assert d["level"] == 150.0
    assert d["kind"] == "tga_liquidity_gate"
    assert "WTREGEN" in d["source"]


@pytest.mark.asyncio
async def test_keylevel_markdown_line_includes_essentials() -> None:
    """Markdown rendering includes kind, asset, level, side, source."""
    session = _mock_session_with_value(150.0)
    kl = await compute_tga_key_level(session)
    assert kl is not None
    md = kl.to_markdown_line()
    assert "tga_liquidity_gate" in md
    assert "USD" in md
    assert "150" in md
    assert "WTREGEN" in md


# ----- KeyLevel is frozen ------------------------------------------


@pytest.mark.asyncio
async def test_fred_units_conversion_millions_to_billions() -> None:
    """Pin r54 empirical bug fix : FRED WTREGEN reports MILLIONS of USD
    per FRED metadata. Computer must divide by 1000 to compare against
    threshold bands defined in BILLIONS.

    Empirical evidence (Hetzner psql 2026-05-15) : latest WTREGEN value
    = 838584 (millions) = $838.584 billion = ABOVE $700B threshold.

    Without the conversion, 838584 would be compared against 700 and
    trigger HIGH-band logic with a level value of 838584 (would render
    as $838584B in markdown — empirically observed pre-fix).
    """
    session = _mock_session_with_raw_millions(838584.0, date(2026, 5, 13))
    kl = await compute_tga_key_level(session)
    assert kl is not None, "838B should fire HIGH band ($700B threshold)"
    assert kl.level == pytest.approx(838.584), (
        f"level must be in billions after ÷1000 conversion ; got {kl.level}"
    )
    # Note formats with .0f rounding so 838.584 → "839B" — accept either.
    assert any(s in kl.note for s in ("838", "839")), (
        f"note should mention ~$838B (in billions, not millions) ; got: {kl.note!r}"
    )


def test_keylevel_dataclass_is_frozen() -> None:
    """KeyLevel is frozen — caller can't mutate after construction."""
    kl = KeyLevel(
        asset="USD",
        level=150.0,
        kind="tga_liquidity_gate",
        side="above_liquidity_drain_below_inject",
        source="FRED:WTREGEN 2026-05-13",
    )
    with pytest.raises((AttributeError, Exception)):
        kl.level = 999.0  # type: ignore[misc]
