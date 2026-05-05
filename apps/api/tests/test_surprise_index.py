"""Pure tests for the surprise index z-score helpers + render."""

from __future__ import annotations

import pytest
from ichor_api.services.surprise_index import (
    SeriesSurprise,
    SurpriseIndexReading,
    _band,
    _z_score,
    render_surprise_index_block,
)

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
    assert "Composite z-score" in md
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
