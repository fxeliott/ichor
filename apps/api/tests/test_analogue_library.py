"""Tests for the analogue library + DTW matcher integration.

Tests that need the live DTW matcher are gated behind
pytest.importorskip("ichor_ml") — they only run when the sibling
ichor-ml package is editable-installed in this venv (production
Hetzner has it, local apps/api venv may not).
"""

from __future__ import annotations

import numpy as np
import pytest
from ichor_api.services.analogue_library import supported_archetype_ids


def _have_ichor_ml() -> bool:
    try:
        __import__("ichor_ml.analogues.dtw")
        return True
    except ImportError:
        return False


_skip_no_ml = pytest.mark.skipif(
    not _have_ichor_ml(),
    reason="ichor_ml not editable-installed in this venv",
)


def test_archetype_ids_canonical_set() -> None:
    """Static IDs check — runs even without ichor_ml installed."""
    ids = set(supported_archetype_ids())
    expected = {
        "acute_vol_spike",
        "grind_higher_vol",
        "vol_capitulation",
        "calm_drift_lower",
        "sustained_panic",
        "post_shock_reset",
        "complacency_to_shock",
        "stagnant_range",
    }
    assert ids == expected


@_skip_no_ml
def test_library_has_8_archetypes() -> None:
    from ichor_api.services.analogue_library import build_archetype_library

    assert len(build_archetype_library()) == 8


@_skip_no_ml
def test_each_archetype_has_28_point_pattern() -> None:
    from ichor_api.services.analogue_library import build_archetype_library

    for ev in build_archetype_library():
        assert ev.pattern.shape == (28,), f"{ev.event_id} has wrong shape"


@_skip_no_ml
def test_each_archetype_has_3_forward_returns() -> None:
    from ichor_api.services.analogue_library import build_archetype_library

    for ev in build_archetype_library():
        assert len(ev.forward_returns_d1_d5_d22) == 3
        for r in ev.forward_returns_d1_d5_d22:
            assert -0.20 < r < 0.20, f"{ev.event_id} forward return out of band: {r}"


@_skip_no_ml
def test_archetypes_are_z_scored() -> None:
    from ichor_api.services.analogue_library import build_archetype_library

    for ev in build_archetype_library():
        mean = float(np.mean(ev.pattern))
        std = float(np.std(ev.pattern))
        assert abs(mean) < 1e-6, f"{ev.event_id} mean {mean} not zero"
        assert abs(std - 1.0) < 0.05, f"{ev.event_id} std {std} not 1"


@_skip_no_ml
def test_archetypes_distinct_shapes() -> None:
    from ichor_api.services.analogue_library import build_archetype_library

    lib = build_archetype_library()
    for i, a in enumerate(lib):
        for b in lib[i + 1 :]:
            diff = float(np.mean((a.pattern - b.pattern) ** 2))
            assert diff > 0.05, f"{a.event_id} and {b.event_id} look identical"


@_skip_no_ml
def test_dtw_matcher_finds_self_match_distance_zero() -> None:
    from ichor_api.services.analogue_library import build_archetype_library
    from ichor_ml.analogues.dtw import DTWAnalogueMatcher

    lib = build_archetype_library()
    matcher = DTWAnalogueMatcher(lib)
    query = lib[0].pattern.copy()
    matches = matcher.find_top_k(query, k=3)
    assert matches[0].library_event_id == lib[0].event_id
    assert matches[0].distance < 0.01, f"self-match distance too high: {matches[0].distance}"


@_skip_no_ml
def test_dtw_matcher_distinguishes_calm_from_panic() -> None:
    from ichor_api.services.analogue_library import build_archetype_library
    from ichor_ml.analogues.dtw import DTWAnalogueMatcher

    lib = build_archetype_library()
    matcher = DTWAnalogueMatcher(lib)
    query = np.linspace(18.0, 12.0, 28)
    matches = matcher.find_top_k(query, k=3)
    assert matches[0].library_event_id in ("calm_drift_lower", "stagnant_range")


def test_run_dtw_module_imports() -> None:
    import importlib

    mod = importlib.import_module("ichor_api.cli.run_dtw_analogue")
    assert hasattr(mod, "run")


def test_run_dtw_help_exits_cleanly() -> None:
    from ichor_api.cli.run_dtw_analogue import main

    with pytest.raises(SystemExit):
        main(["run_dtw_analogue", "--help"])
