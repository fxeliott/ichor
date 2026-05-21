"""Pure tests for the surprise index z-score helpers + render."""

from __future__ import annotations

import pytest
from ichor_api.services.surprise_index import (
    _GROWTH_SERIES,
    _INFLATION_SERIES,
    SeriesSurprise,
    SurpriseIndexReading,
    _band,
    _to_period_changes,
    _z_score,
    render_surprise_index_block,
)

# ─────────────── growth/inflation composite split (r135) ────────────────


def test_growth_and_inflation_series_are_disjoint() -> None:
    # trader MUST-FIX : the composite must never blend the two regime axes.
    assert _GROWTH_SERIES.isdisjoint(_INFLATION_SERIES)


def test_inflation_series_excluded_from_growth_composite() -> None:
    # CPI/PCE are inflation → must NOT be in the growth composite set
    # (they leak a hot-inflation print in as "growth-bullish" otherwise).
    assert "CPIAUCSL" in _INFLATION_SERIES
    assert "PCEPI" in _INFLATION_SERIES
    assert "CPIAUCSL" not in _GROWTH_SERIES
    assert "PCEPI" not in _GROWTH_SERIES
    # Growth/labor series ARE in the composite.
    assert {"PAYEMS", "UNRATE", "INDPRO", "GDPC1"} <= _GROWTH_SERIES


def test_change_zscore_boundary_at_min_history() -> None:
    # 6 levels → 5 changes → _z_score computes (≥5 ok). 5 levels → 4
    # changes → None. Pins the exact "index lights up" threshold.
    six_levels = [1.0, 2.0, 4.0, 7.0, 11.0, 20.0]  # 5 changes, varied
    last6, mean6, std6 = _z_score(_to_period_changes(six_levels))
    assert last6 is not None and mean6 is not None and std6 is not None and std6 > 0
    five_levels = [1.0, 2.0, 4.0, 7.0, 11.0]  # 4 changes → < 5 → None
    last5, mean5, std5 = _z_score(_to_period_changes(five_levels))
    assert last5 is None and mean5 is None and std5 is None


# ──────────────────── _to_period_changes (r135) ────────────────────────


def test_to_period_changes_basic() -> None:
    # [10, 12, 11, 15] → [+2, -1, +4]
    assert _to_period_changes([10.0, 12.0, 11.0, 15.0]) == [2.0, -1.0, 4.0]


def test_to_period_changes_empty_and_singleton() -> None:
    assert _to_period_changes([]) == []
    assert _to_period_changes([42.0]) == []  # need ≥2 levels for 1 change


def test_to_period_changes_len_is_n_minus_1() -> None:
    levels = [float(i) for i in range(25)]
    changes = _to_period_changes(levels)
    assert len(changes) == 24  # 25 levels → 24 changes (Citi window)
    assert all(c == 1.0 for c in changes)  # monotone +1 each step


def test_change_zscore_neutralises_trend_dominated_level() -> None:
    """r135 core fix : a steadily-trending series (like a CPI index) must
    NOT register as a perpetual surprise. Z-scoring the LEVEL would pin
    the latest (highest) print at a high z every period ; z-scoring the
    CHANGE of a constant-slope trend yields ~0 (no surprise)."""
    # CPI-like index rising a steady +0.5 every month for 25 months.
    levels = [300.0 + 0.5 * i for i in range(25)]
    # OLD (level) behaviour would flag the last as a positive outlier:
    last_lvl, _, _ = _z_score(levels)
    assert last_lvl == levels[-1]  # level path: last is the max → high z
    # NEW (change) behaviour : every change is +0.5 → zero variance →
    # honestly "no surprise" (None), not a fake +1.7σ.
    changes = _to_period_changes(levels)
    last_chg, mean_chg, std_chg = _z_score(changes)
    assert last_chg is None  # constant change → std 0 → no surprise
    assert std_chg == pytest.approx(0.0)


