"""Unit tests for the Brier optimizer CLI helpers.

Tests verify the seeding logic + equal-weight defaults without
hitting Postgres.
"""

from __future__ import annotations

from ichor_api.cli.run_brier_optimizer import _FACTOR_NAMES, _equal_weights


def test_factor_names_match_confluence_engine() -> None:
    """If the optimizer seeds weights for factors that don't exist in
    confluence_engine, the runtime weight lookup will silently fall
    back to 1.0 for those keys — defeating the purpose.

    Note (r148) — this hard-coded set is a tautology relative to the
    registry-vs-registry CI guard at
    `test_invariants_ichor.test_r142_brier_optimizer_factor_names_lockstep`
    and the emission-vs-registry guard at
    `test_invariants_ichor.test_r148_confluence_engine_driver_emissions_match_brier_registry`.
    Kept for now to avoid silent coverage loss ; r149 candidate to delete
    since the two new guards already mechanise the safety property more
    rigorously (AST inspection of actual emissions, not a hand-maintained
    parallel list).
    """
    expected = {
        "rate_diff",
        "cot",
        "microstructure_ofi",
        "daily_levels",
        "polymarket_overlay",
        "funding_stress",
        "surprise_index",
        "inflation_surprise",  # r137 — separate inflation-surprise driver
        "vix_term",
        "risk_appetite",
        "btc_risk_proxy",
        "event_anticipation",  # r147 — Engine 8 (Lucca-Moench + Boyd-Hu-Jagannathan)
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
