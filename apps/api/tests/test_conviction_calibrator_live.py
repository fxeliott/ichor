"""S06 Chantier C-5 — ``select_and_fit_live_calibrator`` (the live OOS-gated brain).

Pure unit tests (no DB, no runner): the function decides OUT-OF-SAMPLE whether to
calibrate the live conviction and, if so, refits the winning family on the full
history. Coverage:

  1. honesty gate — a thin held-out split or well-calibrated data → ``None`` (keep raw);
  2. a clearly over-confident track-record → a real calibrator that SHRINKS conviction;
  3. the returned calibrator preserves the ADR-017 no-flip / ADR-022 cap-95 invariants;
  4. determinism (same input → same fit).

The flag-OFF byte-identity of the live wiring (``build_session_verdict``) is held by the
existing golden harnesses (``test_fuser_golden_harness`` + ``test_card_golden_harness``);
this file proves the pure C-5 brain is correct + honest.
"""

from __future__ import annotations

from ichor_api.services.conviction_calibration import (
    CONVICTION_CALIBRATOR_FLAG,
    select_and_fit_live_calibrator,
)


def _overconfident_pairs(n_per_level: int = 100) -> list[tuple[float, int]]:
    """Strongly over-confident: forecasts 0.7 and 0.9 but each realises ~50 % up.
    Interleaved so a chronological split keeps both levels in train AND test.
    Calibration that shrinks toward 0.5 beats identity OOS by construction."""
    pairs: list[tuple[float, int]] = []
    for i in range(n_per_level):
        y = i % 2  # exactly 50 % ones per level over an even count
        pairs.append((0.7, y))
        pairs.append((0.9, y))
    return pairs


def _well_calibrated_pairs(n: int = 120) -> list[tuple[float, int]]:
    """Forecast 0.4 realises 40 % up, forecast 0.6 realises 60 % up — already honest.
    No family should strictly beat 'do not calibrate' OOS → expect None."""
    pairs: list[tuple[float, int]] = []
    for i in range(n):
        pairs.append((0.4, 1 if (i % 5) < 2 else 0))  # 40 % ones
        pairs.append((0.6, 1 if (i % 5) < 3 else 0))  # 60 % ones
    return pairs


# --------------------------------------------------------------------------- #
# Honesty gate — None when not conclusively beneficial                         #
# --------------------------------------------------------------------------- #


def test_flag_constant_is_the_documented_key() -> None:
    assert CONVICTION_CALIBRATOR_FLAG == "conviction_calibrator_oos_enabled"


def test_empty_history_returns_none() -> None:
    assert select_and_fit_live_calibrator([]) is None


def test_thin_held_out_split_returns_none() -> None:
    # 40 pairs, train_frac 0.6 → test split 16 < min_conclusive 30 → abstain.
    pairs = [(0.8, i % 2) for i in range(40)]
    assert select_and_fit_live_calibrator(pairs) is None


def test_well_calibrated_history_keeps_raw_conviction() -> None:
    # Already-honest forecasts → nothing beats identity OOS → None (keep raw).
    assert select_and_fit_live_calibrator(_well_calibrated_pairs()) is None


# --------------------------------------------------------------------------- #
# Conclusive over-confidence → a real shrinking calibrator                     #
# --------------------------------------------------------------------------- #


def test_overconfident_history_returns_shrinking_calibrator() -> None:
    cal = select_and_fit_live_calibrator(_overconfident_pairs())
    assert cal is not None
    # An over-confident "long 90 %" must be SHRUNK toward ~50 % (honest fix).
    shrunk = cal.calibrate_conviction("long", 90.0)
    assert shrunk < 90.0
    # Symmetric on the short side.
    shrunk_short = cal.calibrate_conviction("short", 90.0)
    assert shrunk_short < 90.0


def test_returned_calibrator_holds_adr017_adr022() -> None:
    cal = select_and_fit_live_calibrator(_overconfident_pairs())
    assert cal is not None
    # ADR-022: every calibrated conviction stays within [0, 95].
    for conv in (0.0, 10.0, 50.0, 90.0, 95.0):
        for bias in ("long", "short"):
            out = cal.calibrate_conviction(bias, conv)
            assert 0.0 <= out <= 95.0
    # ADR-017: neutral carries no directional forecast → conviction 0, never a tilt.
    assert cal.calibrate_conviction("neutral", 90.0) == 0.0
    # apply() is a probability map → stays in [0, 1].
    for p in (0.0, 0.25, 0.5, 0.75, 1.0):
        assert 0.0 <= cal.apply(p) <= 1.0


def test_fit_is_deterministic() -> None:
    a = select_and_fit_live_calibrator(_overconfident_pairs())
    b = select_and_fit_live_calibrator(_overconfident_pairs())
    assert (a is None) == (b is None)
    assert a is not None and b is not None
    # Same inputs → same map (probe a few points).
    for p in (0.55, 0.7, 0.85, 0.95):
        assert a.apply(p) == b.apply(p)


def test_min_conclusive_override_gates_harder() -> None:
    # The same over-confident data abstains under a stricter conclusive threshold
    # that the held-out split cannot meet.
    pairs = _overconfident_pairs(n_per_level=40)  # 80 pairs, test split 32
    assert select_and_fit_live_calibrator(pairs) is not None  # 32 >= 30 default
    assert select_and_fit_live_calibrator(pairs, min_conclusive=50) is None  # 32 < 50
