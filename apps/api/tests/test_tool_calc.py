"""Unit tests for the calc tool dispatcher (Capability 5 STEP-2)."""

from __future__ import annotations

import math

import pytest
from ichor_api.services.tool_calc import SUPPORTED_OPS, ToolCalcError, calc

# ── Dispatcher ─────────────────────────────────────────────────────


def test_supported_ops_canonical_nine() -> None:
    """Drift guard against ADR-050 § CALC enum."""
    assert SUPPORTED_OPS == frozenset(
        {
            "zscore",
            "rolling_mean",
            "rolling_std",
            "pct_change",
            "log_returns",
            "correlation",
            "percentile",
            "ewma",
            "annualize_vol",
        }
    )


def test_unknown_operation_raises() -> None:
    with pytest.raises(ToolCalcError, match="unknown operation"):
        calc("not_a_real_op", [1.0, 2.0])


def test_non_list_values_raises() -> None:
    with pytest.raises(ToolCalcError, match="must be a list"):
        calc("zscore", "not a list")  # type: ignore[arg-type]


# ── zscore ─────────────────────────────────────────────────────────


def test_zscore_positive_path() -> None:
    out = calc("zscore", [1.0, 2.0, 3.0, 4.0, 5.0])
    assert len(out) == 5
    # Centered: middle value should be 0
    assert math.isclose(out[2], 0.0, abs_tol=1e-9)
    # Symmetric around mean
    assert math.isclose(out[0], -out[4], rel_tol=1e-9)


def test_zscore_constant_series_returns_zeros() -> None:
    out = calc("zscore", [3.0, 3.0, 3.0])
    assert out == [0.0, 0.0, 0.0]


def test_zscore_too_few_values() -> None:
    with pytest.raises(ToolCalcError, match="need at least 2"):
        calc("zscore", [1.0])


# ── rolling_mean / rolling_std ────────────────────────────────────


def test_rolling_mean_window_3() -> None:
    out = calc("rolling_mean", [1.0, 2.0, 3.0, 4.0, 5.0], {"window": 3})
    assert out == pytest.approx([2.0, 3.0, 4.0])


def test_rolling_std_window_2() -> None:
    out = calc("rolling_std", [1.0, 2.0, 3.0], {"window": 2})
    # stdev([1,2]) = stdev([2,3]) = ~0.7071
    assert out == pytest.approx([0.7071067811865476, 0.7071067811865476])


def test_rolling_mean_missing_window() -> None:
    with pytest.raises(ToolCalcError, match="window"):
        calc("rolling_mean", [1.0, 2.0])


# ── pct_change / log_returns ──────────────────────────────────────


def test_pct_change_simple() -> None:
    out = calc("pct_change", [100.0, 110.0, 99.0])
    assert out == pytest.approx([0.10, -0.10])


def test_pct_change_zero_divisor_raises() -> None:
    with pytest.raises(ToolCalcError, match="zero divisor"):
        calc("pct_change", [0.0, 1.0, 2.0])


def test_log_returns_simple() -> None:
    out = calc("log_returns", [math.e, math.e**2, math.e**3])
    assert out == pytest.approx([1.0, 1.0])


def test_log_returns_non_positive_raises() -> None:
    with pytest.raises(ToolCalcError, match="non-positive"):
        calc("log_returns", [1.0, -1.0])


# ── correlation ────────────────────────────────────────────────────


def test_correlation_pearson_perfect_positive() -> None:
    r = calc(
        "correlation",
        [1.0, 2.0, 3.0, 4.0],
        {"other": [10.0, 20.0, 30.0, 40.0]},
    )
    assert math.isclose(r, 1.0, abs_tol=1e-9)


def test_correlation_pearson_perfect_negative() -> None:
    r = calc(
        "correlation",
        [1.0, 2.0, 3.0, 4.0],
        {"other": [40.0, 30.0, 20.0, 10.0]},
    )
    assert math.isclose(r, -1.0, abs_tol=1e-9)


def test_correlation_spearman_works() -> None:
    """Spearman handles non-linear monotonic relationships."""
    r = calc(
        "correlation",
        [1.0, 2.0, 3.0, 4.0],
        {"other": [1.0, 4.0, 9.0, 16.0], "method": "spearman"},
    )
    assert math.isclose(r, 1.0, abs_tol=1e-9)


