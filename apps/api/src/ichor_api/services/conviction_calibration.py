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

import math
from dataclasses import dataclass
from itertools import pairwise
from typing import Protocol

from .brier import (
    BiasDirection,
    ReliabilityBucket,
    brier_score,
    conviction_to_p_up,
    reliability_buckets,
)


class SupportsApply(Protocol):
    """Structural type for any fitted calibration map ``P_up -> P_up`` — lets the
    OOS scorer and selector treat the isotonic and Platt calibrators uniformly."""

    def apply(self, p_up: float) -> float: ...


def _conviction_from_p_up(bias: BiasDirection, calibrated_p_up: float) -> float:
    """Shared ``(bias, calibrated P_up) -> conviction%`` rule. Direction is
    UNCHANGED (ADR-017) — only the magnitude moves toward the realised
    reliability. If the calibration lands on the wrong side of 0.5 for the bias,
    conviction → 0 (no flip). Clamped 0..95 (ADR-022)."""
    if bias == "neutral":
        return 0.0
    signed = (calibrated_p_up - 0.5) if bias == "long" else (0.5 - calibrated_p_up)
    return min(_CONVICTION_CAP, max(0.0, signed * 2.0) * 100.0)


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
        """Recalibrated conviction % for a ``(bias, conviction)`` via the shared
        ADR-017 (no-flip) / ADR-022 (cap-95) rule."""
        return _conviction_from_p_up(bias, self.apply(conviction_to_p_up(bias, conviction_pct)))


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
    pairs: list[tuple[float, int]], calibrator: SupportsApply
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


# ───────────────── Regularised fit + OOS selection (slice-2, ADR-118) ─────────────────
#
# The slice-1 witness (ADR-116/117) found the raw isotonic fit OVERFITS the thin
# track-record: in-sample Brier improved (0.276→0.238) but OUT-OF-SAMPLE it got
# WORSE (0.259→0.301) on ~24 sessions. Isotonic regression is non-parametric and
# high-variance, so on a few dozen points it chases noise. The textbook antidote
# is to REGULARISE the fit toward the identity (no-correction) by a sample-size-
# aware weight, and to choose that weight OUT-OF-SAMPLE — never in-sample.

# Default shrinkage pseudo-count for ``lambda = N / (N + k)``. With the project's
# thin history (tens of sessions) this keeps the isotonic correction modest until
# the realised track-record is large enough to trust the full fit. In practice
# ``k`` is selected OUT-OF-SAMPLE (``select_regularization_oos``); this constant
# is only the standalone default.
_REG_PSEUDO_COUNT_DEFAULT = 50.0


def _lambda_for(n: float, k: float) -> float:
    """Sample-size-aware shrinkage weight ``N / (N + k)`` (empirical-Bayes /
    James-Stein style). ``N`` small → 0 (trust the identity, no overfit); ``N``
    large → 1 (trust the fit). ``k`` is the regularisation pseudo-count."""
    if n <= 0.0:
        return 0.0
    k = max(0.0, k)
    return n / (n + k)


def _shrink_toward_identity(base: ConvictionCalibrator, lam: float) -> ConvictionCalibrator:
    """Blend a fitted map toward the identity by ``lam`` ∈ [0, 1]:
    ``calibrated' = (1 - lam) * raw + lam * calibrated`` at each knot.

    Within the fitted range this equals EXACTLY ``(1 - lam) * p + lam *
    base.apply(p)`` — linear interpolation commutes with the convex blend (the
    raw knots are the interpolation abscissae, so the blended ordinates
    interpolate to the blended map). Outside the range the clamp lands on the
    blended endpoint. Monotonicity is preserved (a convex combination of two
    non-decreasing maps is non-decreasing), so every ``ConvictionCalibrator``
    invariant (ADR-017 no-flip, ADR-022 cap) carries over unchanged. ``lam = 1``
    recovers the raw isotonic fit; ``lam = 0`` is the identity."""
    if base.is_identity:
        return base
    lam = max(0.0, min(1.0, lam))
    if lam >= 1.0:
        return base
    if lam <= 0.0:
        return ConvictionCalibrator(points=())
    return ConvictionCalibrator(
        points=tuple(
            CalibrationPoint(
                raw_p_up=pt.raw_p_up,
                calibrated_p_up=(1.0 - lam) * pt.raw_p_up + lam * pt.calibrated_p_up,
                weight=pt.weight,
            )
            for pt in base.points
        )
    )


def fit_regularized(
    buckets: list[ReliabilityBucket], *, k: float = _REG_PSEUDO_COUNT_DEFAULT
) -> ConvictionCalibrator:
    """Isotonic fit shrunk toward the identity by ``lambda = N / (N + k)`` where
    ``N`` is the total realised observations across the populated bins — the
    small-sample antidote to the slice-1 overfit finding. A thin, high-variance
    isotonic map is pulled back toward "no correction" until the track-record
    earns the full fit. ``k = 0`` recovers the raw slice-1 isotonic; large ``k``
    → identity. Identity base (insufficient history) stays identity."""
    base = fit_from_reliability(buckets)
    if base.is_identity:
        return base
    n = float(sum(b.count for b in buckets if b.count > 0))
    return _shrink_toward_identity(base, _lambda_for(n, k))


