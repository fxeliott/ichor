"""Tests for the feature-flag admin CLI (pure arg/validation + the dimension SSOT)."""

from __future__ import annotations

import pytest
from ichor_api.cli.run_set_feature_flag import _dimension_flags, main


def test_dimension_flags_are_the_ten_s04_votes() -> None:
    """The CLI's dimension list must match the producer flag constants EXACTLY (SSOT —
    a drift would let the operator activate a non-existent / wrong flag)."""
    keys = set(_dimension_flags())
    assert keys == {
        "cot_dimension_vote_enabled",
        "volume_dimension_vote_enabled",
        "geopolitics_dimension_vote_enabled",
        "positioning_tff_dimension_vote_enabled",
        "sentiment_dimension_vote_enabled",
        "vol_regime_dimension_vote_enabled",
        "positioning_divergence_dimension_vote_enabled",
        "manipulation_liquidity_dimension_vote_enabled",
        "correlations_dimension_vote_enabled",
        "real_yield_dimension_vote_enabled",
    }


def test_doubt_votes_listed_before_directional() -> None:
    """Recommended order: the 4 DOUBT votes (lower conviction only → safest) come first."""
    order = list(_dimension_flags())
    assert order[:4] == [
        "vol_regime_dimension_vote_enabled",
        "manipulation_liquidity_dimension_vote_enabled",
        "correlations_dimension_vote_enabled",
        "positioning_divergence_dimension_vote_enabled",
    ]
    # the directional ones are last
    assert order[-1] == "real_yield_dimension_vote_enabled"


def test_rollout_out_of_range_is_rejected() -> None:
    with pytest.raises(SystemExit):
        main(["some_flag", "--on", "--rollout", "200"])
    with pytest.raises(SystemExit):
        main(["some_flag", "--on", "--rollout", "-5"])


def test_on_and_off_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        main(["some_flag", "--on", "--off"])


def test_toggle_without_on_or_off_is_bad_usage() -> None:
    # Neither --on nor --off + a key → bad usage (parser.error → SystemExit, no DB touch).
    with pytest.raises(SystemExit):
        main(["some_flag"])


def test_toggle_without_key_is_bad_usage() -> None:
    with pytest.raises(SystemExit):
        main(["--on"])
