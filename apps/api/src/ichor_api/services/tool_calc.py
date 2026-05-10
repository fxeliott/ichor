"""calc tool handler — Capability 5 STEP-2 (W84+, ADR-071).

Pure stdlib math dispatcher for the 9 deterministic operations declared
in `tools_registry.CALC.input_schema.operation.enum`:

  zscore, rolling_mean, rolling_std, pct_change, log_returns,
  correlation, percentile, ewma, annualize_vol

NO I/O, NO model invocation, NO data fetching. ADR-017-safe by
construction (the output is a number or list of numbers — cannot leak
"buy"/"sell" verbs).

Used by the orchestrator's Pass 2 + Pass 3 (per `CALC.primary_passes`)
when Claude needs to derive a deterministic statistic from a values
array surfaced in the data_pool — e.g. compute a z-score of the
current MCT trend vs the trailing-5y series.
"""

from __future__ import annotations

import math
import statistics
from typing import Any

# Public list of supported operations — locked to ADR-050 enum.
SUPPORTED_OPS: frozenset[str] = frozenset(
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


class ToolCalcError(ValueError):
    """Raised on bad inputs (empty array, NaN, unknown op, etc.)."""


def _need_min_length(values: list[float], n: int, op: str) -> None:
    if len(values) < n:
        raise ToolCalcError(f"{op}: need at least {n} values, got {len(values)}")


def _no_nan(values: list[float], op: str) -> None:
    """W99 — reject non-numeric, NaN, AND infinity. Also reject `bool`
    (which Python's `isinstance(v, int)` treats as numeric, but
    statistically meaningless for stats ops). Defense added post code
    review : `inf` flowing into `statistics.fmean` raises an opaque
    `AttributeError` that the router cannot translate to a useful 400.
    """
    for i, v in enumerate(values):
        if isinstance(v, bool):
            raise ToolCalcError(f"{op}: bool not numeric at index {i}")
        if not isinstance(v, (int, float)):
            raise ToolCalcError(f"{op}: non-numeric at index {i}: {type(v).__name__}")
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            raise ToolCalcError(f"{op}: NaN/inf at index {i}: {v}")


# ── Operations ───────────────────────────────────────────────────


def _op_zscore(values: list[float], params: dict[str, Any]) -> list[float]:
    """Element-wise z-score against the values' own mean + stdev.

    Returns a list of z-scores (same length as input). Stdev uses
    sample (n-1) by default; pass `population=True` to use n.
    """
    _need_min_length(values, 2, "zscore")
    _no_nan(values, "zscore")
    use_pop = bool(params.get("population", False))
    mu = statistics.fmean(values)
    sigma = statistics.pstdev(values) if use_pop else statistics.stdev(values)
    if sigma == 0:
        # Constant series — every z-score is 0 by convention.
        return [0.0] * len(values)
    return [(v - mu) / sigma for v in values]


def _op_rolling_mean(values: list[float], params: dict[str, Any]) -> list[float]:
    """Trailing rolling mean of size `window`. First (window-1) outputs
    are dropped (returned list shorter than input)."""
    window = int(params.get("window", 0))
    if window < 1:
        raise ToolCalcError("rolling_mean: `window` param must be >= 1")
    _need_min_length(values, window, "rolling_mean")
    _no_nan(values, "rolling_mean")
    return [
        statistics.fmean(values[i - window + 1 : i + 1]) for i in range(window - 1, len(values))
    ]


def _op_rolling_std(values: list[float], params: dict[str, Any]) -> list[float]:
    """Trailing rolling sample stdev (n-1) of size `window`."""
    window = int(params.get("window", 0))
    if window < 2:
        raise ToolCalcError("rolling_std: `window` param must be >= 2")
    _need_min_length(values, window, "rolling_std")
    _no_nan(values, "rolling_std")
    return [
        statistics.stdev(values[i - window + 1 : i + 1]) for i in range(window - 1, len(values))
    ]


def _op_pct_change(values: list[float], params: dict[str, Any]) -> list[float]:
    """Element-wise percent change v[i]/v[i-1] - 1. Returns list of
    length n-1."""
    _need_min_length(values, 2, "pct_change")
    _no_nan(values, "pct_change")
    out: list[float] = []
    for i in range(1, len(values)):
        if values[i - 1] == 0:
            raise ToolCalcError(f"pct_change: zero divisor at index {i - 1}")
        out.append(values[i] / values[i - 1] - 1.0)
    return out


def _op_log_returns(values: list[float], params: dict[str, Any]) -> list[float]:
    """Element-wise log-return ln(v[i]/v[i-1]). All values must be > 0."""
    _need_min_length(values, 2, "log_returns")
    _no_nan(values, "log_returns")
    for i, v in enumerate(values):
        if v <= 0:
            raise ToolCalcError(f"log_returns: non-positive value at index {i}: {v}")
    return [math.log(values[i] / values[i - 1]) for i in range(1, len(values))]


def _op_correlation(values: list[float], params: dict[str, Any]) -> float:
    """Pearson correlation of `values` (interpreted as the X array)
    with `params['other']` (the Y array). Defaults to Pearson; pass
    `method='spearman'` for Spearman rank correlation."""
    other = params.get("other")
    if not isinstance(other, list):
        raise ToolCalcError("correlation: `params.other` (second array) is required")
    if len(other) != len(values):
        raise ToolCalcError(
            f"correlation: arrays must be same length ({len(values)} vs {len(other)})"
        )
    _need_min_length(values, 2, "correlation")
    _no_nan(values, "correlation")
    _no_nan(other, "correlation")
    # W99 — pre-check for constant series. statistics.correlation raises
    # StatisticsError("at least one of the inputs is constant") which
    # bubbles up as a generic 500 if not caught. Translate to a
    # ToolCalcError for a clean 400 + useful message to the agent.
    if statistics.pstdev(values) == 0:
        raise ToolCalcError("correlation: first array is constant (sigma=0)")
    if statistics.pstdev(other) == 0:
        raise ToolCalcError("correlation: second array is constant (sigma=0)")
    method = str(params.get("method", "pearson")).lower()
    if method not in {"pearson", "spearman"}:
        raise ToolCalcError(f"correlation: unknown method '{method}' (pearson | spearman)")
    if method == "spearman":
        return statistics.correlation(values, other, method="ranked")
    return statistics.correlation(values, other)


def _op_percentile(values: list[float], params: dict[str, Any]) -> float:
    """Return the k-th percentile (0..100). Linear interpolation."""
    k = params.get("k")
    if k is None:
        raise ToolCalcError("percentile: `params.k` (0..100) is required")
    k_f = float(k)
    if not (0.0 <= k_f <= 100.0):
        raise ToolCalcError(f"percentile: k must be in [0, 100], got {k_f}")
    _need_min_length(values, 1, "percentile")
    _no_nan(values, "percentile")
    if len(values) == 1:
        return values[0]
    sorted_v = sorted(values)
    n = len(sorted_v)
    # Linear interpolation between closest ranks.
    rank = (k_f / 100.0) * (n - 1)
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return sorted_v[lo]
    frac = rank - lo
    return sorted_v[lo] + frac * (sorted_v[hi] - sorted_v[lo])


def _op_ewma(values: list[float], params: dict[str, Any]) -> list[float]:
    """Exponentially-weighted moving average. Pass `alpha` in (0, 1].
    Output length matches input; first element is values[0]."""
    alpha = float(params.get("alpha", 0))
    if not (0.0 < alpha <= 1.0):
        raise ToolCalcError(f"ewma: alpha must be in (0, 1], got {alpha}")
    _need_min_length(values, 1, "ewma")
    _no_nan(values, "ewma")
    out = [values[0]]
    for v in values[1:]:
        out.append(alpha * v + (1 - alpha) * out[-1])
    return out


def _op_annualize_vol(values: list[float], params: dict[str, Any]) -> float:
    """Annualised volatility = stdev(values) * sqrt(periods_per_year).
    `periods_per_year` defaults to 252 (trading days)."""
    periods = int(params.get("periods_per_year", 252))
    if periods < 1:
        raise ToolCalcError(f"annualize_vol: periods_per_year must be >= 1, got {periods}")
    _need_min_length(values, 2, "annualize_vol")
    _no_nan(values, "annualize_vol")
    return statistics.stdev(values) * math.sqrt(periods)


_DISPATCH: dict[str, Any] = {
    "zscore": _op_zscore,
    "rolling_mean": _op_rolling_mean,
    "rolling_std": _op_rolling_std,
    "pct_change": _op_pct_change,
    "log_returns": _op_log_returns,
    "correlation": _op_correlation,
    "percentile": _op_percentile,
    "ewma": _op_ewma,
    "annualize_vol": _op_annualize_vol,
}


def calc(operation: str, values: list[float], params: dict[str, Any] | None = None) -> Any:
    """Dispatch a deterministic math operation. Returns float | list[float].

    Raises `ToolCalcError` on bad input (unknown op, empty/NaN values,
    missing params, divide-by-zero on pct_change, log of non-positive,
    etc.).
    """
    if operation not in SUPPORTED_OPS:
        raise ToolCalcError(f"unknown operation '{operation}'. Supported: {sorted(SUPPORTED_OPS)}")
    if not isinstance(values, list):
        raise ToolCalcError(f"`values` must be a list, got {type(values).__name__}")
    return _DISPATCH[operation](values, params or {})


__all__ = ["SUPPORTED_OPS", "ToolCalcError", "calc"]
