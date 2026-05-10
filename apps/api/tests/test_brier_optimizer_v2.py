"""Unit tests for Brier-optimizer V2 helpers (no DB).

Covers the math primitives the V2 CLI relies on :
- `derive_realized_outcome` — Brier identity inverse
- `drivers_to_signal_row` — sign-convention pivot from Driver.contribution
  ∈ [-1, +1] into the V1 signal space [0, 1]
- env-flag gating in `run_brier_optimizer_v2._v2_enabled`
"""

from __future__ import annotations

import numpy as np
import pytest
from ichor_api.cli.run_brier_optimizer_v2 import _v2_enabled
from ichor_api.services.brier_optimizer import (
    DEFAULT_FACTOR_NAMES,
    derive_realized_outcome,
    drivers_to_signal_row,
)

# ─────────────────────── derive_realized_outcome ───────────────────────


def test_derive_long_high_conviction_correct_call() -> None:
    # bias=long, conviction=80 → p_up = 0.9
    # if y=1, brier = (0.9 - 1)^2 = 0.01
    assert derive_realized_outcome("long", 80.0, 0.01) == 1


def test_derive_long_high_conviction_wrong_call() -> None:
    # bias=long, conviction=80 → p_up = 0.9
    # if y=0, brier = 0.9^2 = 0.81
    assert derive_realized_outcome("long", 80.0, 0.81) == 0


def test_derive_short_high_conviction_correct_call() -> None:
    # bias=short, conviction=80 → p_up = 0.1
    # if y=0, brier = 0.1^2 = 0.01
    assert derive_realized_outcome("short", 80.0, 0.01) == 0


def test_derive_short_high_conviction_wrong_call() -> None:
    # bias=short, conviction=80 → p_up = 0.1
    # if y=1, brier = (0.1 - 1)^2 = 0.81
    assert derive_realized_outcome("short", 80.0, 0.81) == 1


def test_derive_neutral_is_ambiguous() -> None:
    # bias=neutral → p_up = 0.5 → both candidates give brier = 0.25.
    assert derive_realized_outcome("neutral", 50.0, 0.25) is None


def test_derive_unknown_bias_returns_none() -> None:
    assert derive_realized_outcome("sideways", 70.0, 0.1) is None


def test_derive_long_low_conviction_resolvable() -> None:
    # bias=long, conviction=20 → p_up = 0.6
    # if y=1, brier = 0.16 ; if y=0, brier = 0.36 — clearly resolvable.
    assert derive_realized_outcome("long", 20.0, 0.16) == 1
    assert derive_realized_outcome("long", 20.0, 0.36) == 0


# ─────────────────────── drivers_to_signal_row ───────────────────────


def test_drivers_signed_mapping_at_extremes_and_neutral() -> None:
    drivers = [
        {"factor": "rate_diff", "contribution": -1.0, "evidence": "x"},
        {"factor": "cot", "contribution": 1.0, "evidence": "y"},
        {"factor": "microstructure_ofi", "contribution": 0.0, "evidence": "z"},
    ]
    sig = drivers_to_signal_row(drivers)
    assert sig is not None
    idx = list(DEFAULT_FACTOR_NAMES)
    assert pytest.approx(sig[idx.index("rate_diff")]) == 0.0
    assert pytest.approx(sig[idx.index("cot")]) == 1.0
    assert pytest.approx(sig[idx.index("microstructure_ofi")]) == 0.5


def test_drivers_default_neutral_for_missing_factors() -> None:
    drivers = [{"factor": "rate_diff", "contribution": 0.6, "evidence": "..."}]
    sig = drivers_to_signal_row(drivers)
    assert sig is not None
    idx = list(DEFAULT_FACTOR_NAMES).index("rate_diff")
    assert pytest.approx(sig[idx]) == 0.8  # 0.5 + 0.5 * 0.6
    others = np.delete(sig, idx)
    np.testing.assert_allclose(others, 0.5)


def test_drivers_clamps_out_of_range() -> None:
    drivers = [
        {"factor": "rate_diff", "contribution": 1.5, "evidence": "x"},
        {"factor": "cot", "contribution": -2.0, "evidence": "y"},
    ]
    sig = drivers_to_signal_row(drivers)
    assert sig is not None
    idx = list(DEFAULT_FACTOR_NAMES)
    assert pytest.approx(sig[idx.index("rate_diff")]) == 1.0
    assert pytest.approx(sig[idx.index("cot")]) == 0.0


def test_drivers_empty_or_none_returns_none() -> None:
    assert drivers_to_signal_row(None) is None
    assert drivers_to_signal_row([]) is None


def test_drivers_skips_malformed_entries() -> None:
    drivers = [
        {"factor": "rate_diff", "contribution": 0.5, "evidence": "x"},
        {"factor": "cot"},  # missing contribution
        "not a dict",  # malformed entry should be skipped, not crash
        {"factor": None, "contribution": 0.5},
        {"factor": "vix_term", "contribution": "not a number"},
    ]
    sig = drivers_to_signal_row(drivers)  # type: ignore[arg-type]
    assert sig is not None
    idx = list(DEFAULT_FACTOR_NAMES).index("rate_diff")
    assert pytest.approx(sig[idx]) == 0.75


def test_drivers_unknown_factors_dont_pollute_canonical_signal() -> None:
    drivers = [
        {"factor": "made_up_factor", "contribution": 1.0, "evidence": "x"},
    ]
    # Only an unknown factor present — every canonical factor stays at neutral
    # and the row is not None (we still return a vector, just all 0.5).
    sig = drivers_to_signal_row(drivers)
    assert sig is not None
    np.testing.assert_allclose(sig, 0.5)


# ─────────────────────── feature flag ───────────────────────


def test_v2_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ICHOR_API_BRIER_V2_ENABLED", raising=False)
    assert _v2_enabled() is False


@pytest.mark.parametrize("value", ["true", "True", "TRUE", "1", "yes", "on"])
def test_v2_enabled_for_truthy_values(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("ICHOR_API_BRIER_V2_ENABLED", value)
    assert _v2_enabled() is True


@pytest.mark.parametrize("value", ["false", "0", "no", "off", "", "maybe"])
def test_v2_disabled_for_falsy_values(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("ICHOR_API_BRIER_V2_ENABLED", value)
    assert _v2_enabled() is False


def test_factor_names_match_v1_seed_list() -> None:
    """V2's canonical factor list must stay aligned with the V1 seed list
    exposed by `cli.run_brier_optimizer._FACTOR_NAMES` — otherwise the
    runtime weight lookup will silently fall back to 1.0 for those keys."""
    from ichor_api.cli.run_brier_optimizer import _FACTOR_NAMES

    assert set(DEFAULT_FACTOR_NAMES) == set(_FACTOR_NAMES)


# ─────────────────────── _v2_enabled ergonomics ───────────────────────


def test_v2_enabled_strips_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICHOR_API_BRIER_V2_ENABLED", "  true  ")
    assert _v2_enabled() is True
