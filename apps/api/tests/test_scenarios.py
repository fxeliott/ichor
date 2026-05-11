"""Unit tests for `services.scenarios` (W105 skeleton).

ADR-085 contract enforcement : 7 buckets exact, sum=1, cap-95 per bucket,
unique labels, magnitude range valid. Plus `cap_and_normalize` algorithmic
properties (mass preservation, convergence, edge cases).
"""

from __future__ import annotations

import pytest
from ichor_api.services.scenarios import (
    BUCKET_LABELS,
    BUCKET_Z_THRESHOLDS,
    CAP_95,
    Scenario,
    ScenarioDecomposition,
    bucket_for_zscore,
    cap_and_normalize,
)
from pydantic import ValidationError

# ───────────────────────── BUCKET_LABELS canonical ─────────────────────


def test_bucket_labels_canonical_order() -> None:
    """Order is most-bearish → most-bullish ; never reorder."""
    assert BUCKET_LABELS == (
        "crash_flush",
        "strong_bear",
        "mild_bear",
        "base",
        "mild_bull",
        "strong_bull",
        "melt_up",
    )


def test_bucket_labels_exactly_seven() -> None:
    assert len(BUCKET_LABELS) == 7
    assert len(set(BUCKET_LABELS)) == 7


def test_bucket_z_thresholds_strictly_increasing() -> None:
    for i in range(len(BUCKET_Z_THRESHOLDS) - 1):
        assert BUCKET_Z_THRESHOLDS[i] < BUCKET_Z_THRESHOLDS[i + 1]


# ───────────────────────── Scenario model ──────────────────────────────


def _valid_scenario(label: str = "base", p: float = 0.5) -> Scenario:
    return Scenario(
        label=label,  # type: ignore[arg-type]
        p=p,
        magnitude_pips=(-10.0, 10.0),
        mechanism="Sideways consolidation absent strong catalyst",
    )


def test_scenario_valid_construction() -> None:
    s = _valid_scenario()
    assert s.label == "base"
    assert s.p == 0.5


def test_scenario_rejects_invalid_label() -> None:
    with pytest.raises(ValidationError):
        Scenario(
            label="extreme_bear",  # type: ignore[arg-type]
            p=0.1,
            magnitude_pips=(-50.0, -20.0),
            mechanism="x" * 30,
        )


def test_scenario_rejects_probability_above_cap_95() -> None:
    with pytest.raises(ValidationError):
        _valid_scenario(p=0.96)


def test_scenario_rejects_negative_probability() -> None:
    with pytest.raises(ValidationError):
        _valid_scenario(p=-0.01)


def test_scenario_accepts_zero_probability() -> None:
    s = _valid_scenario(p=0.0)
    assert s.p == 0.0


def test_scenario_rejects_magnitude_low_above_high() -> None:
    with pytest.raises(ValidationError):
        Scenario(
            label="base",
            p=0.5,
            magnitude_pips=(10.0, -10.0),
            mechanism="x" * 30,
        )


def test_scenario_rejects_short_mechanism() -> None:
    with pytest.raises(ValidationError):
        Scenario(
            label="base",
            p=0.5,
            magnitude_pips=(-10.0, 10.0),
            mechanism="too short",
        )


def test_scenario_rejects_buy_token_in_mechanism() -> None:
    """ADR-017 boundary regression guard at runtime construction."""
    with pytest.raises(ValidationError, match="ADR-017"):
        Scenario(
            label="strong_bull",
            p=0.1,
            magnitude_pips=(40.0, 120.0),
            mechanism="If catalyst lands cleanly, traders should BUY breakout above",
        )


def test_scenario_rejects_sell_token_in_mechanism() -> None:
    with pytest.raises(ValidationError, match="ADR-017"):
        Scenario(
            label="strong_bear",
            p=0.1,
            magnitude_pips=(-120.0, -40.0),
            mechanism="SELL on retracement to the 0.5 fib level after rejection",
        )


def test_scenario_rejects_tp_sl_tokens_in_mechanism() -> None:
    for forbidden in ("TP at 1.0850 zone", "SL above 1.0900", "stop loss at PDH"):
        with pytest.raises(ValidationError, match="ADR-017"):
            Scenario(
                label="base",
                p=0.5,
                magnitude_pips=(-10.0, 10.0),
                mechanism=f"Mechanism with forbidden token: {forbidden} mechanism context",
            )


