"""Tests for ``dimension_vote`` (ADR-120, Chantier C slice-0).

Pure-core contract for one analysis dimension's vote. Numeric assertions are
hand-computed; the ADR-017 (no-tilt for non-directional) and ADR-103 (honest
absence → 0) invariants are asserted directly.
"""

from __future__ import annotations

import pytest
from ichor_api.services.dimension_vote import (
    DimensionVote,
    effective_provenances,
    net_dimension_vote,
    total_uncertainty_credit,
)


class TestContract:
    def test_rejects_out_of_range_strength(self) -> None:
        with pytest.raises(ValueError, match="strength"):
            DimensionVote("x", "up", 1.5)
        with pytest.raises(ValueError, match="strength"):
            DimensionVote("x", "up", -0.1)

    def test_rejects_out_of_range_freshness(self) -> None:
        with pytest.raises(ValueError, match="freshness"):
            DimensionVote("x", "up", 0.5, freshness=1.1)

    def test_non_directional_must_be_neutral(self) -> None:
        with pytest.raises(ValueError, match="non-directional"):
            DimensionVote("theme", "up", 0.5, directional=False)
        # neutral + non-directional is fine
        assert DimensionVote("theme", "neutral", 0.5, directional=False).provenance == "theme"


class TestIsEffective:
    def test_present_nonzero_is_effective(self) -> None:
        assert DimensionVote("c", "up", 0.8).is_effective is True

    def test_absent_is_not_effective(self) -> None:
        assert DimensionVote("c", "up", 0.8, honest_absence=True).is_effective is False

    def test_zero_strength_or_freshness_not_effective(self) -> None:
        assert DimensionVote("c", "up", 0.0).is_effective is False
        assert DimensionVote("c", "up", 0.8, freshness=0.0).is_effective is False


class TestSignedContribution:
    def test_up_is_positive(self) -> None:
        assert DimensionVote("c", "up", 0.8).signed_contribution() == pytest.approx(0.8)

    def test_down_is_negative(self) -> None:
        assert DimensionVote("c", "down", 0.5).signed_contribution() == pytest.approx(-0.5)

    def test_freshness_scales(self) -> None:
        # up 0.8 × freshness 0.5 = 0.4
        assert DimensionVote("c", "up", 0.8, freshness=0.5).signed_contribution() == pytest.approx(
            0.4
        )

    def test_neutral_is_zero(self) -> None:
        assert DimensionVote("c", "neutral", 0.9).signed_contribution() == 0.0

    def test_non_directional_is_zero(self) -> None:
        assert (
            DimensionVote("theme", "neutral", 0.9, directional=False).signed_contribution() == 0.0
        )

    def test_absent_is_zero(self) -> None:
        assert DimensionVote("c", "up", 0.9, honest_absence=True).signed_contribution() == 0.0


class TestUncertaintyCredit:
    def test_neutral_present_gives_credit(self) -> None:
        # neutral 0.6 × fresh 1.0 = 0.6
        assert DimensionVote("c", "neutral", 0.6).uncertainty_credit() == pytest.approx(0.6)

    def test_non_directional_present_gives_credit(self) -> None:
        assert DimensionVote("theme", "neutral", 0.5, directional=False).uncertainty_credit() == (
            pytest.approx(0.5)
        )

    def test_directional_vote_gives_no_uncertainty_credit(self) -> None:
        # an up/down vote contributes to direction, not to the uncertainty term
        assert DimensionVote("c", "up", 0.8).uncertainty_credit() == 0.0

    def test_absent_gives_no_credit(self) -> None:
        assert DimensionVote("c", "neutral", 0.6, honest_absence=True).uncertainty_credit() == 0.0


class TestAggregation:
    def _votes(self) -> list[DimensionVote]:
        return [
            DimensionVote("confluence", "up", 0.8),  # +0.8
            DimensionVote("rates", "down", 0.5),  # -0.5
            DimensionVote("geopolitics", "up", 0.4, freshness=0.5),  # +0.2
            DimensionVote("theme", "neutral", 0.6, directional=False),  # 0 (credit 0.6)
            DimensionVote("positioning", "up", 0.9, honest_absence=True),  # 0 (absent)
        ]

    def test_net_vote_sums_signed(self) -> None:
        # 0.8 - 0.5 + 0.2 + 0 + 0 = 0.5
        assert net_dimension_vote(self._votes()) == pytest.approx(0.5)

    def test_total_uncertainty_credit(self) -> None:
        # only the theme layer contributes credit = 0.6
        assert total_uncertainty_credit(self._votes()) == pytest.approx(0.6)

    def test_effective_provenances_excludes_absent_and_zero(self) -> None:
        # absent positioning excluded; all others effective (incl. neutral theme)
        assert effective_provenances(self._votes()) == (
            "confluence",
            "rates",
            "geopolitics",
            "theme",
        )

    def test_empty_aggregations(self) -> None:
        assert net_dimension_vote([]) == 0.0
        assert total_uncertainty_credit([]) == 0.0
        assert effective_provenances([]) == ()
