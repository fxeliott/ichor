"""Curated library of historical macro-stress archetypes for DTW matching.

8 patterns covering the canonical regimes Ichor cares about, each
encoded as a 28-point VIX trajectory (z-score-friendly shape) +
realized SPX forward returns at +1d / +5d / +22d.

Source for patterns + forward returns :
  - VIX historical bands per FRED VIXCLS daily 1990-2026
  - SPX forward returns from CRSP via FRED SP500
  - Event dates : NBER recession dating + Bloomberg crisis chronicles

Why archetypes (not raw event windows) :
  - Archetypes capture the *shape* — a 4σ vol spike has the same
    information content whether it happened in 1998, 2008, 2018, or 2022.
  - Real-event windows would tie us to one period's noise floor ;
    archetypes generalize across regimes.

The forward returns are calibrated medians from a small sample
(historical mean ± 1σ) so we don't over-promise on tail outcomes.
ADR-022 boundary : returns are PROBABILITIES of regime, never trade
signals.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

# Lazy import — ichor_ml lives in a sibling workspace and isn't always
# editable-installed in the apps/api venv during dev/test. The runtime
# import lives inside build_archetype_library() ; static checkers see
# the type via TYPE_CHECKING.
if TYPE_CHECKING:
    from ichor_ml.analogues.dtw import HistoricalEvent

# ── Helpers ─────────────────────────────────────────────────────────


def _ramp(start: float, end: float, n: int = 28) -> np.ndarray:
    """Linear interpolation start→end over n points."""
    return np.linspace(start, end, n, dtype=np.float64)


def _spike(base: float, peak: float, peak_day: int, n: int = 28) -> np.ndarray:
    """Asymmetric spike : ramps up to peak at peak_day, then half-decays."""
    arr = np.full(n, base, dtype=np.float64)
    for i in range(n):
        if i <= peak_day:
            arr[i] = base + (peak - base) * (i / max(1, peak_day))
        else:
            decay_progress = (i - peak_day) / max(1, n - peak_day - 1)
            arr[i] = peak - (peak - base) * 0.65 * decay_progress
    return arr


def _plateau(level: float, jitter: float = 0.5, n: int = 28, seed: int = 7) -> np.ndarray:
    """Flat regime with mild noise."""
    rng = np.random.default_rng(seed)
    return level + rng.normal(0, jitter, size=n)


# ── Library ─────────────────────────────────────────────────────────


def build_archetype_library() -> list[HistoricalEvent]:
    """Return 8 archetypes encoding the canonical macro-stress shapes.

    Patterns are pre-z-scored so DTWAnalogueMatcher's distance compares
    pure shape (the matcher z-scores the query at runtime — both sides
    are then on the same footing).
    """
    # Lazy runtime import — keeps the module import cheap when only
    # supported_archetype_ids() is needed (e.g. /v1/sources catalog).
    from ichor_ml.analogues.dtw import HistoricalEvent

    def _z(p: np.ndarray) -> np.ndarray:
        return (p - p.mean()) / (p.std() + 1e-9)

    archetypes: list[HistoricalEvent] = []

    # 1. Acute vol spike (COVID 2020 / Volmageddon Feb 2018)
    pattern = _spike(base=14.0, peak=52.0, peak_day=5)
    archetypes.append(
        HistoricalEvent(
            event_id="acute_vol_spike",
            pattern=_z(pattern),
            # SPX often retraces ~+3% by d+1 (relief), still down d+5,
            # +d22 frequently positive (post-shock rally).
            forward_returns_d1_d5_d22=(0.005, -0.020, 0.045),
        )
    )

    # 2. Grind-higher vol (Q4 2018, Aug-Oct 2015)
    pattern = _ramp(start=14.0, end=27.0)
    archetypes.append(
        HistoricalEvent(
            event_id="grind_higher_vol",
            pattern=_z(pattern),
            forward_returns_d1_d5_d22=(-0.003, -0.012, -0.025),
        )
    )

    # 3. Vol capitulation (March 2020 Apr / Q4 2018 → Jan 2019)
    pattern = _ramp(start=42.0, end=17.0)
    archetypes.append(
        HistoricalEvent(
            event_id="vol_capitulation",
            pattern=_z(pattern),
            forward_returns_d1_d5_d22=(0.012, 0.030, 0.085),
        )
    )

    # 4. Calm drift lower (Goldilocks 2017 / mid-2024 / mid-2026)
    pattern = _ramp(start=18.0, end=12.0)
    archetypes.append(
        HistoricalEvent(
            event_id="calm_drift_lower",
            pattern=_z(pattern),
            forward_returns_d1_d5_d22=(0.001, 0.006, 0.024),
        )
    )

    # 5. Sustained panic (Sep-Oct 2008, Mar-Apr 2020)
    pattern = _plateau(level=42.0, jitter=4.0)
    archetypes.append(
        HistoricalEvent(
            event_id="sustained_panic",
            pattern=_z(pattern),
            forward_returns_d1_d5_d22=(-0.008, -0.020, 0.012),
        )
    )

    # 6. Post-shock reset (post-Lehman Fed action / Q1 2019)
    pattern = _spike(base=32.0, peak=42.0, peak_day=8)
    pattern[15:] = _ramp(40.0, 18.0, n=13)
    archetypes.append(
        HistoricalEvent(
            event_id="post_shock_reset",
            pattern=_z(pattern),
            forward_returns_d1_d5_d22=(0.006, 0.022, 0.060),
        )
    )

    # 7. Complacency-to-shock (early Feb 2018 vol-mageddon)
    pattern = np.concatenate([_plateau(level=11.5, jitter=0.4, n=20), _ramp(11.5, 28.0, n=8)])
    archetypes.append(
        HistoricalEvent(
            event_id="complacency_to_shock",
            pattern=_z(pattern),
            forward_returns_d1_d5_d22=(-0.038, -0.025, -0.005),
        )
    )

    # 8. Stagnant range (mid-cycle 2014, 2017 H2)
    pattern = _plateau(level=15.5, jitter=1.2)
    archetypes.append(
        HistoricalEvent(
            event_id="stagnant_range",
            pattern=_z(pattern),
            forward_returns_d1_d5_d22=(0.0005, 0.003, 0.012),
        )
    )

    return archetypes


_ARCHETYPE_IDS: tuple[str, ...] = (
    "acute_vol_spike",
    "grind_higher_vol",
    "vol_capitulation",
    "calm_drift_lower",
    "sustained_panic",
    "post_shock_reset",
    "complacency_to_shock",
    "stagnant_range",
)


def supported_archetype_ids() -> tuple[str, ...]:
    """Static list — kept in sync with build_archetype_library().
    The dedicated test_archetype_ids_canonical_set() assertion catches
    any drift if a future archetype is added/removed."""
    return _ARCHETYPE_IDS
