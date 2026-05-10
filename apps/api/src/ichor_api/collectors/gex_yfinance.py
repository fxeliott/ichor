"""yfinance-derived dealer GEX collector — wires the dormant `yfinance_options`
schedule slot in register-cron-collectors-extended.sh.

Why this exists : FlashAlpha's free tier is unusable for index/ETF GEX
(SPX/NDX/SPY/QQQ require Basic+ paid plan, single-name on free tier
needs a per-expiry filter and is capped at 5 req/day). We compute
dealer GEX ourselves from yfinance options chains for SPY + QQQ — the
two ETFs whose gamma drives Ichor's regime detection (positive GEX =
mean-revert market, negative = trend-amplify).

Convention : SqueezeMetrics (the most widely-cited public formula) :
  - Dealers are net SHORT calls (clients are net long calls)
  - Dealers are net LONG  puts  (clients are net long puts hedging)
  - dealer_gex_call_per_strike = -1 * gamma * OI * 100 * spot² * 0.01
  - dealer_gex_put_per_strike  = +1 * gamma * OI * 100 * spot² * 0.01
  - Total positive → dealers long gamma → vol-suppressing
  - Total negative → dealers short gamma → vol-amplifying

Trade-offs vs FlashAlpha Basic+ :
  - Cost: $0/mo vs ~$99/mo
  - Precision: ~80% (yfinance OI lags 1 day, IV is yahoo-derived not CBOE)
  - Coverage: full chain across all expirations (FlashAlpha free = 1 expiry)
  - Resilience: zero external commercial dependency (the
    `flashalphalive.com` domain went dark March 2026 — a reminder
    that single-vendor dependencies are fragile).

ADR-022 §dealer GEX strategy. Ships under handler name
`yfinance_options` to match the pre-existing cron slot.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog

log = structlog.get_logger(__name__)


# ── Constants ────────────────────────────────────────────────────────

# Convention : dealers net short calls, net long puts (SqueezeMetrics).
_CALL_DEALER_SIGN = -1.0
_PUT_DEALER_SIGN = +1.0

# Standard listed equity option contract size.
_CONTRACT_MULTIPLIER = 100.0

# Risk-free rate. Black-Scholes gamma is low-sensitivity to r — using
# a static 5% (~current Fed Funds) is sufficient for the regime signal.
# If we later persist FRED DGS3MO daily we can plug it in, but it's not
# load-bearing.
_RISK_FREE_RATE = 0.05

# ETFs we poll. SPY tracks SPX, QQQ tracks NDX — these are the two
# dominant gamma sources for the US equity complex.
WATCHED_TICKERS: tuple[str, ...] = ("SPY", "QQQ")

# Cap how many expiries we pull per ticker. Beyond ~12 weeks out, OI
# dries up and noise dominates ; pulling everything also wastes I/O.
_MAX_EXPIRIES = 8


# ── Types ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DealerGexSnapshot:
    """One dealer GEX snapshot, source-agnostic.

    Fields mirror the `gex_snapshots` table columns (PolygonGexSnapshot
    model) so persistence is a 1:1 mapping.
    """

    asset: str
    captured_at: datetime
    spot: float
    dealer_gex_total: float
    """Net dealer gamma in USD per 1% spot move. Positive =
    vol-suppressing, negative = vol-amplifying."""

    gamma_flip: float | None
    """Strike where cumulative dealer GEX crosses zero — the pivot."""

    call_wall: float | None
    """Strike with the largest absolute call dealer gamma — typical
    resistance level."""

    put_wall: float | None
    """Strike with the largest absolute put dealer gamma — typical
    support level."""

    source: str = "yfinance"
    raw: dict[str, Any] | None = None


# ── Black-Scholes gamma ──────────────────────────────────────────────


def bs_gamma(
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    sigma: float,
    risk_free_rate: float = _RISK_FREE_RATE,
) -> float:
    """Black-Scholes gamma. Returns 0 on degenerate inputs (sigma≤0,
    T≤0, S≤0, K≤0) so callers can safely sum without filtering.

    Formula : Γ = φ(d1) / (S σ √T)
    where d1 = (ln(S/K) + (r + σ²/2) T) / (σ √T)
    and φ is the standard-normal PDF.

    Gamma is identical for calls and puts — only the dealer convention
    sign differs (cf module docstring).
    """
    if sigma <= 0 or time_to_expiry_years <= 0 or spot <= 0 or strike <= 0:
        return 0.0
    sqrt_t = math.sqrt(time_to_expiry_years)
    d1 = (
        math.log(spot / strike) + (risk_free_rate + 0.5 * sigma * sigma) * time_to_expiry_years
    ) / (sigma * sqrt_t)
    pdf = math.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi)
    return pdf / (spot * sigma * sqrt_t)


# ── Aggregation ──────────────────────────────────────────────────────


def aggregate_dealer_gex(
    spot: float,
    options_by_strike: dict[float, dict[str, float]],
) -> tuple[float, float | None, float | None, float | None]:
    """Compute (total_dealer_gex_usd, gamma_flip, call_wall, put_wall).

    Args:
        spot: current underlying price.
        options_by_strike: {strike: {"call_gamma_oi": float, "put_gamma_oi": float}}
            where gamma_oi = sum across expiries of (gamma * open_interest).

    Returns:
        - total_dealer_gex_usd : net dealer gamma per 1% spot move, in USD
        - gamma_flip : strike where running dealer gex crosses zero
          (None if all strikes have same sign)
        - call_wall : strike with max |call dealer gex|
        - put_wall  : strike with max |put dealer gex|

    All four are None if `options_by_strike` is empty.
    """
    if not options_by_strike:
        return 0.0, None, None, None

    strikes = sorted(options_by_strike.keys())
    per_strike: list[tuple[float, float, float, float]] = []  # (K, call_gex, put_gex, total)
    for k in strikes:
        d = options_by_strike[k]
        call_gex = (
            _CALL_DEALER_SIGN
            * d.get("call_gamma_oi", 0.0)
            * _CONTRACT_MULTIPLIER
            * spot
            * spot
            * 0.01
        )
        put_gex = (
            _PUT_DEALER_SIGN
            * d.get("put_gamma_oi", 0.0)
            * _CONTRACT_MULTIPLIER
            * spot
            * spot
            * 0.01
        )
        per_strike.append((k, call_gex, put_gex, call_gex + put_gex))

    total = sum(t[3] for t in per_strike)

    # gamma_flip = the strike where the cumulative-from-low running
    # sum crosses zero. We look for the *closest-to-spot* zero crossing
    # via linear interpolation between adjacent strikes whose running
    # sum changes sign. If no crossing exists (chain entirely one-sided),
    # flip is None.
    running = 0.0
    cumulative: list[tuple[float, float]] = []
    for k, _, _, gex in per_strike:
        running += gex
        cumulative.append((k, running))

    crossings: list[float] = []
    for i in range(1, len(cumulative)):
        prev_k, prev_run = cumulative[i - 1]
        cur_k, cur_run = cumulative[i]
        if (prev_run > 0 and cur_run <= 0) or (prev_run < 0 and cur_run >= 0):
            if cur_run != prev_run:
                t = -prev_run / (cur_run - prev_run)
                crossings.append(prev_k + t * (cur_k - prev_k))
            else:
                crossings.append(cur_k)
    flip_strike = min(crossings, key=lambda x: abs(x - spot)) if crossings else None

    # call_wall = strike with max |call dealer gex|
    # put_wall  = strike with max |put dealer gex|
    call_wall = max(per_strike, key=lambda t: abs(t[1]))[0]
    put_wall = max(per_strike, key=lambda t: abs(t[2]))[0]

    return total, flip_strike, call_wall, put_wall


# ── yfinance bridge ──────────────────────────────────────────────────


def _compute_for_chains(
    spot: float,
    chains: list[tuple[str, Any, Any]],  # [(expiry_str, calls_df, puts_df)]
    *,
    now: datetime,
) -> tuple[dict[float, dict[str, float]], int]:
    """Walk the option chain dataframes, build the per-strike map.

    Returns (options_by_strike, n_contracts_processed).
    """
    options_by_strike: dict[float, dict[str, float]] = {}
    n_contracts = 0
    for expiry_str, calls, puts in chains:
        try:
            expiry = datetime.strptime(expiry_str, "%Y-%m-%d").replace(tzinfo=UTC)
        except (TypeError, ValueError):
            continue
        days_to_expiry = (expiry - now).total_seconds() / 86400.0
        if days_to_expiry <= 0:
            continue
        time_t = days_to_expiry / 365.25

        for df, side in ((calls, "call"), (puts, "put")):
            if df is None:
                continue
            try:
                empty = bool(df.empty)
            except AttributeError:
                # Already a list of rows in tests — handle that path
                empty = len(df) == 0
            if empty:
                continue
            iterator = (
                df.iterrows() if hasattr(df, "iterrows") else ((i, row) for i, row in enumerate(df))
            )
            for _, row in iterator:
                try:
                    strike = (
                        float(row["strike"])
                        if hasattr(row, "__getitem__")
                        else float(getattr(row, "strike", 0.0))
                    )
                    oi_raw = (
                        row["openInterest"]
                        if hasattr(row, "__getitem__")
                        else getattr(row, "openInterest", 0.0)
                    )
                    iv_raw = (
                        row["impliedVolatility"]
                        if hasattr(row, "__getitem__")
                        else getattr(row, "impliedVolatility", 0.0)
                    )
                except (KeyError, TypeError, ValueError):
                    continue
                try:
                    oi = float(oi_raw or 0.0)
                    iv = float(iv_raw or 0.0)
                except (TypeError, ValueError):
                    continue
                if strike <= 0 or oi <= 0 or iv <= 0:
                    continue
                gamma = bs_gamma(spot, strike, time_t, iv)
                bucket = options_by_strike.setdefault(
                    strike, {"call_gamma_oi": 0.0, "put_gamma_oi": 0.0}
                )
                bucket[f"{side}_gamma_oi"] += gamma * oi
                n_contracts += 1
    return options_by_strike, n_contracts


def _sync_fetch(ticker: str, max_expiries: int) -> DealerGexSnapshot | None:
    """Synchronous yfinance pull. Called via asyncio.to_thread to keep
    the event loop responsive.
    """
    try:
        import yfinance as yf
    except ImportError:
        log.warning("gex_yfinance.yfinance_missing", ticker=ticker)
        return None

    t = yf.Ticker(ticker)
    try:
        spot_hist = t.history(period="1d")
        if spot_hist.empty:
            log.warning("gex_yfinance.spot_empty", ticker=ticker)
            return None
        spot = float(spot_hist["Close"].iloc[-1])
    except Exception as e:
        log.warning("gex_yfinance.spot_failed", ticker=ticker, error=str(e)[:200])
        return None

    try:
        expiries = list(t.options)[:max_expiries]
    except Exception as e:
        log.warning("gex_yfinance.expiries_failed", ticker=ticker, error=str(e)[:200])
        return None

    if not expiries:
        log.warning("gex_yfinance.no_expiries", ticker=ticker)
        return None

    chains: list[tuple[str, Any, Any]] = []
    for exp in expiries:
        try:
            chain = t.option_chain(exp)
            chains.append((exp, chain.calls, chain.puts))
        except Exception as e:
            log.warning("gex_yfinance.chain_failed", ticker=ticker, expiry=exp, error=str(e)[:200])

    if not chains:
        return None

    now = datetime.now(UTC)
    options_by_strike, n_contracts = _compute_for_chains(spot, chains, now=now)
    total, flip, call_wall, put_wall = aggregate_dealer_gex(spot, options_by_strike)

    log.info(
        "gex_yfinance.computed",
        ticker=ticker,
        spot=spot,
        total_gex_bn=round(total / 1e9, 3),
        flip=flip,
        n_expiries=len(chains),
        n_contracts=n_contracts,
    )

    return DealerGexSnapshot(
        asset=ticker,
        captured_at=now,
        spot=spot,
        dealer_gex_total=total,
        gamma_flip=flip,
        call_wall=call_wall,
        put_wall=put_wall,
        source="yfinance",
        raw={
            "n_expiries": len(chains),
            "n_strikes": len(options_by_strike),
            "n_contracts": n_contracts,
            "expiries": [e for e, _, _ in chains],
        },
    )


async def fetch_gex_for_ticker(
    ticker: str, *, max_expiries: int = _MAX_EXPIRIES
) -> DealerGexSnapshot | None:
    """Async wrapper. yfinance HTTP calls are sync, run in a thread."""
    return await asyncio.to_thread(_sync_fetch, ticker, max_expiries)


async def poll_all(
    tickers: tuple[str, ...] = WATCHED_TICKERS,
    *,
    max_expiries: int = _MAX_EXPIRIES,
) -> list[DealerGexSnapshot]:
    """Pull all watched tickers concurrently."""
    results = await asyncio.gather(
        *(fetch_gex_for_ticker(t, max_expiries=max_expiries) for t in tickers)
    )
    return [r for r in results if r is not None]


def supported_tickers() -> tuple[str, ...]:
    return WATCHED_TICKERS
