"""Unit tests for `services.scenario_calibration` — pure logic only.

The DB-touching paths (`fetch_session_window_returns`, `compute_
calibration_bins`, `persist_calibration`) are exercised via integration
tests separately ; these tests pin the EWMA, the per-asset unit
translation, the fallback magnitudes, the cold-start behaviour, and
the prompt-block formatter.
"""

from __future__ import annotations

import math

import pytest
from ichor_api.services.scenario_calibration import (
    _FALLBACK_1SIG_PIPS,
    _PIP_UNIT_FACTOR,
    CONFIDENCE_FLOOR,
    EWMA_LAMBDA,
    _ewma_std,
    compute_calibration_bins_from_returns,
    format_calibration_block,
)
from ichor_brain.scenarios import BUCKET_Z_THRESHOLDS

# ─────────────────────── EWMA σ pure function ────────────────────────


def test_ewma_std_empty_returns_nan() -> None:
    assert math.isnan(_ewma_std([]))


def test_ewma_std_single_observation_returns_magnitude() -> None:
    # n=1 can't compute variance ; return |r|.
    assert _ewma_std([0.005]) == 0.005
    assert _ewma_std([-0.012]) == 0.012


def test_ewma_std_constant_returns_converge_to_magnitude() -> None:
    # RiskMetrics zero-mean convention : σ² = E[r²] not E[(r-mean)²].
    # Steady state σ² = (1-λ)·r² + λ·σ² → σ² = r² → σ = |r|.
    sigma = _ewma_std([0.001] * 100)
    assert sigma == pytest.approx(0.001, rel=1e-6)


def test_ewma_std_lambda_default_matches_riskmetrics() -> None:
    # Sanity : λ=0.94 is the RiskMetrics convention. The function must
    # honour the default, and `_ewma_std(returns, lam=0.94)` matches
    # `_ewma_std(returns)`.
    rets = [0.005, -0.003, 0.002, 0.001, -0.004]
    assert _ewma_std(rets) == _ewma_std(rets, lam=EWMA_LAMBDA)
    assert EWMA_LAMBDA == 0.94


def test_ewma_std_responsive_to_recent_shock() -> None:
    # 100 small returns then 1 large shock → EWMA σ should be higher
    # than the EW-equal alternative (because λ<1 down-weights past).
    quiet = [0.001] * 100
    shock = [0.05]
    sigma_post = _ewma_std(quiet + shock)
    sigma_pre = _ewma_std(quiet)
    assert sigma_post > sigma_pre + 1e-6


# ─────────── compute_calibration_bins_from_returns (pure) ───────────


def test_cold_start_uses_fallback_magnitude_table() -> None:
    # 0 returns → falls back to _FALLBACK_1SIG_PIPS["EUR_USD"] = 35.0
    res = compute_calibration_bins_from_returns("EUR_USD", "pre_londres", [])
    assert res.sample_n == 0
    assert res.sigma_pips == _FALLBACK_1SIG_PIPS["EUR_USD"]
    assert res.bins_z_thresholds == list(BUCKET_Z_THRESHOLDS)
    # z=-2.5 → -2.5 * 35.0 pips = -87.5 pips.
    assert res.bins_pip_thresholds[0] == pytest.approx(-87.5)
    assert res.bins_pip_thresholds[-1] == pytest.approx(87.5)


def test_sub_floor_sample_uses_fallback() -> None:
    # sample_n < CONFIDENCE_FLOOR (60) → fallback regardless of value.
    rets = [0.001] * (CONFIDENCE_FLOOR - 1)
    res = compute_calibration_bins_from_returns("USD_JPY", "pre_ny", rets)
    assert res.sample_n == CONFIDENCE_FLOOR - 1
    assert res.sigma_pips == _FALLBACK_1SIG_PIPS["USD_JPY"]


def test_above_floor_uses_ewma_times_unit_factor() -> None:
    # Synthetic : 252 returns of magnitude 0.001 → σ ≈ 0.001 ; for
    # EUR_USD (factor 10000), σ_pips = 10. z=-2.5 → -25 pips.
    rets = [0.001 if i % 2 == 0 else -0.001 for i in range(252)]
    res = compute_calibration_bins_from_returns("EUR_USD", "pre_londres", rets)
    assert res.sample_n == 252
    assert res.sigma_pips > 0.0
    assert res.sigma_pips < 20.0  # sanity ; not the fallback (35.0)
    # z thresholds line up with σ_pips scaling.
    expected_low = -2.5 * res.sigma_pips
    expected_high = 2.5 * res.sigma_pips
    assert res.bins_pip_thresholds[0] == pytest.approx(expected_low, abs=1e-9)
    assert res.bins_pip_thresholds[-1] == pytest.approx(expected_high, abs=1e-9)