def fit_regularized_from_pairs(
    pairs: list[tuple[float, int]],
    *,
    k: float = _REG_PSEUDO_COUNT_DEFAULT,
    n_bins: int = 10,
) -> ConvictionCalibrator:
    """``fit_regularized`` from raw ``(p_up, y)`` pairs (binned via
    ``reliability_buckets``). Empty input → identity."""
    if not pairs:
        return ConvictionCalibrator(points=())
    buckets = reliability_buckets([p for p, _ in pairs], [y for _, y in pairs], n_bins=n_bins)
    return fit_regularized(buckets, k=k)


@dataclass(frozen=True, slots=True)
class RegularizationSelection:
    """Outcome of an OUT-OF-SAMPLE search over the shrinkage pseudo-count ``k``.

    ``best_k is None`` means *no calibration* (identity) scored best on the held-
    out split — the honest answer when any fit would overfit. ``improved`` is
    True only when the chosen calibrator STRICTLY beats the identity OOS. The
    ``table`` carries every ``(k or None=identity, test Brier)`` tried, so the
    caller can report the full search honestly."""

    best_k: float | None
    best_test_brier: float
    identity_test_brier: float
    improved: bool
    table: tuple[tuple[float | None, float], ...]


def select_regularization_oos(
    train_pairs: list[tuple[float, int]],
    test_pairs: list[tuple[float, int]],
    candidate_ks: list[float],
    *,
    n_bins: int = 10,
) -> RegularizationSelection | None:
    """Pick the shrinkage ``k`` that minimises Brier on a DISJOINT test split —
    the only honest selection (ADR-116/117: in-sample Brier is not meaningful for
    this fit). The identity (no calibration) is ALWAYS a candidate, so the search
    can decline to calibrate when nothing helps out-of-sample. Ties resolve to
    the more conservative option (a ``k`` must STRICTLY beat the identity to be
    chosen). Returns ``None`` if either split is empty — the caller treats that
    as 'do not calibrate'."""
    if not train_pairs or not test_pairs:
        return None
    identity_brier = brier_improvement(test_pairs, ConvictionCalibrator(points=()))[1]
    table: list[tuple[float | None, float]] = [(None, identity_brier)]
    best_k: float | None = None
    best_brier = identity_brier
    for k in candidate_ks:
        cal = fit_regularized_from_pairs(train_pairs, k=k, n_bins=n_bins)
        test_brier = brier_improvement(test_pairs, cal)[1]
        table.append((k, test_brier))
        if test_brier < best_brier:
            best_brier = test_brier
            best_k = k
    return RegularizationSelection(
        best_k=best_k,
        best_test_brier=best_brier,
        identity_test_brier=identity_brier,
        improved=best_k is not None,
        table=tuple(table),
    )


# ───────────────────── Platt scaling (slice-3, ADR-118) ──────────────────────
#
# The literature's first choice for a SMALL calibration set: a 2-parameter
# sigmoid has far lower variance than the non-parametric isotonic fit and so
# generalises better out-of-sample on a few dozen points (Niculescu-Mizil &
# Caruana, ICML 2005 — isotonic "has more degrees of freedom than Platt Scaling,
# so it is easier for it to overfit when the calibration set is small"). Platt's
# regularised targets (1999) keep the log-loss finite on a confident sample.
# Kept GATED, like the isotonic slices: a pure-core candidate the OOS selector
# can pick — never auto-wired into the live verdict.


@dataclass(frozen=True, slots=True)
class PlattCalibrator:
    """A fitted 2-parameter Platt map ``P_up -> 1 / (1 + exp(a*P_up + b))``
    (Platt 1999; Lin, Lin & Weng 2007). Monotone when ``a < 0`` (the normal fit
    on a sane forecast); ``calibrate_conviction`` shares the ADR-017/022 rule, so
    a perverse fit collapses conviction to 0 rather than flipping a direction."""

    a: float
    b: float

    @property
    def is_identity(self) -> bool:
        return False

    def apply(self, p_up: float) -> float:
        """Calibrated ``P_up`` — the logistic map, evaluated in the overflow-safe
        branch for either sign of the exponent."""
        z = self.a * p_up + self.b
        if z >= 0.0:
            ez = math.exp(-z)
            return ez / (1.0 + ez)
        ez = math.exp(z)
        return 1.0 / (1.0 + ez)

    def calibrate_conviction(self, bias: BiasDirection, conviction_pct: float) -> float:
        """Recalibrated conviction % via the shared ADR-017 / ADR-022 rule."""
        return _conviction_from_p_up(bias, self.apply(conviction_to_p_up(bias, conviction_pct)))


