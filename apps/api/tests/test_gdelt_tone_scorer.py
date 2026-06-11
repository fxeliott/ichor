"""Tests for the local GDELT tone scorer (ADR-112).

Pure-function coverage of the distribution→tone mapping plus the scale
contract the consumers depend on (TARIFF_SHOCK threshold −1.5, heatmap
bands, most-negative ranking all assume the GDELT-like −10..+10 scale).
"""

from __future__ import annotations

import pytest
from ichor_api.cli.run_gdelt_tone_scorer import (
    _GDELT_SCALE,
    _LANGUAGE_EN,
    _MAX_AGE_HOURS,
    tone_from_distribution,
)


class TestToneFromDistribution:
    def test_strong_negative_maps_to_gdelt_scale(self) -> None:
        # A clearly negative headline: p_neg 0.92 / p_pos 0.03.
        tone = tone_from_distribution({"positive": 0.03, "neutral": 0.05, "negative": 0.92})
        assert tone == pytest.approx((0.03 - 0.92) * 10.0)
        assert -10.0 <= tone <= -8.0

    def test_strong_positive(self) -> None:
        tone = tone_from_distribution({"positive": 0.9, "neutral": 0.08, "negative": 0.02})
        assert tone == pytest.approx(8.8)

    def test_neutral_lands_near_zero_not_at_confidence(self) -> None:
        # Ambivalent: barely-winning positive must NOT inherit full
        # confidence — the softmax difference keeps it near zero.
        tone = tone_from_distribution({"positive": 0.40, "neutral": 0.25, "negative": 0.35})
        assert abs(tone) < 1.0

    def test_bounded_in_gdelt_range(self) -> None:
        assert tone_from_distribution({"positive": 1.0, "negative": 0.0}) == _GDELT_SCALE
        assert tone_from_distribution({"positive": 0.0, "negative": 1.0}) == -_GDELT_SCALE

    def test_missing_keys_are_zero(self) -> None:
        # Defensive: a malformed distribution must not raise.
        assert tone_from_distribution({}) == 0.0

    def test_tariff_shock_threshold_reachable(self) -> None:
        """The consumer contract that motivated ADR-112: a moderately
        negative headline must be able to cross the TARIFF_SHOCK gate
        avg_tone <= -1.5 (impossible on the dead 0.0 column)."""
        tone = tone_from_distribution({"positive": 0.10, "neutral": 0.55, "negative": 0.35})
        assert tone <= -1.5


class TestScorerContract:
    def test_language_filter_is_long_form_english(self) -> None:
        # Prod stores the long-form name (witnessed 'English' 2,181 rows/48h),
        # NOT an ISO code — pin it so a refactor to 'en' fails loudly.
        assert _LANGUAGE_EN == "English"

    def test_rescan_window_mirrors_news_scorer(self) -> None:
        # 6h bounded retry window (run_news_tone_scorer pattern): rows
        # older than the window are left alone — never retried forever.
        assert _MAX_AGE_HOURS == 6
