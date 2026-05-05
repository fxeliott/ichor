"""Vol surface — SABR (Hagan) + SVI (Gatheral raw) calibration.

Use for : option-implied skew / kurtosis on FX + indices, IV30 → IV90
term structure features for the Bias Aggregator.

References :
  - Hagan P.S., Kumar D., Lesniewski A., Woodward D. (2002),
    "Managing Smile Risk", Wilmott Magazine, p. 84-108.
  - Gatheral J. (2004), "A parsimonious arbitrage-free implied
    volatility parameterization with application to the valuation of
    volatility derivatives", Global Derivatives Conference.

The Hagan formula approximates SABR-implied **Black-76 lognormal vol**
in closed form, which is what FX market quotes natively use. The SVI
raw parametrization gives **total implied variance** as a function of
log-moneyness ; trivially convertible to vol.

Implementation : pure numpy + scipy.optimize.least_squares (Levenberg-
Marquardt). No vollib dependency — vollib is for the upstream IV back-
out from option premiums, which the upstream feed (OANDA / Tradier /
Polygon options chain) provides directly.

ADR-022 boundary : these models output **probabilities / vol forecasts**,
never BUY/SELL signals. Skew + term structure are inputs to the brain
Pass 2 confluence engine.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares


@dataclass(frozen=True)
class SABRParams:
    """SABR (Hagan-Kumar-Lesniewski-Woodward 2002) implied vol model.

    Notes :
      - alpha > 0 : ATM lognormal vol level.
      - beta ∈ [0, 1] : elasticity. 0 = normal, 0.5 = stochastic-vol CIR,
        1 = lognormal. FX market convention is beta = 1 (lognormal) ;
        equity index convention is often beta = 0.5. Pinned (not fit).
      - rho ∈ (-1, 1) : correlation between price and vol. Negative for
        equity (smirk) ; near zero for FX.
      - nu > 0 : vol-of-vol.
    """

    alpha: float
    beta: float
    rho: float
    nu: float


@dataclass(frozen=True)
class SVIParams:
    """Stochastic Volatility Inspired raw params (Gatheral 2004).

    `total_variance(k) = a + b * (rho * (k - m) + sqrt((k - m)^2 + sigma^2))`

    where k = log(K/F) is log-moneyness. Constraints for arbitrage-
    freeness :
      - b >= 0
      - |rho| < 1
      - sigma > 0
      - a + b * sigma * sqrt(1 - rho^2) >= 0
    """

    a: float
    b: float
    rho: float
    m: float
    sigma: float


@dataclass(frozen=True)
class SABRFitResult:
    params: SABRParams
    rmse: float
    n_iter: int
    success: bool


@dataclass(frozen=True)
class SVIFitResult:
    params: SVIParams
    rmse: float
    n_iter: int
    success: bool


# ─────────────────────────── SABR Hagan formula ───────────────────────────


def hagan_lognormal_vol(
    F: float,
    K: float,
    T: float,
    alpha: float,
    beta: float,
    rho: float,
    nu: float,
) -> float:
    """SABR Black-76 lognormal vol via Hagan (2002) closed-form expansion.

    Args:
        F: forward price.
        K: strike.
        T: time to expiry in years.
        alpha, beta, rho, nu: SABR params.

    Returns:
        Black-76 implied lognormal vol (annualized). Falls back to ATM
        formula when K is within 1 bp of F to avoid log(F/K) → 0
        division.
    """
    if F <= 0 or K <= 0 or T <= 0 or alpha <= 0 or nu < 0:
        return float("nan")
    if abs(rho) >= 1.0:
        return float("nan")

    one_minus_beta = 1.0 - beta
    FK_beta = (F * K) ** (one_minus_beta / 2.0)
    log_FK = math.log(F / K)

    # ATM branch (stable closed form)
    if abs(log_FK) < 1e-7:
        f_pow = F**one_minus_beta
        return (alpha / f_pow) * (
            1.0
            + (
                (one_minus_beta**2 / 24.0) * (alpha**2) / (f_pow**2)
                + (rho * beta * nu * alpha) / (4.0 * f_pow)
                + ((2.0 - 3.0 * rho**2) / 24.0) * nu**2
            )
            * T
        )

    # General branch
    z = (nu / alpha) * FK_beta * log_FK
    sqrt_term = math.sqrt(1.0 - 2.0 * rho * z + z * z)
    x_z = math.log((sqrt_term + z - rho) / (1.0 - rho))

    if abs(x_z) < 1e-12:
        return float("nan")

    correction = 1.0 + (
        (one_minus_beta**2 / 24.0) * (log_FK**2) + (one_minus_beta**4 / 1920.0) * (log_FK**4)
    )
    first = alpha / (FK_beta * correction)
    z_over_x = z / x_z

    higher_order = (
        1.0
        + (
            (one_minus_beta**2 / 24.0) * (alpha**2) / (FK_beta**2)
            + (rho * beta * nu * alpha) / (4.0 * FK_beta)
            + ((2.0 - 3.0 * rho**2) / 24.0) * nu**2
        )
        * T
    )

    return first * z_over_x * higher_order


def fit_sabr_smile(
    strikes: Sequence[float],
    market_ivs: Sequence[float],
    forward: float,
    tenor_years: float,
    *,
    beta: float = 1.0,
    initial_alpha: float = 0.10,
    initial_rho: float = 0.0,
    initial_nu: float = 0.40,
    max_iter: int = 200,
) -> SABRFitResult:
    """Fit SABR (alpha, rho, nu) to a single-tenor IV smile by least squares.

    `beta` is pinned (FX convention 1.0 ; equity-index convention 0.5)
    because the smile alone is not informative enough to identify all
    four params jointly without overfitting (Hagan 2002 §4.2).

    Args:
        strikes: K array.
        market_ivs: market Black-76 lognormal vols.
        forward: F.
        tenor_years: T.
        beta: pinned ; default 1.0 (FX).
        initial_alpha / rho / nu: warm-start.
        max_iter: scipy.optimize cap.

    Returns:
        SABRFitResult with fitted params + RMSE + convergence flag.

    Raises:
        ValueError: if `strikes` and `market_ivs` differ in length, or
            fewer than 3 points provided.
    """
    K = np.asarray(strikes, dtype=np.float64)
    iv = np.asarray(market_ivs, dtype=np.float64)
    if K.shape != iv.shape:
        raise ValueError("strikes and market_ivs must have the same shape")
    if K.size < 3:
        raise ValueError(f"Need at least 3 strikes to fit SABR, got {K.size}")
    if forward <= 0 or tenor_years <= 0:
        raise ValueError("forward and tenor_years must be positive")

    def residuals(theta: np.ndarray) -> np.ndarray:
        alpha, rho, nu = theta
        return np.array(
            [
                hagan_lognormal_vol(forward, k, tenor_years, alpha, beta, rho, nu) - iv_k
                for k, iv_k in zip(K, iv, strict=False)
            ]
        )

    x0 = np.array([initial_alpha, initial_rho, initial_nu])
    bounds = ([1e-6, -0.999, 1e-6], [10.0, 0.999, 10.0])

    res = least_squares(
        residuals,
        x0,
        bounds=bounds,
        method="trf",
        max_nfev=max_iter,
        xtol=1e-10,
        ftol=1e-10,
    )
    alpha, rho, nu = float(res.x[0]), float(res.x[1]), float(res.x[2])
    rmse = float(np.sqrt(np.mean(res.fun**2)))
    return SABRFitResult(
        params=SABRParams(alpha=alpha, beta=beta, rho=rho, nu=nu),
        rmse=rmse,
        n_iter=int(res.nfev),
        success=bool(res.success),
    )


# ─────────────────────────── SVI raw fit ───────────────────────────


def svi_total_variance(
    log_moneyness: float,
    a: float,
    b: float,
    rho: float,
    m: float,
    sigma: float,
) -> float:
    """SVI raw : w(k) = a + b * (rho*(k-m) + sqrt((k-m)^2 + sigma^2))."""
    km = log_moneyness - m
    return a + b * (rho * km + math.sqrt(km * km + sigma * sigma))


def fit_svi_smile(
    log_moneyness: Sequence[float],
    total_variance: Sequence[float],
    *,
    initial_a: float = 0.04,
    initial_b: float = 0.10,
    initial_rho: float = -0.10,
    initial_m: float = 0.0,
    initial_sigma: float = 0.10,
    max_iter: int = 200,
) -> SVIFitResult:
    """Fit SVI raw (a, b, rho, m, sigma) to a single-tenor variance smile.

    Args:
        log_moneyness: k = log(K/F) array.
        total_variance: w = sigma_imp^2 * T array.
        initial_*: warm-start.
        max_iter: scipy.optimize cap.

    Returns:
        SVIFitResult with fitted params + RMSE + convergence flag.

    Raises:
        ValueError: if shapes mismatch or < 5 points (SVI has 5 params).
    """
    k = np.asarray(log_moneyness, dtype=np.float64)
    w = np.asarray(total_variance, dtype=np.float64)
    if k.shape != w.shape:
        raise ValueError("log_moneyness and total_variance must have the same shape")
    if k.size < 5:
        raise ValueError(f"Need at least 5 points to fit SVI raw, got {k.size}")

    def residuals(theta: np.ndarray) -> np.ndarray:
        a, b, rho, m, sigma = theta
        return np.array(
            [svi_total_variance(ki, a, b, rho, m, sigma) - wi for ki, wi in zip(k, w, strict=False)]
        )

    x0 = np.array([initial_a, initial_b, initial_rho, initial_m, initial_sigma])
    bounds = (
        [-1.0, 1e-6, -0.999, -2.0, 1e-6],
        [5.0, 5.0, 0.999, 2.0, 5.0],
    )

    res = least_squares(
        residuals,
        x0,
        bounds=bounds,
        method="trf",
        max_nfev=max_iter,
        xtol=1e-10,
        ftol=1e-10,
    )
    a, b, rho, m, sigma = (float(v) for v in res.x)
    rmse = float(np.sqrt(np.mean(res.fun**2)))
    return SVIFitResult(
        params=SVIParams(a=a, b=b, rho=rho, m=m, sigma=sigma),
        rmse=rmse,
        n_iter=int(res.nfev),
        success=bool(res.success),
    )


# ─────────────────────────── Skew / term-structure features ───────────────


def sabr_25d_risk_reversal(params: SABRParams, forward: float, tenor_years: float) -> float:
    """25-delta risk reversal proxy : IV(K_high_25d) - IV(K_low_25d).

    Approximation : K_25d ≈ F * exp(±0.6745 * ATM_vol * sqrt(T)) — uses
    the Mercurio-Rebonato approximation since solving the exact Black-76
    delta inversion would need scipy. 0.6745 is the 25th-percentile
    z-score (Φ^-1(0.25)).

    Returns:
        IV_25d_call - IV_25d_put. Positive = upside skew (FX EUR/USD
        when calls bid). Negative = downside smirk (typical equity).
    """
    sqrt_T = math.sqrt(tenor_years)
    atm_vol = hagan_lognormal_vol(
        forward, forward, tenor_years, params.alpha, params.beta, params.rho, params.nu
    )
    if math.isnan(atm_vol) or atm_vol <= 0:
        return float("nan")
    log_K_high = 0.6745 * atm_vol * sqrt_T
    log_K_low = -log_K_high
    K_high = forward * math.exp(log_K_high)
    K_low = forward * math.exp(log_K_low)
    iv_high = hagan_lognormal_vol(
        forward, K_high, tenor_years, params.alpha, params.beta, params.rho, params.nu
    )
    iv_low = hagan_lognormal_vol(
        forward, K_low, tenor_years, params.alpha, params.beta, params.rho, params.nu
    )
    return iv_high - iv_low


__all__ = [
    "SABRFitResult",
    "SABRParams",
    "SVIFitResult",
    "SVIParams",
    "fit_sabr_smile",
    "fit_svi_smile",
    "hagan_lognormal_vol",
    "sabr_25d_risk_reversal",
    "svi_total_variance",
]
