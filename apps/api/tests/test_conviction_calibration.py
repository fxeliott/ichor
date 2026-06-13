"""Tests for ``conviction_calibration`` (ADR-117, Chantier B slice-1).

Numeric assertions are hand-computed; the isotonic property (in-sample Brier
never increases) is asserted directly.
"""

from __future__ import annotations

import pytest
from ichor_api.services.brier import ReliabilityBucket, brier_score, reliability_buckets
from ichor_api.services.conviction_calibration import (
    CalibrationPoint,
    CalibratorSelection,
    ConvictionCalibrator,
    PlattCalibrator,
    RegularizationSelection,
    _pav,
    brier_improvement,
    fit_from_pairs,
    fit_from_reliability,
    fit_platt,
    fit_regularized,
    fit_regularized_from_pairs,
    select_calibrator_oos,
    select_regularization_oos,
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


class TestRegularizedFit:
    """slice-2 (ADR-118): isotonic shrunk toward identity by lambda = N/(N+k).
    The slice-1 witness showed the raw isotonic overfits the thin history; the
    shrinkage pulls a noisy fit back toward 'no correction'."""

    def test_k_zero_recovers_isotonic(self) -> None:
        # lambda = N/(N+0) = 1 → full isotonic, identical to slice-1 fit
        buckets = [_bucket(0.6, 0.7, 10), _bucket(0.9, 0.5, 10)]
        raw = fit_from_reliability(buckets)
        reg = fit_regularized(buckets, k=0.0)
        assert [p.calibrated_p_up for p in reg.points] == pytest.approx(
            [p.calibrated_p_up for p in raw.points]
        )

    def test_lambda_formula_blends_knot(self) -> None:
        # N = 10+10 = 20, k = 20 → lambda = 20/40 = 0.5. PAV on realised [0.7,0.5]
        # (decreasing) pools to [0.6,0.6]; knot raw=0.9 cal=0.6 →
        # blended = 0.5*0.9 + 0.5*0.6 = 0.75.
        reg = fit_regularized([_bucket(0.6, 0.7, 10), _bucket(0.9, 0.5, 10)], k=20.0)
        knot = next(p for p in reg.points if p.raw_p_up == pytest.approx(0.9))
        assert knot.calibrated_p_up == pytest.approx(0.75)

    def test_large_k_shrinks_toward_identity(self) -> None:
        # N=20, k=1000 → lambda = 20/1020 ≈ 0.0196 → barely calibrated
        buckets = [_bucket(0.6, 0.7, 10), _bucket(0.9, 0.5, 10)]
        reg = fit_regularized(buckets, k=1000.0)
        knot = next(p for p in reg.points if p.raw_p_up == pytest.approx(0.9))
        lam = 20.0 / 1020.0
        assert knot.calibrated_p_up == pytest.approx((1 - lam) * 0.9 + lam * 0.6)
        assert knot.calibrated_p_up > 0.88  # very close to the raw 0.9 (identity)

    def test_small_n_is_near_identity(self) -> None:
        # the overfit antidote: N=4 with default k=50 → lambda = 4/54 ≈ 0.074
        buckets = [_bucket(0.6, 0.7, 2), _bucket(0.9, 0.5, 2)]
        reg = fit_regularized(buckets)  # default k = 50
        knot = next(p for p in reg.points if p.raw_p_up == pytest.approx(0.9))
        lam = 4.0 / (4.0 + 50.0)
        assert knot.calibrated_p_up == pytest.approx((1 - lam) * 0.9 + lam * 0.6)
        assert knot.calibrated_p_up > 0.85  # far closer to identity than raw fit 0.6

    def test_identity_base_stays_identity(self) -> None:
        # single populated bin → base identity → regularized identity for any k
        assert fit_regularized([_bucket(0.9, 0.5)], k=10.0).is_identity
        assert fit_regularized_from_pairs([], k=10.0).is_identity

    def test_regularized_preserves_monotonicity(self) -> None:
        buckets = [_bucket(0.2, 0.4, 5), _bucket(0.5, 0.3, 5), _bucket(0.8, 0.9, 5)]
        cals = [p.calibrated_p_up for p in fit_regularized(buckets, k=15.0).points]
        assert cals == sorted(cals)  # non-decreasing (convex blend of two isotone maps)

    def test_within_range_equals_true_blend(self) -> None:
        # knot-blend interpolation == (1-lam)*p + lam*base.apply(p) inside the range
        buckets = [_bucket(0.4, 0.5, 10), _bucket(0.8, 0.6, 10)]  # N=20, k=20 → lam=0.5
        base = fit_from_reliability(buckets)
        reg = fit_regularized(buckets, k=20.0)
        p = 0.6  # strictly inside [0.4, 0.8]
        assert reg.apply(p) == pytest.approx(0.5 * p + 0.5 * base.apply(p))

    def test_from_pairs_matches_buckets(self) -> None:
        pairs = [(0.9, 0), (0.9, 1), (0.6, 1), (0.6, 0), (0.3, 0), (0.3, 1)]
        buckets = reliability_buckets([p for p, _ in pairs], [y for _, y in pairs], n_bins=10)
        assert [p.calibrated_p_up for p in fit_regularized_from_pairs(pairs, k=5.0).points] == (
            pytest.approx([p.calibrated_p_up for p in fit_regularized(buckets, k=5.0).points])
        )

    def test_invariants_carry_through_blend(self) -> None:
        # ADR-017 no-flip carries through the shrinkage (k=0 → sharp full isotonic)
        buckets = [_bucket(0.5, 0.5, 10), _bucket(0.95, 0.2, 10)]  # very over-confident
        reg = fit_regularized(buckets, k=0.0)
        # long 90 → p_up 0.95 → apply ~0.2 (wrong side of 0.5) → conviction 0, no flip
        assert reg.calibrate_conviction("long", 90.0) == 0.0


class TestSelectRegularizationOos:
    """The honest arbiter: choose k (incl. 'no calibration') by OUT-OF-SAMPLE
    Brier on a disjoint split — never in-sample (ADR-116/117)."""

    def test_picks_full_isotonic_when_it_beats_identity_oos(self) -> None:
        # train: 0.9-forecasts realise 50% up, 0.1-forecasts realise 50% up →
        # full isotonic (k=0) maps everything to 0.5. test mirrors the regime.
        train = [(0.9, 1), (0.9, 0), (0.9, 1), (0.9, 0), (0.1, 0), (0.1, 1), (0.1, 0), (0.1, 1)]
        test = [(0.9, 0), (0.9, 1), (0.1, 1), (0.1, 0)]
        sel = select_regularization_oos(train, test, [0.0, 5.0, 50.0])
        assert sel is not None
        # identity test Brier = (0.81+0.01+0.81+0.01)/4 = 0.41 ; k=0 maps all→0.5 → 0.25
        assert sel.identity_test_brier == pytest.approx(0.41)
        assert sel.best_k == 0.0
        assert sel.best_test_brier == pytest.approx(0.25)
        assert sel.improved is True

    def test_declines_to_calibrate_when_nothing_helps_oos(self) -> None:
        # well-calibrated train (0.7→2/3 up, 0.3→1/3 up) → any fit only hurts OOS
        train = [(0.7, 1), (0.7, 1), (0.7, 0), (0.3, 0), (0.3, 0), (0.3, 1)]
        test = [(0.7, 1), (0.3, 0)]
        sel = select_regularization_oos(train, test, [0.0, 10.0])
        assert sel is not None
        assert sel.identity_test_brier == pytest.approx(0.09)  # (0.09+0.09)/2
        assert sel.best_k is None  # honest: declines to calibrate
        assert sel.improved is False

    def test_identity_always_a_candidate(self) -> None:
        sel = select_regularization_oos([(0.8, 1), (0.2, 0)], [(0.8, 0)], [5.0])
        assert sel is not None
        assert None in [k for k, _ in sel.table]

    def test_empty_split_returns_none(self) -> None:
        assert select_regularization_oos([], [(0.5, 1)], [1.0]) is None
        assert select_regularization_oos([(0.5, 1)], [], [1.0]) is None

    def test_selection_is_typed(self) -> None:
        sel = select_regularization_oos([(0.8, 1), (0.2, 0)], [(0.8, 0)], [5.0])
        assert isinstance(sel, RegularizationSelection)


class TestPlatt:
    """slice-3 (ADR-118): Platt's 2-parameter sigmoid (Lin, Lin & Weng 2007) —
    the literature's low-variance choice for a small calibration set."""

    def test_empty_or_single_class_is_none(self) -> None:
        assert fit_platt([]) is None
        assert fit_platt([(0.9, 1), (0.6, 1)]) is None  # all positive → unidentifiable
        assert fit_platt([(0.9, 0), (0.6, 0)]) is None  # all negative → unidentifiable

    def test_monotone_increasing_on_separable(self) -> None:
        # higher score ↔ higher outcome → fitted map is increasing
        cal = fit_platt([(0.9, 1), (0.8, 1), (0.7, 1), (0.3, 0), (0.2, 0), (0.1, 0)])
        assert cal is not None
        assert cal.apply(0.2) < cal.apply(0.5) < cal.apply(0.9)

    def test_apply_strictly_in_unit_interval(self) -> None:
        cal = fit_platt([(0.95, 1), (0.05, 0), (0.6, 1), (0.4, 0)])
        assert cal is not None
        for p in (0.0, 0.5, 1.0):
            assert 0.0 < cal.apply(p) < 1.0

    def test_shrinks_overconfident_forecasts(self) -> None:
        # 0.9-forecasts realise only ~50% → Platt pulls a 0.9 down toward 0.5
        pairs = [(0.9, 1), (0.9, 0), (0.9, 1), (0.9, 0), (0.1, 1), (0.1, 0), (0.1, 1), (0.1, 0)]
        cal = fit_platt(pairs)
        assert cal is not None
        assert cal.apply(0.9) < 0.75
        assert cal.apply(0.1) > 0.25

    def test_deterministic(self) -> None:
        pairs = [(0.8, 1), (0.2, 0), (0.6, 1), (0.4, 0)]
        c1, c2 = fit_platt(pairs), fit_platt(pairs)
        assert c1 is not None and c2 is not None
        assert (c1.a, c1.b) == (c2.a, c2.b)

    def test_numerically_stable_on_extremes(self) -> None:
        cal = fit_platt([(1.0, 1), (0.0, 0), (0.99, 1), (0.01, 0)])
        assert cal is not None
        assert 0.0 < cal.apply(1.0) < 1.0
        assert 0.0 < cal.apply(0.0) < 1.0

    def test_reduces_brier_on_miscalibrated_data(self) -> None:
        # an inverted (strongly miscalibrated) set: high score ↔ low outcome. A
        # 2-param sigmoid fixes the global bias → STRICT Brier reduction with a
        # real margin (a degenerate a≈0,b≈0 fit would only tie raw — rejected).
        pairs = [(0.9, 1), (0.9, 0), (0.9, 0), (0.1, 0), (0.1, 1), (0.1, 1)]
        cal = fit_platt(pairs)
        assert cal is not None
        assert cal.a != 0.0  # non-degenerate fit
        raw, calibrated = brier_improvement(pairs, cal)
        assert calibrated < raw - 0.10  # raw≈0.543 → calibrated≈0.227 (Δ≈0.32)

    def test_calibrate_conviction_no_flip(self) -> None:
        # a>0 → decreasing map: long 90 → p_up 0.95 → apply<0.5 (wrong side) → 0
        cal = PlattCalibrator(a=2.0, b=-1.0)
        assert cal.apply(0.95) < 0.5
        assert cal.calibrate_conviction("long", 90.0) == 0.0

    def test_calibrate_conviction_caps_at_95(self) -> None:
        # a strongly increasing map pushing a modest long to near-certainty caps
        cal = PlattCalibrator(a=-20.0, b=9.0)  # apply(0.7) ≈ 1/(1+e^{-5}) ≈ 0.993
        assert cal.calibrate_conviction("long", 40.0) == 95.0


class TestSelectCalibratorOos:
    """Cross-family OOS arbiter: identity vs regularised isotonic vs Platt."""

    def test_picks_a_calibrator_when_it_beats_identity_oos(self) -> None:
        train = [(0.9, 1), (0.9, 0), (0.9, 1), (0.9, 0), (0.1, 0), (0.1, 1), (0.1, 0), (0.1, 1)]
        test = [(0.9, 0), (0.9, 1), (0.1, 1), (0.1, 0)]
        sel = select_calibrator_oos(train, test, ks=(0.0, 50.0))
        assert sel is not None
        assert sel.identity_test_brier == pytest.approx(0.41)
        assert sel.best_test_brier < sel.identity_test_brier  # 0.25 (maps→0.5) < 0.41
        assert sel.best_test_brier < 0.30
        assert sel.improved is True
        labels = [lbl for lbl, _ in sel.table]
        assert "identity" in labels and "platt" in labels

    def test_declines_when_already_calibrated(self) -> None:
        train = [(0.7, 1), (0.7, 1), (0.7, 0), (0.3, 0), (0.3, 0), (0.3, 1)]
        test = [(0.7, 1), (0.3, 0)]
        sel = select_calibrator_oos(train, test, ks=(0.0,))
        assert sel is not None
        assert sel.best_label == "identity"
        assert sel.improved is False

    def test_platt_can_win_the_cross_family_search(self) -> None:
        # a SMOOTH global over-confidence bias across many distinct levels: the
        # binned isotonic overfits the per-bin noise (worse OOS than identity),
        # while Platt's 2-param sigmoid generalises and STRICTLY wins — the exact
        # Niculescu-Mizil & Caruana 2005 small-N regime. Pins the best_label='platt'
        # selection branch.
        train = [
            (0.95, 1),
            (0.95, 0),
            (0.85, 1),
            (0.85, 1),
            (0.75, 0),
            (0.75, 1),
            (0.65, 1),
            (0.65, 0),
            (0.35, 1),
            (0.35, 0),
            (0.25, 0),
            (0.25, 1),
            (0.15, 0),
            (0.15, 0),
            (0.05, 1),
            (0.05, 0),
        ]
        test = [
            (0.95, 1),
            (0.85, 0),
            (0.75, 1),
            (0.65, 1),
            (0.35, 0),
            (0.25, 0),
            (0.15, 0),
            (0.05, 1),
        ]
        sel = select_calibrator_oos(train, test, ks=(0.0, 5.0, 20.0, 50.0))
        assert sel is not None
        assert sel.best_label == "platt"
        assert sel.improved is True
        # Platt strictly beats identity AND every isotonic candidate OOS
        non_platt = [b for lbl, b in sel.table if lbl != "platt"]
        assert sel.best_test_brier < min(non_platt)

    def test_empty_split_returns_none(self) -> None:
        assert select_calibrator_oos([], [(0.5, 1)]) is None
        assert select_calibrator_oos([(0.5, 1)], []) is None

    def test_selection_is_typed(self) -> None:
        sel = select_calibrator_oos([(0.8, 1), (0.2, 0)], [(0.8, 0)])
        assert isinstance(sel, CalibratorSelection)
