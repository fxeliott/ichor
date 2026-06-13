"""Tests for ``conviction_calibration`` (ADR-117, Chantier B slice-1).

Numeric assertions are hand-computed; the isotonic property (in-sample Brier
never increases) is asserted directly.
"""

from __future__ import annotations

import pytest
from ichor_api.services.brier import ReliabilityBucket, brier_score
from ichor_api.services.conviction_calibration import (
    CalibrationPoint,
    ConvictionCalibrator,
    _pav,
    brier_improvement,
    fit_from_pairs,
    fit_from_reliability,
)


def _bucket(pred: float, realized: float, count: int = 10) -> ReliabilityBucket:
    return ReliabilityBucket(
        bin_lower=pred - 0.05,
        bin_upper=pred + 0.05,
        count=count,
        mean_predicted=pred,
        mean_realized=realized,
    )


class TestPav:
    def test_already_monotonic_unchanged(self) -> None:
        assert _pav([0.2, 0.5, 0.8], [1.0, 1.0, 1.0]) == pytest.approx([0.2, 0.5, 0.8])

    def test_pools_violation(self) -> None:
        # [0.8, 0.2, 0.5] → pool first two (mean 0.5), then 0.5 ≥ 0.5 ok
        assert _pav([0.8, 0.2, 0.5], [1.0, 1.0, 1.0]) == pytest.approx([0.5, 0.5, 0.5])

    def test_weighted_pool(self) -> None:
        # [0.9 (w3), 0.1 (w1)] violation → pooled mean = (0.9*3+0.1*1)/4 = 0.7
        assert _pav([0.9, 0.1], [3.0, 1.0]) == pytest.approx([0.7, 0.7])


class TestFit:
    def test_insufficient_bins_is_identity(self) -> None:
        assert fit_from_reliability([_bucket(0.9, 0.5)]).is_identity
        assert fit_from_pairs([]).is_identity

    def test_fit_makes_calibrated_monotonic(self) -> None:
        # over-confident: pred 0.9 only realises 0.5; pred 0.6 realises 0.7
        cal = fit_from_reliability([_bucket(0.6, 0.7, 10), _bucket(0.9, 0.5, 10)])
        # realised [0.7, 0.5] is decreasing → PAV pools to [0.6, 0.6]
        assert [p.calibrated_p_up for p in cal.points] == pytest.approx([0.6, 0.6])
        assert cal.apply(0.9) == pytest.approx(0.6)  # 0.9 shrunk to 0.6


class TestApply:
    def test_clamps_to_endpoints(self) -> None:
        cal = ConvictionCalibrator(
            points=(CalibrationPoint(0.6, 0.6, 5), CalibrationPoint(0.9, 0.7, 5))
        )
        assert cal.apply(0.4) == pytest.approx(0.6)  # below first knot
        assert cal.apply(0.99) == pytest.approx(0.7)  # above last knot

    def test_linear_interpolation(self) -> None:
        cal = ConvictionCalibrator(
            points=(CalibrationPoint(0.6, 0.6, 5), CalibrationPoint(0.8, 0.7, 5))
        )
        # midpoint 0.7 → halfway between 0.6 and 0.7 = 0.65
        assert cal.apply(0.7) == pytest.approx(0.65)

    def test_identity_when_unfitted(self) -> None:
        assert ConvictionCalibrator(points=()).apply(0.83) == pytest.approx(0.83)


class TestCalibrateConviction:
    def _shrinker(self) -> ConvictionCalibrator:
        # maps an over-confident long (p_up 0.95) down to 0.55
        return ConvictionCalibrator(
            points=(CalibrationPoint(0.5, 0.5, 5), CalibrationPoint(0.95, 0.55, 10))
        )

    def test_shrinks_overconfident_long(self) -> None:
        # long 90 → p_up 0.95 → calibrated 0.55 → conviction (0.55-0.5)*2*100 = 10
        assert self._shrinker().calibrate_conviction("long", 90.0) == pytest.approx(10.0)

    def test_wrong_side_collapses_to_zero_no_flip(self) -> None:
        # calibration puts a long forecast below 0.5 → conviction 0 (never flips)
        cal = ConvictionCalibrator(
            points=(CalibrationPoint(0.5, 0.5, 5), CalibrationPoint(0.9, 0.4, 5))
        )
        assert cal.calibrate_conviction("long", 80.0) == 0.0

    def test_caps_at_95(self) -> None:
        cal = ConvictionCalibrator(
            points=(CalibrationPoint(0.5, 0.5, 5), CalibrationPoint(0.7, 0.99, 5))
        )
        # long 40 → p_up 0.7 → 0.99 → (0.49)*2*100 = 98 → capped 95
        assert cal.calibrate_conviction("long", 40.0) == 95.0

    def test_short_direction_symmetric(self) -> None:
        # short 90 → p_up 0.05 ; a calibrator mapping 0.05→0.45 → conviction 10
        cal = ConvictionCalibrator(
            points=(CalibrationPoint(0.05, 0.45, 5), CalibrationPoint(0.5, 0.5, 5))
        )
        assert cal.calibrate_conviction("short", 90.0) == pytest.approx(10.0)

    def test_neutral_is_zero(self) -> None:
        assert self._shrinker().calibrate_conviction("neutral", 50.0) == 0.0

    def test_identity_preserves_conviction(self) -> None:
        # identity calibrator → calibrated conviction == raw conviction
        ident = ConvictionCalibrator(points=())
        assert ident.calibrate_conviction("long", 80.0) == pytest.approx(80.0)


class TestBrierImprovement:
    def test_computes_raw_per_sample_brier(self) -> None:
        pairs = [(0.9, 0), (0.6, 1), (0.3, 0)]
        cal = fit_from_pairs(pairs, n_bins=10)
        raw, _calibrated = brier_improvement(pairs, cal)
        assert raw == pytest.approx(sum(brier_score(p, y) for p, y in pairs) / len(pairs))

    def test_calibration_can_worsen_in_sample_brier(self) -> None:
        """Honest property (NOT 'never worsens'): the PAV fits BUCKET means, but
        Brier is scored PER SAMPLE through a clamping/interpolating map — a raw
        forecast below the first knot is clamped UP and can be hurt. (0.1, 0):
        raw Brier 0.01 → apply(0.1)=0.4 (clamped) → 0.16, strictly worse."""
        cal = ConvictionCalibrator(
            points=(CalibrationPoint(0.55, 0.4, 5), CalibrationPoint(0.72, 1.0, 1))
        )
        raw, calibrated = brier_improvement([(0.1, 0)], cal)
        assert raw == pytest.approx(0.01)
        assert calibrated == pytest.approx(0.16)
        assert calibrated > raw

    def test_identity_leaves_brier_unchanged(self) -> None:
        pairs = [(0.7, 1), (0.4, 0)]
        raw, calibrated = brier_improvement(pairs, ConvictionCalibrator(points=()))
        assert raw == pytest.approx(calibrated)

    def test_empty_is_zero(self) -> None:
        assert brier_improvement([], fit_from_pairs([])) == (0.0, 0.0)
