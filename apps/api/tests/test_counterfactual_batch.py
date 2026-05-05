"""Unit tests for the counterfactual-batch CLI helpers."""

from __future__ import annotations

import pytest

from ichor_api.cli.run_counterfactual_batch import (
    ASSETS,
    _DEFAULT_SCRUB,
    _pick_scrub_event,
)


def test_assets_match_phase1_universe() -> None:
    """Same 8-asset list as run_har_rv / run_hmm_regime."""
    assert "EUR_USD" in ASSETS
    assert "XAU_USD" in ASSETS
    assert "NAS100_USD" in ASSETS
    assert len(ASSETS) == 8


def test_pick_scrub_falls_back_when_empty() -> None:
    assert _pick_scrub_event(None) == _DEFAULT_SCRUB
    assert _pick_scrub_event([]) == _DEFAULT_SCRUB
    assert _pick_scrub_event({}) == _DEFAULT_SCRUB


def test_pick_scrub_string_list_uses_first() -> None:
    out = _pick_scrub_event(["ECB Lagarde dovish surprise", "OPEC supply cut"])
    assert out == "ECB Lagarde dovish surprise"


def test_pick_scrub_dict_list_uses_label_field() -> None:
    out = _pick_scrub_event(
        [
            {"label": "Fed Powell hawkish pivot", "weight": 0.7},
            {"label": "EU PMI rebound", "weight": 0.3},
        ]
    )
    assert out == "Fed Powell hawkish pivot"


def test_pick_scrub_dict_list_falls_back_to_title() -> None:
    out = _pick_scrub_event([{"title": "BoJ intervention risk", "weight": 0.6}])
    assert out == "BoJ intervention risk"


def test_pick_scrub_truncates_long_strings() -> None:
    long_event = "x" * 1000
    out = _pick_scrub_event([long_event])
    assert len(out) <= 480


def test_pick_scrub_handles_dict_top_level() -> None:
    out = _pick_scrub_event({"label": "Crisis flag", "details": "..."})
    assert out == "Crisis flag"


def test_pick_scrub_unknown_shape_falls_back() -> None:
    """Defensive : if neither list nor dict matches, use the default."""
    assert _pick_scrub_event(42) == _DEFAULT_SCRUB
    assert _pick_scrub_event([{"unknown_key": "x"}]) == _DEFAULT_SCRUB


def test_module_imports() -> None:
    import importlib

    mod = importlib.import_module("ichor_api.cli.run_counterfactual_batch")
    assert hasattr(mod, "run")


def test_help_exits_cleanly() -> None:
    from ichor_api.cli.run_counterfactual_batch import main

    with pytest.raises(SystemExit):
        main(["run_counterfactual_batch", "--help"])