def test_per_asset_unit_factor_distinct() -> None:
    # FX majors except USD_JPY = 10000 ; USD_JPY = 100 ; XAU/indices = 1.
    assert _PIP_UNIT_FACTOR["EUR_USD"] == 10_000.0
    assert _PIP_UNIT_FACTOR["GBP_USD"] == 10_000.0
    assert _PIP_UNIT_FACTOR["USD_CAD"] == 10_000.0
    assert _PIP_UNIT_FACTOR["USD_JPY"] == 100.0
    assert _PIP_UNIT_FACTOR["XAU_USD"] == 1.0
    assert _PIP_UNIT_FACTOR["NAS100_USD"] == 1.0
    assert _PIP_UNIT_FACTOR["SPX500_USD"] == 1.0


def test_xau_uses_usd_unit_not_pips() -> None:
    rets = [0.002] * 252
    res = compute_calibration_bins_from_returns("XAU_USD", "pre_ny", rets)
    # Factor 1.0 ; σ_pips ≈ 0.002 directly (USD price points).
    # The point is just : not multiplied by 10000.
    assert res.sigma_pips < 1.0


def test_index_assets_use_unit_factor_1() -> None:
    rets = [0.01] * 252  # 1% session return
    res = compute_calibration_bins_from_returns("NAS100_USD", "ny_close", rets)
    # Factor 1.0 ; σ_pips ≈ 0.01 directly. Not realistic NDX magnitude
    # but the function is unit-only ; production data feeds index
    # points not log-returns at the production layer.
    assert res.sigma_pips < 0.05


def test_fallback_magnitude_realistic_per_asset() -> None:
    # Sanity ranges from researcher 2026-05-12 web review.
    assert 20.0 <= _FALLBACK_1SIG_PIPS["EUR_USD"] <= 60.0
    assert 25.0 <= _FALLBACK_1SIG_PIPS["GBP_USD"] <= 70.0
    assert 20.0 <= _FALLBACK_1SIG_PIPS["USD_CAD"] <= 60.0
    assert 15.0 <= _FALLBACK_1SIG_PIPS["USD_JPY"] <= 60.0
    assert 5.0 <= _FALLBACK_1SIG_PIPS["XAU_USD"] <= 30.0
    assert 50.0 <= _FALLBACK_1SIG_PIPS["NAS100_USD"] <= 300.0
    assert 10.0 <= _FALLBACK_1SIG_PIPS["SPX500_USD"] <= 80.0


def test_calibration_result_dataclass_immutable() -> None:
    rets = [0.001] * 252
    res = compute_calibration_bins_from_returns("EUR_USD", "pre_londres", rets)
    with pytest.raises((AttributeError, Exception)):
        res.sample_n = 999  # type: ignore[misc] — frozen dataclass


# ─────────── format_calibration_block — prompt-friendly ───────────


def test_format_calibration_block_contains_canonical_thresholds() -> None:
    res = compute_calibration_bins_from_returns("EUR_USD", "pre_londres", [])
    block = format_calibration_block(res)
    # Block should mention EWMA λ + the 6 z-thresholds + per-asset unit.
    assert "EWMA" in block
    assert "0.94" in block
    assert "EUR_USD" in block
    assert "pre_londres" in block
    # 6 z thresholds printed.
    for z in BUCKET_Z_THRESHOLDS:
        assert f"{z:+.2f}" in block


def test_format_calibration_block_unit_label_per_asset() -> None:
    res_fx = compute_calibration_bins_from_returns("EUR_USD", "pre_londres", [])
    assert "pips" in format_calibration_block(res_fx)

    res_xau = compute_calibration_bins_from_returns("XAU_USD", "pre_ny", [])
    assert "USD" in format_calibration_block(res_xau)

    res_nas = compute_calibration_bins_from_returns("NAS100_USD", "ny_close", [])
    assert "points" in format_calibration_block(res_nas)


# ─────────── ADR-085 invariants — boundaries via canonical tuple ───────────


def test_bins_z_thresholds_match_canonical_tuple() -> None:
    res = compute_calibration_bins_from_returns("EUR_USD", "pre_londres", [])
    # Doctrinal pin : the rendered z-thresholds match the canonical
    # 6-tuple from ichor_brain.scenarios.BUCKET_Z_THRESHOLDS — defence
    # against silent drift if a future sub-wave reorders or mutates
    # the canonical thresholds.
    assert tuple(res.bins_z_thresholds) == BUCKET_Z_THRESHOLDS


def test_bins_pip_thresholds_strictly_monotone() -> None:
    rets = [0.002] * 252
    res = compute_calibration_bins_from_returns("EUR_USD", "pre_londres", rets)
    pips = res.bins_pip_thresholds
    # 6 boundaries ; each strictly greater than the previous.
    for i in range(1, len(pips)):
        assert pips[i] > pips[i - 1]
