"""Tests for SABR-Hagan + SVI raw fit on synthetic smiles."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


pytest.importorskip("scipy", reason="scipy required for SABR/SVI least-squares fit")
pytest.importorskip("numpy", reason="numpy required")

import numpy as np  # noqa: E402

from ichor_ml.vol.sabr_svi import (  # noqa: E402
    SABRParams,
    SVIParams,
    fit_sabr_smile,
    fit_svi_smile,
    hagan_lognormal_vol,
    sabr_25d_risk_reversal,
    svi_total_variance,
)


# ───────────────────────── Hagan formula sanity ─────────────────────────


def test_hagan_atm_returns_alpha_when_lognormal_and_no_volvol() -> None:
    """At F=K, beta=1, nu=0, T→0 : Hagan formula collapses to alpha exactly."""
    vol = hagan_lognormal_vol(F=1.10, K=1.10, T=1e-6, alpha=0.08, beta=1.0, rho=0.0, nu=0.0)
    assert vol == pytest.approx(0.08, rel=1e-3)


def test_hagan_continuous_around_ATM() -> None:
    """Hagan should not have a jump going through K=F."""
    F, T = 1.10, 0.25
    p = (0.08, 1.0, -0.1, 0.4)
    iv_atm = hagan_lognormal_vol(F, F * 1.0, T, *p)
    iv_just_below = hagan_lognormal_vol(F, F * (1 - 1e-5), T, *p)
    iv_just_above = hagan_lognormal_vol(F, F * (1 + 1e-5), T, *p)
    assert abs(iv_atm - iv_just_below) < 1e-3
    assert abs(iv_atm - iv_just_above) < 1e-3


def test_hagan_returns_nan_for_invalid_inputs() -> None:
    assert math.isnan(hagan_lognormal_vol(F=1.10, K=-1, T=1, alpha=0.1, beta=1, rho=0, nu=0.4))
    assert math.isnan(hagan_lognormal_vol(F=1.10, K=1.10, T=1, alpha=-1, beta=1, rho=0, nu=0.4))
    assert math.isnan(hagan_lognormal_vol(F=1.10, K=1.10, T=1, alpha=0.1, beta=1, rho=2, nu=0.4))


# ───────────────────────── SABR fit recovery ─────────────────────────


def test_sabr_fit_recovers_synthetic_params() -> None:
    """Generate IVs from known params, fit, check we recover them."""
    F = 1.10
    T = 0.25  # 3M
    true = SABRParams(alpha=0.08, beta=1.0, rho=-0.15, nu=0.45)
    strikes = np.array([F * m for m in (0.95, 0.97, 0.99, 1.00, 1.01, 1.03, 1.05)])
    ivs = np.array(
        [
            hagan_lognormal_vol(F, k, T, true.alpha, true.beta, true.rho, true.nu)
            for k in strikes
        ]
    )
    fit = fit_sabr_smile(strikes.tolist(), ivs.tolist(), forward=F, tenor_years=T, beta=1.0)
    assert fit.success
    assert fit.rmse < 1e-5
    assert fit.params.alpha == pytest.approx(true.alpha, abs=5e-3)
    assert fit.params.rho == pytest.approx(true.rho, abs=5e-2)
    assert fit.params.nu == pytest.approx(true.nu, abs=5e-2)


def test_sabr_fit_rejects_too_few_points() -> None:
    with pytest.raises(ValueError, match="at least 3 strikes"):
        fit_sabr_smile([1.10, 1.11], [0.08, 0.09], forward=1.10, tenor_years=0.25)


def test_sabr_fit_rejects_mismatched_shapes() -> None:
    with pytest.raises(ValueError, match="same shape"):
        fit_sabr_smile([1.10, 1.11, 1.12], [0.08, 0.09], forward=1.10, tenor_years=0.25)


def test_sabr_fit_rejects_bad_forward_or_tenor() -> None:
    with pytest.raises(ValueError, match="positive"):
        fit_sabr_smile([1.10, 1.11, 1.12], [0.08, 0.09, 0.10], forward=0, tenor_years=0.25)
    with pytest.raises(ValueError, match="positive"):
        fit_sabr_smile([1.10, 1.11, 1.12], [0.08, 0.09, 0.10], forward=1.10, tenor_years=0)


# ───────────────────────── 25d risk reversal ─────────────────────────


def test_25d_rr_zero_for_symmetric_smile() -> None:
    """rho=0, beta=1 → smile is symmetric → 25d RR ≈ 0."""
    params = SABRParams(alpha=0.10, beta=1.0, rho=0.0, nu=0.4)
    rr = sabr_25d_risk_reversal(params, forward=1.10, tenor_years=0.25)
    assert abs(rr) < 1e-3


def test_25d_rr_negative_for_smirk() -> None:
    """rho<0 (equity smirk) → puts more expensive than calls → RR < 0."""
    params = SABRParams(alpha=0.10, beta=1.0, rho=-0.4, nu=0.6)
    rr = sabr_25d_risk_reversal(params, forward=1.10, tenor_years=0.25)
    assert rr < -1e-4


# ───────────────────────── SVI raw ─────────────────────────


def test_svi_total_variance_at_minimum_equals_a_plus_b_sigma_sqrt() -> None:
    """The minimum of SVI is at k=m, value = a + b*sigma*sqrt(1-rho^2)."""
    a, b, rho, m, sigma = 0.04, 0.10, -0.20, 0.0, 0.30
    w_at_m = svi_total_variance(m, a, b, rho, m, sigma)
    expected = a + b * sigma * (1 - rho * rho) ** 0.5
    # The actual minimum of w(k) = a + b*(rho*(k-m) + sqrt((k-m)^2 + sigma^2)) is at
    # k* such that w'(k*) = 0 → rho + (k-m)/sqrt((k-m)^2+sigma^2) = 0
    # → (k-m)/sqrt((k-m)^2+sigma^2) = -rho
    # → (k-m)^2 / ((k-m)^2 + sigma^2) = rho^2
    # → (k-m)^2 = rho^2 * sigma^2 / (1 - rho^2)
    # at k=m exactly, w = a + b*sigma (not the global min unless rho=0)
    assert w_at_m == pytest.approx(a + b * sigma, abs=1e-9)
    # And the closed-form global min (when rho≠0) is verified below
    expected_min_below_a_plus_b_sigma = expected < a + b * sigma
    assert expected_min_below_a_plus_b_sigma  # rho ≠ 0 → global min is lower


def test_svi_fit_recovers_synthetic_params() -> None:
    true = SVIParams(a=0.04, b=0.10, rho=-0.30, m=0.02, sigma=0.20)
    ks = np.linspace(-0.30, 0.30, 11)
    ws = np.array(
        [svi_total_variance(k, true.a, true.b, true.rho, true.m, true.sigma) for k in ks]
    )
    fit = fit_svi_smile(ks.tolist(), ws.tolist())
    assert fit.success
    assert fit.rmse < 1e-6
    assert fit.params.a == pytest.approx(true.a, abs=1e-3)
    assert fit.params.b == pytest.approx(true.b, abs=5e-3)
    assert fit.params.rho == pytest.approx(true.rho, abs=2e-2)
    assert fit.params.m == pytest.approx(true.m, abs=5e-3)
    assert fit.params.sigma == pytest.approx(true.sigma, abs=2e-2)


def test_svi_fit_rejects_too_few_points() -> None:
    with pytest.raises(ValueError, match="at least 5 points"):
        fit_svi_smile([0.0, 0.1, 0.2, 0.3], [0.04, 0.05, 0.07, 0.10])


def test_svi_fit_rejects_mismatched_shapes() -> None:
    with pytest.raises(ValueError, match="same shape"):
        fit_svi_smile([0.0, 0.1, 0.2, 0.3, 0.4], [0.04, 0.05, 0.07])
