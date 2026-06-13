"""conviction_calibration.py — Chantier B slice-1 (ADR-117).

Pure-core, I/O-free. The first learning-loop slice: recalibrate Ichor's
conviction against its OWN realised track-record.

The benchmark witness (ADR-116) showed the verdict's conviction is poorly
calibrated — Brier 0.38 out-of-sample, worse than the 0.25 no-skill reference:
a "long 90 %" does not close up 90 % of the time. Nothing in the live pipeline
corrects this — ``brier.conviction_to_p_up`` is a fixed affine rule and
``conviction_fusion`` "intentionally takes no learned weight".

This module fits a monotonic (isotonic / pool-adjacent-violators) reliability
map from the EXISTING reliability buckets (``brier.reliability_buckets``: mean
forecast ``P_up`` vs mean realised ``y`` per bin) and applies it:
``raw P_up -> calibrated P_up -> calibrated conviction``. A historically
over-confident conviction is shrunk toward what actually happened.

Scope (ADR-117 slice-1): pure compute + read-only fit/apply only. **NO live
wiring** — the verdict still emits its raw conviction until a later GATED step
(deploy + witness that the calibrated Brier actually improves out-of-sample).
Mirrors the S04 ``conviction_fusion`` discipline: pure core first, gated
integration later.

Doctrine:
- ADR-009 (Voie D): zero LLM / IO / spend — pure arithmetic.
- ADR-017: direction stays bucket-derived; calibration only shrinks/grows the
  conviction MAGNITUDE, never flips a direction nor emits an order. If the
  calibration disagrees with the bias (calibrated ``P_up`` on the wrong side of
  0.5), conviction collapses to 0 rather than flipping.
- ADR-022: calibrated conviction clamped to 0..95.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

from .brier import (
    BiasDirection,
    ReliabilityBucket,
    brier_score,
    conviction_to_p_up,
    reliability_buckets,
)

_CONVICTION_CAP = 95.0
# Below this many populated reliability bins the fit is an identity map (an
# honest "not enough history to calibrate" rather than a noisy correction).
_MIN_BINS_TO_CALIBRATE = 2


@dataclass(frozen=True, slots=True)
class CalibrationPoint:
    """One fitted knot of the monotonic map: a raw forecast probability and the
    isotonic-adjusted realised frequency at that level."""

    raw_p_up: float
    calibrated_p_up: float
    weight: int


def _pav(values: list[float], weights: list[float]) -> list[float]:
    """Weighted pool-adjacent-violators → non-decreasing isotonic fit of
    ``values`` (one output per input, order preserved). Standard PAVA."""
    blocks: list[list[float]] = []  # each: [weighted_sum, weight, count]
    for v, w in zip(values, weights, strict=True):
        blocks.append([v * w, w, 1.0])
        while len(blocks) >= 2 and (blocks[-2][0] / blocks[-2][1]) > (
            blocks[-1][0] / blocks[-1][1]
        ):
            b2 = blocks.pop()
            b1 = blocks.pop()
            blocks.append([b1[0] + b2[0], b1[1] + b2[1], b1[2] + b2[2]])
    out: list[float] = []
    for wsum, w, count in blocks:
        out.extend([wsum / w] * int(count))
    return out


@dataclass(frozen=True, slots=True)
class ConvictionCalibrator:
    """A fitted monotonic ``raw_P_up -> calibrated_P_up`` map. ``points`` are
    sorted by ``raw_p_up`` ascending with non-decreasing ``calibrated_p_up``
    (isotonic). Empty ``points`` = identity (insufficient history → honest
    no-op)."""

    points: tuple[CalibrationPoint, ...]

    @property
    def is_identity(self) -> bool:
        return not self.points

    def apply(self, p_up: float) -> float:
        """Calibrated ``P_up`` for a raw forecast, by linear interpolation
        between fitted knots (clamped to the endpoints). Identity if unfitted."""
        pts = self.points
        if not pts:
            return p_up
        if p_up <= pts[0].raw_p_up:
            return pts[0].calibrated_p_up
        if p_up >= pts[-1].raw_p_up:
            return pts[-1].calibrated_p_up
        for lo, hi in pairwise(pts):
            if lo.raw_p_up <= p_up <= hi.raw_p_up:
                span = hi.raw_p_up - lo.raw_p_up
                if span <= 0.0:
                    return lo.calibrated_p_up
                t = (p_up - lo.raw_p_up) / span
                return lo.calibrated_p_up + t * (hi.calibrated_p_up - lo.calibrated_p_up)
        return p_up  # unreachable: the loop covers [pts[0], pts[-1]]

    def calibrate_conviction(self, bias: BiasDirection, conviction_pct: float) -> float:
        """Recalibrated conviction % for a ``(bias, conviction)``. Direction is
        UNCHANGED (ADR-017) — only the magnitude moves toward the realised
        reliability. If the calibration lands on the wrong side of 0.5 for the
        bias, conviction → 0 (no flip). Clamped 0..95 (ADR-022)."""
        if bias == "neutral":
            return 0.0
        calibrated = self.apply(conviction_to_p_up(bias, conviction_pct))
        signed = (calibrated - 0.5) if bias == "long" else (0.5 - calibrated)
        return min(_CONVICTION_CAP, max(0.0, signed * 2.0) * 100.0)


def fit_from_reliability(buckets: list[ReliabilityBucket]) -> ConvictionCalibrator:
    """Fit the monotonic calibrator from reliability buckets (raw
    ``mean_predicted`` → realised ``mean_realized``) via weighted isotonic PAV.
    Fewer than ``_MIN_BINS_TO_CALIBRATE`` populated bins → identity."""
    usable = sorted((b for b in buckets if b.count > 0), key=lambda b: b.mean_predicted)
    if len(usable) < _MIN_BINS_TO_CALIBRATE:
        return ConvictionCalibrator(points=())
    fitted = _pav([b.mean_realized for b in usable], [float(b.count) for b in usable])
    return ConvictionCalibrator(
        points=tuple(
            CalibrationPoint(raw_p_up=b.mean_predicted, calibrated_p_up=r, weight=b.count)
            for b, r in zip(usable, fitted, strict=True)
        )
    )


def fit_from_pairs(pairs: list[tuple[float, int]], *, n_bins: int = 10) -> ConvictionCalibrator:
    """Convenience: bin ``(p_up, y)`` pairs via ``brier.reliability_buckets`` then
    fit. Empty input → identity."""
    if not pairs:
        return ConvictionCalibrator(points=())
    buckets = reliability_buckets([p for p, _ in pairs], [y for _, y in pairs], n_bins=n_bins)
    return fit_from_reliability(buckets)


def brier_improvement(
    pairs: list[tuple[float, int]], calibrator: ConvictionCalibrator
) -> tuple[float, float]:
    """``(raw_mean_brier, calibrated_mean_brier)`` over ``(p_up, y)`` pairs — the
    headline "does calibration help" number.

    NOTE: in-sample is TYPICALLY but **NOT guaranteed** improved. The PAV fit
    minimises weighted error on the BUCKET MEANS, whereas this scores PER-SAMPLE
    Brier through a clamping + interpolating map — a raw forecast below the first
    knot (or between knots) can be moved adversely, so the calibrated in-sample
    Brier can be strictly worse (verifier-confirmed). The honest test is
    therefore OUT-OF-SAMPLE: the caller fits on a train split and measures on a
    disjoint test split (the witness).
    """
    if not pairs:
        return (0.0, 0.0)
    n = len(pairs)
    raw = sum(brier_score(p, y) for p, y in pairs) / n
    cal = sum(brier_score(calibrator.apply(p), y) for p, y in pairs) / n
    return (raw, cal)