def test_scenario_accepts_mechanism_with_buy_inside_word() -> None:
    """Word-boundary regex must allow `buyer`, `buyback`, `obuya` etc.
    Only standalone `BUY` / `SELL` / `TP` / `SL` are rejected."""
    s = Scenario(
        label="mild_bull",
        p=0.2,
        magnitude_pips=(10.0, 40.0),
        mechanism="Asian buyback flows lift JPY crosses pre-Londres typically",
    )
    assert s.label == "mild_bull"


def test_scenario_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Scenario(
            label="base",
            p=0.5,
            magnitude_pips=(-10.0, 10.0),
            mechanism="x" * 30,
            extra_field="should be forbidden",  # type: ignore[call-arg]
        )


# ───────────────────────── ScenarioDecomposition model ─────────────────


def _balanced_scenarios(ps: list[float] | None = None) -> list[Scenario]:
    """Build 7 valid scenarios with the canonical labels and given probs.
    Default = uniform 1/7 each."""
    probs = ps if ps is not None else [1.0 / 7.0] * 7
    return [
        Scenario(
            label=label,
            p=p,
            magnitude_pips=(-50.0 + 10 * i, -40.0 + 10 * i),
            mechanism=f"Mechanism stub for {label} bucket xxxxxxxxxxxxxxxxxxxx",
        )
        for i, (label, p) in enumerate(zip(BUCKET_LABELS, probs, strict=True))
    ]


def test_decomposition_valid_uniform_prior() -> None:
    d = ScenarioDecomposition(
        asset="EUR_USD",
        session_type="pre_londres",
        scenarios=_balanced_scenarios(),
    )
    assert len(d.scenarios) == 7
    assert abs(sum(s.p for s in d.scenarios) - 1.0) < 1e-6


def test_decomposition_rejects_6_buckets() -> None:
    with pytest.raises(ValidationError):
        ScenarioDecomposition(
            asset="EUR_USD",
            session_type="pre_londres",
            scenarios=_balanced_scenarios()[:6],
        )


def test_decomposition_rejects_8_buckets() -> None:
    extra = _balanced_scenarios() + [
        Scenario(
            label="base",
            p=0.0,
            magnitude_pips=(-1.0, 1.0),
            mechanism="duplicate base bucket xxxxxxxxxxxxxxxxxxxx",
        )
    ]
    with pytest.raises(ValidationError):
        ScenarioDecomposition(
            asset="EUR_USD",
            session_type="pre_londres",
            scenarios=extra,
        )


def test_decomposition_rejects_duplicate_labels() -> None:
    dup = _balanced_scenarios()
    # Replace second scenario with another "base" — 6 unique labels, 1 dup.
    dup[1] = Scenario(
        label="base",
        p=0.14,
        magnitude_pips=(-5.0, 5.0),
        mechanism="duplicate base again xxxxxxxxxxxxxxxxxxxx",
    )
    with pytest.raises(ValidationError):
        ScenarioDecomposition(
            asset="EUR_USD",
            session_type="pre_londres",
            scenarios=dup,
        )


def test_decomposition_rejects_sum_not_one() -> None:
    bad_probs = [0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1]  # sum = 0.7
    with pytest.raises(ValidationError):
        ScenarioDecomposition(
            asset="EUR_USD",
            session_type="pre_londres",
            scenarios=_balanced_scenarios(bad_probs),
        )


def test_decomposition_accepts_realistic_skew() -> None:
    """A typical broken-smile distribution : mass on mild_bear + base."""
    realistic = [0.02, 0.10, 0.25, 0.34, 0.20, 0.07, 0.02]
    assert abs(sum(realistic) - 1.0) < 1e-9
    d = ScenarioDecomposition(
        asset="EUR_USD",
        session_type="pre_londres",
        scenarios=_balanced_scenarios(realistic),
    )
    assert d.scenarios[3].p == 0.34


# ───────────────────────── cap_and_normalize ───────────────────────────


def test_cap_normalize_noop_when_below_cap() -> None:
    probs = [0.1, 0.2, 0.3, 0.2, 0.1, 0.05, 0.05]
    assert abs(sum(probs) - 1.0) < 1e-9
    out = cap_and_normalize(probs)
    assert out == probs  # unchanged


def test_cap_normalize_clips_max_above_cap() -> None:
    probs = [0.98, 0.005, 0.005, 0.005, 0.0, 0.005, 0.0]
    assert abs(sum(probs) - 1.0) < 1e-9
    out = cap_and_normalize(probs)
    assert max(out) <= CAP_95 + 1e-12
    assert abs(sum(out) - 1.0) < 1e-9  # mass preserved