def test_correlation_missing_other_raises() -> None:
    with pytest.raises(ToolCalcError, match="other"):
        calc("correlation", [1.0, 2.0])


def test_correlation_length_mismatch_raises() -> None:
    with pytest.raises(ToolCalcError, match="same length"):
        calc("correlation", [1.0, 2.0, 3.0], {"other": [1.0, 2.0]})


# ── percentile ─────────────────────────────────────────────────────


def test_percentile_median() -> None:
    p50 = calc("percentile", [1.0, 2.0, 3.0, 4.0, 5.0], {"k": 50})
    assert p50 == pytest.approx(3.0)


def test_percentile_p90() -> None:
    p90 = calc("percentile", [1.0, 2.0, 3.0, 4.0, 5.0], {"k": 90})
    assert p90 == pytest.approx(4.6)


def test_percentile_out_of_range_raises() -> None:
    with pytest.raises(ToolCalcError, match=r"\[0, 100\]"):
        calc("percentile", [1.0, 2.0], {"k": 150})


# ── ewma ───────────────────────────────────────────────────────────


def test_ewma_alpha_one_equals_input() -> None:
    """alpha=1 means we always take the current value."""
    out = calc("ewma", [1.0, 2.0, 3.0], {"alpha": 1.0})
    assert out == [1.0, 2.0, 3.0]


def test_ewma_alpha_half() -> None:
    out = calc("ewma", [10.0, 20.0, 30.0], {"alpha": 0.5})
    assert out == pytest.approx([10.0, 15.0, 22.5])


def test_ewma_alpha_out_of_range_raises() -> None:
    with pytest.raises(ToolCalcError, match=r"\(0, 1\]"):
        calc("ewma", [1.0, 2.0], {"alpha": 0.0})


# ── annualize_vol ──────────────────────────────────────────────────


def test_annualize_vol_default_252() -> None:
    # Constant returns => 0 stdev => 0 vol
    assert calc("annualize_vol", [0.01, 0.01, 0.01]) == 0.0


def test_annualize_vol_simple() -> None:
    # stdev([0.01, -0.01]) = 0.01414... × sqrt(252) ≈ 0.224
    out = calc("annualize_vol", [0.01, -0.01])
    assert out == pytest.approx(0.01414213562 * math.sqrt(252), rel=1e-6)


def test_annualize_vol_custom_periods() -> None:
    out = calc("annualize_vol", [0.01, -0.01], {"periods_per_year": 365})
    assert out == pytest.approx(0.01414213562 * math.sqrt(365), rel=1e-6)


# ── NaN guard ──────────────────────────────────────────────────────


def test_nan_input_raises() -> None:
    # W99 — message split : NaN/inf has its own branch, distinct from
    # non-numeric type errors. Match either.
    with pytest.raises(ToolCalcError, match=r"NaN|non-numeric"):
        calc("zscore", [1.0, float("nan"), 3.0])


def test_inf_input_raises() -> None:
    """W99 regression — inf flowing into statistics ops raised an opaque
    AttributeError instead of ToolCalcError. Now caught by `_no_nan`."""
    with pytest.raises(ToolCalcError, match="inf"):
        calc("zscore", [1.0, float("inf"), 3.0])
    with pytest.raises(ToolCalcError, match="inf"):
        calc("rolling_mean", [1.0, float("-inf"), 3.0, 4.0], {"window": 2})


def test_bool_input_raises() -> None:
    """W99 regression — bool inherits int in Python so isinstance(True, int)
    is True. We reject explicitly to avoid surprising stats outputs."""
    with pytest.raises(ToolCalcError, match="bool"):
        calc("zscore", [True, False, True, True])  # type: ignore[list-item]


def test_correlation_constant_series_raises() -> None:
    """W99 regression — statistics.correlation raised StatisticsError on
    constant input ; now wrapped in ToolCalcError for clean 400."""
    # values constant
    with pytest.raises(ToolCalcError, match="constant"):
        calc("correlation", [1.0, 1.0, 1.0, 1.0], {"other": [1.0, 2.0, 3.0, 4.0]})
    # other constant
    with pytest.raises(ToolCalcError, match="constant"):
        calc("correlation", [1.0, 2.0, 3.0, 4.0], {"other": [5.0, 5.0, 5.0, 5.0]})