def test_change_zscore_flags_genuine_acceleration() -> None:
    """A real surprise = the latest CHANGE breaks the change-distribution.
    Noisy ~+0.5 changes (so std > 0) then a sudden +3.0 jump → strong
    positive z. (Prior changes must vary — a perfectly constant trend has
    zero variance and is correctly read as 'no surprise', see the test
    above.)"""
    levels = [300.0]
    for i in range(23):  # 23 noisy prior changes around +0.5
        levels.append(levels[-1] + (0.4 if i % 2 == 0 else 0.6))
    levels.append(levels[-1] + 3.0)  # the genuine acceleration
    changes = _to_period_changes(levels)
    assert len(changes) == 24
    last, mean, std = _z_score(changes)
    assert last == pytest.approx(3.0)
    assert mean is not None and mean == pytest.approx(0.5, abs=0.05)
    assert std is not None and std > 0
    z = (last - mean) / std
    assert z > 1.5  # genuine upside surprise in the change distribution


# ─────────────────────────── _z_score ──────────────────────────────────


def test_z_score_returns_nones_on_short_history() -> None:
    last, mean, std = _z_score([1.0, 2.0, 3.0])
    assert last is None and mean is None and std is None


def test_z_score_returns_nones_on_zero_std() -> None:
    last, mean, std = _z_score([1.0] * 8)
    assert last is None  # std is 0
    assert mean == pytest.approx(1.0)
    assert std == pytest.approx(0.0)


def test_z_score_basic_positive_outlier() -> None:
    history = [10.0, 10.5, 9.5, 10.2, 9.8, 10.1, 15.0]
    last, mean, std = _z_score(history)
    assert last == 15.0
    assert mean is not None and 9.5 < mean < 10.5
    assert std is not None and std > 0


# ─────────────────────────── _band ─────────────────────────────────────


def test_band_neutral_zone() -> None:
    assert _band(0.3) == "neutral"
    assert _band(-0.4) == "neutral"
    assert _band(None) == "neutral"


def test_band_positive_thresholds() -> None:
    assert _band(0.6) == "positive"
    assert _band(1.4) == "positive"
    assert _band(1.6) == "strong_positive"
    assert _band(3.0) == "strong_positive"


def test_band_negative_thresholds() -> None:
    assert _band(-0.6) == "negative"
    assert _band(-1.4) == "negative"
    assert _band(-1.6) == "strong_negative"
    assert _band(-3.0) == "strong_negative"


# ─────────────────────────── render ────────────────────────────────────


def test_render_insufficient_history() -> None:
    r = SurpriseIndexReading(
        region="US",
        composite=None,
        band="neutral",
        series=[],
        n_series_used=0,
    )
    md, sources = render_surprise_index_block(r)
    assert "insufficient" in md.lower()
    assert sources == []


def test_render_full_payload() -> None:
    r = SurpriseIndexReading(
        region="US",
        composite=0.8,
        band="positive",
        series=[
            SeriesSurprise(
                series_id="PAYEMS",
                label="Nonfarm payrolls",
                last_value=160_000_000,
                rolling_mean=158_000_000,
                rolling_std=500_000,
                z_score=4.0,
                n_history=24,
            ),
            SeriesSurprise(
                series_id="UNRATE",
                label="Unemployment rate",
                last_value=3.6,
                rolling_mean=4.0,
                rolling_std=0.2,
                z_score=2.0,
                n_history=24,
            ),
        ],
        n_series_used=2,
    )
    md, sources = render_surprise_index_block(r)
    assert "Growth-surprise composite" in md  # r135 — was "Composite z-score"
    assert "+0.80" in md
    assert "positive" in md
    assert "PAYEMS" in md
    assert "UNRATE" in md
    assert "FRED:PAYEMS" in sources
    assert "FRED:UNRATE" in sources


def test_render_handles_n_a_z_score_per_series() -> None:
    r = SurpriseIndexReading(
        region="US",
        composite=0.2,
        band="neutral",
        series=[
            SeriesSurprise(
                series_id="GDPC1",
                label="Real GDP",
                last_value=None,
                rolling_mean=None,
                rolling_std=None,
                z_score=None,
                n_history=2,
            ),
        ],
        n_series_used=0,
    )
    md, sources = render_surprise_index_block(r)
    assert "GDPC1" in md
    assert "n/a" in md
    assert "FRED:GDPC1" in sources