def test_cap_normalize_redistributes_proportionally() -> None:
    # The 3 small buckets should grow in proportion to their original mass.
    probs = [0.97, 0.01, 0.01, 0.01, 0.0, 0.0, 0.0]
    out = cap_and_normalize(probs)
    # Excess = 0.97 - 0.95 = 0.02. The 3 buckets with 0.01 each (sum=0.03)
    # should each gain 0.02 * (0.01/0.03) = 0.00667.
    # The zero buckets stay at 0 (zero mass → zero share of redistribution).
    assert out[0] == pytest.approx(0.95, abs=1e-9)
    assert out[4] == pytest.approx(0.0, abs=1e-9)
    assert out[5] == pytest.approx(0.0, abs=1e-9)
    assert out[6] == pytest.approx(0.0, abs=1e-9)
    for j in (1, 2, 3):
        assert out[j] == pytest.approx(0.01 + 0.02 * (0.01 / 0.03), abs=1e-9)


def test_cap_normalize_handles_all_zero_others() -> None:
    """Edge case : one bucket holds all mass, others all zero. Excess
    falls back to uniform redistribution over the n-1 others."""
    probs = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    out = cap_and_normalize(probs)
    assert out[0] == pytest.approx(0.95, abs=1e-9)
    # Remaining 0.05 distributed uniformly across the 6 others.
    for j in range(1, 7):
        assert out[j] == pytest.approx(0.05 / 6, abs=1e-9)


def test_cap_normalize_rejects_single_element() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        cap_and_normalize([1.0])


def test_cap_normalize_rejects_negative_probability() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        cap_and_normalize([0.5, -0.1, 0.6])


def test_cap_normalize_rejects_zero_sum() -> None:
    with pytest.raises(ValueError, match="positive"):
        cap_and_normalize([0.0, 0.0, 0.0])


def test_cap_normalize_rejects_invalid_cap() -> None:
    with pytest.raises(ValueError, match="cap must be"):
        cap_and_normalize([0.5, 0.5], cap=1.0)
    with pytest.raises(ValueError, match="cap must be"):
        cap_and_normalize([0.5, 0.5], cap=0.0)


def test_cap_normalize_preserves_total_mass() -> None:
    """Pure proportional clipping must preserve sum exactly (up to float)."""
    seeds = [
        [0.9, 0.05, 0.03, 0.01, 0.005, 0.005, 0.0],
        [0.96, 0.02, 0.01, 0.005, 0.003, 0.001, 0.001],
        [0.99, 0.001, 0.001, 0.001, 0.001, 0.003, 0.003],
    ]
    for probs in seeds:
        out = cap_and_normalize(probs)
        assert abs(sum(out) - sum(probs)) < 1e-9


def test_cap_normalize_idempotent_when_already_capped() -> None:
    capped = cap_and_normalize([0.97, 0.01, 0.01, 0.01, 0.0, 0.0, 0.0])
    twice = cap_and_normalize(capped)
    for a, b in zip(capped, twice, strict=True):
        assert a == pytest.approx(b, abs=1e-9)


# ───────────────────────── bucket_for_zscore ──────────────────────────


def test_bucket_for_zscore_extremes() -> None:
    assert bucket_for_zscore(-3.0) == "crash_flush"
    assert bucket_for_zscore(-2.5) == "crash_flush"  # lower-inclusive
    assert bucket_for_zscore(3.0) == "melt_up"
    assert bucket_for_zscore(2.5) == "melt_up"  # upper-inclusive at extreme


def test_bucket_for_zscore_base_band() -> None:
    assert bucket_for_zscore(-0.1) == "base"
    assert bucket_for_zscore(0.0) == "base"
    assert bucket_for_zscore(0.24) == "base"


def test_bucket_for_zscore_boundaries() -> None:
    # Lower-inclusive : z = -1.0 falls into strong_bear (not mild_bear).
    assert bucket_for_zscore(-1.0) == "strong_bear"
    # Upper-exclusive on base : z = 0.25 falls into mild_bull (not base).
    assert bucket_for_zscore(0.25) == "mild_bull"
    # Upper-exclusive on mild_bull : z = 1.0 falls into strong_bull.
    assert bucket_for_zscore(1.0) == "strong_bull"


def test_bucket_for_zscore_all_buckets_reachable() -> None:
    """Every bucket label must be reachable from some z input."""
    reached: set[str] = set()
    for z in (-3.0, -1.5, -0.5, 0.0, 0.5, 1.5, 3.0):
        reached.add(bucket_for_zscore(z))
    assert reached == set(BUCKET_LABELS)
