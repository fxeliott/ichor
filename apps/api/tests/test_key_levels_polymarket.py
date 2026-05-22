"""Tests for polymarket_decision computer (ADR-083 D3 phase 5, r58).

Final phase of ADR-083 D3 contract delivery. Covers macro keyword
filter + extreme price thresholds + top-N anti-accumulation cap +
recency/volume filters.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from ichor_api.services.key_levels import (
    KeyLevel,
    compute_polymarket_decision_levels,
)
from ichor_api.services.key_levels.polymarket import (
    POLYMARKET_MIN_VOLUME_USD,
    POLYMARKET_STRONG_NO_THRESHOLD,
    POLYMARKET_STRONG_YES_THRESHOLD,
    POLYMARKET_TOP_N,
    _is_macro_relevant,
)


def _mock_session_with_rows(rows: list[tuple]) -> MagicMock:
    session = MagicMock()
    result = MagicMock()
    result.all.return_value = rows
    session.execute = AsyncMock(return_value=result)
    return session


_NOW = datetime.now(UTC)


# ----- Constants invariants -----------------------------------------


def test_thresholds_are_extreme() -> None:
    assert POLYMARKET_STRONG_YES_THRESHOLD == 0.85
    assert POLYMARKET_STRONG_NO_THRESHOLD == 0.15
    assert POLYMARKET_STRONG_NO_THRESHOLD < POLYMARKET_STRONG_YES_THRESHOLD


def test_top_n_anti_accumulation_strict() -> None:
    """Top-N capped at small number per anti-accumulation discipline."""
    assert POLYMARKET_TOP_N == 3
    assert POLYMARKET_TOP_N <= 5


def test_min_volume_filter_excludes_noise() -> None:
    assert POLYMARKET_MIN_VOLUME_USD >= 10_000.0


# ----- Macro relevance keyword filter ------------------------------


def test_macro_keyword_filter_accepts_bitcoin() -> None:
    assert _is_macro_relevant(
        "bitcoin-above-76k-on-may-15", "Will the price of Bitcoin be above $76,000 on May 15?"
    )


def test_macro_keyword_filter_accepts_fed() -> None:
    assert _is_macro_relevant("fed-rate-cut-june", "Will the Fed cut rates in June?")


def test_macro_keyword_filter_accepts_election() -> None:
    assert _is_macro_relevant("trump-vs-harris-2026", "Trump vs Harris electoral college?")


def test_macro_keyword_filter_rejects_atp() -> None:
    """Sport noise must be filtered out (ATP tennis was 80%+ of volume r58 audit)."""
    assert not _is_macro_relevant(
        "atp-rublev-basilas-2026-05-12",
        "Internazionali BNL d'Italia: Andrey Rublev vs Nikoloz Basilashvili",
    )


def test_macro_keyword_filter_rejects_soccer() -> None:
    assert not _is_macro_relevant(
        "arg-boc-cah-2026-05-09-boc",
        "Will CA Boca Juniors win on 2026-05-09?",
    )


# ----- None / empty paths ------------------------------------------


@pytest.mark.asyncio
async def test_returns_empty_when_no_data() -> None:
    session = _mock_session_with_rows([])
    assert await compute_polymarket_decision_levels(session) == []


@pytest.mark.asyncio
async def test_filters_out_non_macro_markets() -> None:
    """ATP/soccer markets even with extreme prices must be filtered out."""
    session = _mock_session_with_rows(
        [
            ("atp-rublev-basilas", "ATP match", [0.9995, 0.0005], 1_000_000.0, _NOW),
            ("arg-boc-soccer", "Boca match", [0.0005, 0.9995], 500_000.0, _NOW),
        ]
    )
    assert await compute_polymarket_decision_levels(session) == []


@pytest.mark.asyncio
async def test_filters_out_mid_range_prices() -> None:
    """Macro markets with mid-range price (0.40-0.60) = not actionable."""
    session = _mock_session_with_rows(
        [("bitcoin-above-100k", "BTC > 100k?", [0.50, 0.50], 200_000.0, _NOW)]
    )
    assert await compute_polymarket_decision_levels(session) == []


# ----- Extreme price firing ----------------------------------------


@pytest.mark.asyncio
async def test_strong_yes_above_threshold_fires() -> None:
    """Macro market with YES @ 0.95 → KeyLevel fires (strong YES)."""
    session = _mock_session_with_rows(
        [
            (
                "bitcoin-above-76k-on-may-15",
                "Will the price of Bitcoin be above $76,000 on May 15?",
                [0.9995, 0.0005],
                500_000.0,
                _NOW,
            )
        ]
    )
    levels = await compute_polymarket_decision_levels(session)
    assert len(levels) == 1
    kl = levels[0]
    assert isinstance(kl, KeyLevel)
    assert kl.kind == "polymarket_decision"
    assert kl.level > POLYMARKET_STRONG_YES_THRESHOLD
    assert "strong YES" in kl.note or "YES" in kl.note
    assert "bitcoin" in kl.source.lower()


@pytest.mark.asyncio
async def test_strong_no_below_threshold_fires() -> None:
    """Macro market with YES @ 0.05 (NO @ 0.95) → KeyLevel fires (strong NO)."""
    session = _mock_session_with_rows(
        [
            (
                "fed-rate-cut-june",
                "Will the Fed cut rates in June?",
                [0.05, 0.95],
                300_000.0,
                _NOW,
            )
        ]
    )
    levels = await compute_polymarket_decision_levels(session)
    assert len(levels) == 1
    kl = levels[0]
    assert kl.level < POLYMARKET_STRONG_NO_THRESHOLD
    assert "NO" in kl.note


# ----- Top-N anti-accumulation cap --------------------------------


@pytest.mark.asyncio
async def test_top_n_cap_strict_ranks_by_volume() -> None:
    """6 macro markets at extreme prices → top 3 by volume returned."""
    rows = [
        (f"bitcoin-{i}", f"BTC scenario {i}", [0.95, 0.05], 100_000.0 * (10 - i), _NOW)
        for i in range(6)
    ]
    session = _mock_session_with_rows(rows)
    levels = await compute_polymarket_decision_levels(session)
    assert len(levels) == POLYMARKET_TOP_N
    # Highest volumes first : i=0 → 1_000_000, i=1 → 900_000, i=2 → 800_000
    assert "bitcoin-0" in levels[0].source
    assert "bitcoin-1" in levels[1].source
    assert "bitcoin-2" in levels[2].source


# ----- Serialization ---------------------------------------------


@pytest.mark.asyncio
async def test_keylevel_to_dict_matches_adr_083_d3_shape() -> None:
    session = _mock_session_with_rows(
        [("bitcoin-above-76k", "BTC > 76k?", [0.92, 0.08], 200_000.0, _NOW)]
    )
    levels = await compute_polymarket_decision_levels(session)
    d = levels[0].to_dict()
    assert set(d.keys()) >= {"asset", "level", "kind", "side", "source"}
    assert d["asset"] == "USD"
    assert d["kind"] == "polymarket_decision"
    assert "polymarket" in d["source"]
