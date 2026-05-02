"""Vol surface — SABR + SVI fit via vollib (1.0.7+, ex-py_vollib per AUDIT_V3 §2).

Use for : option-implied skew/kurtosis on FX + indices, IV30 → IV90 term
structure features for the Bias Aggregator.

Phase 0 scaffold — full implementation Phase 1 once OANDA + Tradier feeds
provide options-chain data.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SABRParams:
    """SABR (Hagan-Kumar-Lesniewski-Woodward) implied vol model params."""
    alpha: float
    beta: float
    rho: float
    nu: float


@dataclass
class SVIParams:
    """Stochastic Volatility Inspired (Gatheral 2004) raw params."""
    a: float
    b: float
    rho: float
    m: float
    sigma: float


def fit_sabr_smile(
    strikes: list[float],
    market_ivs: list[float],
    forward: float,
    tenor_years: float,
    *,
    beta: float = 0.5,
) -> SABRParams:
    """Fit SABR to a single tenor smile.

    Phase 0: stub returning placeholder. Full impl in Phase 1 — needs vollib
    + scipy.optimize.least_squares.

    Args:
        strikes: array of strike prices
        market_ivs: array of market implied vols (Black-Scholes vol for FX)
        forward: forward price
        tenor_years: time to expiry in years
        beta: SABR beta (0=normal, 0.5=square-root, 1=lognormal). Default 0.5.

    Returns:
        SABRParams (alpha, beta, rho, nu)
    """
    # TODO Phase 1: real fit via vollib.black_scholes.implied_volatility
    # and scipy.optimize.least_squares
    raise NotImplementedError(
        "SABR fit pending Phase 1 (needs OANDA/Tradier options feed). "
        "Ticket: model_registry.yaml id 'sabr-eurusd-v0' status=planned"
    )


def fit_svi_smile(
    log_moneyness: list[float],
    total_variance: list[float],
) -> SVIParams:
    """Fit SVI raw to a single tenor smile (Gatheral parametrization).

    Phase 0: stub.
    """
    raise NotImplementedError(
        "SVI fit pending Phase 1 — see model_registry.yaml id 'svi-eurusd-v0'"
    )
