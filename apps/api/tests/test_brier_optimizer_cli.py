"""Unit tests for the Brier optimizer CLI helpers.

Tests verify the seeding logic + equal-weight defaults without
hitting Postgres.
"""

from __future__ import annotations

from ichor_api.cli.run_brier_optimizer import _FACTOR_NAMES, _equal_weights


def test_factor_names_match_confluence_engine() -> None:
    """If the optimizer seeds weights for factors that don't exist in
    confluence_engine, the runtime weight lookup will silently fall
    back to 1.0 for those keys — defeating the purpose."""
    expected = {
        "rate_diff",
        "cot",
        "microstructure_ofi",
        "daily_levels",
        "polymarket_overlay",
        "funding_stress",
        "surprise_index",
        "vix_term",
        "risk_appetite",
        "btc_risk_proxy",
    }
    assert set(_FACTOR_NAMES) == expected


def test_equal_weights_sums_to_one() -> None:
    w = _equal_weights()
    assert abs(sum(w.values()) - 1.0) < 1e-9


def test_equal_weights_has_one_entry_per_factor() -> None:
    w = _equal_weights()
    assert len(w) == len(_FACTOR_NAMES)
    assert set(w.keys()) == set(_FACTOR_NAMES)


def test_equal_weights_are_strictly_positive() -> None:
    w = _equal_weights()
    for k, v in w.items():
        assert v > 0, f"weight for {k} must be > 0, got {v}"