def fit_platt(
    pairs: list[tuple[float, int]], *, max_iter: int = 100, min_step: float = 1e-10
) -> PlattCalibrator | None:
    """Fit Platt's 2-parameter sigmoid by REGULARISED maximum likelihood
    (Lin, Lin & Weng 2007 — the numerically-stable Newton refinement of Platt
    1999). Hard 0/1 labels are softened to ``(N_pos+1)/(N_pos+2)`` /
    ``1/(N_neg+2)`` so the log-loss cannot diverge on a small, confident sample
    (the small-N anti-overfit). Returns ``None`` for empty input or a single-
    class sample (a 2-parameter sigmoid is unidentifiable without both
    outcomes)."""
    if not pairs:
        return None
    scores = [p for p, _ in pairs]
    labels = [y for _, y in pairs]
    prior1 = sum(labels)
    prior0 = len(labels) - prior1
    if prior1 == 0 or prior0 == 0:
        return None
    hi = (prior1 + 1.0) / (prior1 + 2.0)
    lo = 1.0 / (prior0 + 2.0)
    targets = [hi if y == 1 else lo for y in labels]

    def _nll(a_: float, b_: float) -> float:
        total = 0.0
        for f, t in zip(scores, targets, strict=True):
            z = f * a_ + b_
            # log(1 + exp(z)) evaluated in the stable branch for either sign
            if z >= 0.0:
                total += t * z + math.log1p(math.exp(-z))
            else:
                total += (t - 1.0) * z + math.log1p(math.exp(z))
        return total

    a = 0.0
    b = math.log((prior0 + 1.0) / (prior1 + 1.0))
    current = _nll(a, b)
    sigma = 1e-12
    for _ in range(max_iter):
        h11 = h22 = h21 = g1 = g2 = 0.0
        for f, t in zip(scores, targets, strict=True):
            z = f * a + b
            if z >= 0.0:
                ez = math.exp(-z)
                p = ez / (1.0 + ez)
            else:
                ez = math.exp(z)
                p = 1.0 / (1.0 + ez)
            d2 = p * (1.0 - p)
            h11 += f * f * d2
            h22 += d2
            h21 += f * d2
            d1 = t - p  # g = ∇NLL = Σ (t - p)·[f, 1]
            g1 += f * d1
            g2 += d1
        if abs(g1) < 1e-9 and abs(g2) < 1e-9:
            break
        h11 += sigma
        h22 += sigma
        det = h11 * h22 - h21 * h21
        if det == 0.0:
            break
        # Newton step on the NLL: delta = -H^{-1} g
        d_a = -(h22 * g1 - h21 * g2) / det
        d_b = -(h11 * g2 - h21 * g1) / det
        gd = g1 * d_a + g2 * d_b  # directional derivative (< 0 for a descent step)
        step = 1.0
        while step >= min_step:
            new_nll = _nll(a + step * d_a, b + step * d_b)
            if new_nll < current + 1e-4 * step * gd:  # Armijo sufficient decrease
                a += step * d_a
                b += step * d_b
                current = new_nll
                break
            step *= 0.5
        else:
            break  # line search exhausted → converged
    return PlattCalibrator(a=a, b=b)


@dataclass(frozen=True, slots=True)
class CalibratorSelection:
    """Outcome of an OUT-OF-SAMPLE search across calibration FAMILIES (identity,
    regularised isotonic over candidate ``k``, Platt). ``best_label == 'identity'``
    means no method beat 'do not calibrate' on the held-out split — the honest
    default. ``improved`` is True only when the winner strictly beats identity."""

    best_label: str
    best_test_brier: float
    identity_test_brier: float
    improved: bool
    table: tuple[tuple[str, float], ...]


def select_calibrator_oos(
    train_pairs: list[tuple[float, int]],
    test_pairs: list[tuple[float, int]],
    *,
    ks: tuple[float, ...] = (0.0, 5.0, 20.0, 50.0),
    n_bins: int = 10,
) -> CalibratorSelection | None:
    """Pick the calibration FAMILY+hyperparameter that minimises Brier on a
    DISJOINT test split — identity, regularised isotonic over ``ks``, and Platt
    all compete on the same held-out data. Identity is always a candidate, so the
    search can decline to calibrate. Ties resolve conservatively (a method must
    strictly beat identity). Returns ``None`` if either split is empty."""
    if not train_pairs or not test_pairs:
        return None
    identity_brier = brier_improvement(test_pairs, ConvictionCalibrator(points=()))[1]
    table: list[tuple[str, float]] = [("identity", identity_brier)]
    best_label = "identity"
    best_brier = identity_brier
    for k in ks:
        cal = fit_regularized_from_pairs(train_pairs, k=k, n_bins=n_bins)
        test_brier = brier_improvement(test_pairs, cal)[1]
        label = f"isotonic_k={k:g}"
        table.append((label, test_brier))
        if test_brier < best_brier:
            best_brier, best_label = test_brier, label
    platt = fit_platt(train_pairs)
    if platt is not None:
        test_brier = brier_improvement(test_pairs, platt)[1]
        table.append(("platt", test_brier))
        if test_brier < best_brier:
            best_brier, best_label = test_brier, "platt"
    return CalibratorSelection(
        best_label=best_label,
        best_test_brier=best_brier,
        identity_test_brier=identity_brier,
        improved=best_label != "identity",
        table=tuple(table),
    )
