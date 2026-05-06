"""yfinance options chains collector — put/call ratio + IV skew.

Free, no API key. Yahoo Finance options data is unofficially-scraped but
the `yfinance` library handles the parsing. This collector deliberately
avoids the import-time cost of yfinance: it imports the lib lazily.

Captures, per asset (and per expiration):
  - Put/Call open-interest ratio
  - Put/Call volume ratio
  - ATM IV
  - 25-delta risk reversal proxy (call IV − put IV at ±5% from spot)
  - Open interest by side

Cf https://www.codearmo.com/python-tutorial/calculate-options-metrics-python
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class OptionsSnapshot:
    """One snapshot of options data for one underlying."""

    ticker: str
    spot: float | None
    expiry: str  # ISO date
    pcr_open_interest: float | None
    pcr_volume: float | None
    atm_iv: float | None
    risk_reversal_25d: float | None  # call_iv - put_iv at strike ≈ spot × 1.05 vs spot × 0.95
    total_call_oi: int
    total_put_oi: int
    fetched_at: datetime


def _safe_div(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or den == 0:
        return None
    return num / den


def _nearest_strike(strikes: list[float], target: float) -> float | None:
    if not strikes:
        return None
    return min(strikes, key=lambda s: abs(s - target))


def compute_metrics(
    ticker: str,
    expiry: str,
    spot: float | None,
    calls: list[dict[str, Any]],
    puts: list[dict[str, Any]],
) -> OptionsSnapshot:
    """Pure function on dicts (so it's testable without yfinance).

    Defensive against NaN inputs : Yahoo's option_chain DataFrame
    sometimes carries NaN volume/openInterest for very recent
    contracts (no fills yet). `int(NaN)` raises ; coerce-to-zero
    instead so a single bad row doesn't kill the whole compute.
    """

    def _safe_int(x: object) -> int:
        if x is None:
            return 0
        try:
            f = float(x)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0
        return 0 if (f != f) else int(f)  # f != f → NaN

    call_oi = sum(_safe_int(c.get("openInterest")) for c in calls)
    put_oi = sum(_safe_int(p.get("openInterest")) for p in puts)
    call_vol = sum(_safe_int(c.get("volume")) for c in calls)
    put_vol = sum(_safe_int(p.get("volume")) for p in puts)

    atm_iv: float | None = None
    rr25: float | None = None
    if spot is not None and calls and puts:
        call_strikes = [float(c["strike"]) for c in calls if c.get("strike") is not None]
        atm = _nearest_strike(call_strikes, spot)
        if atm is not None:
            atm_call = next((c for c in calls if float(c.get("strike", 0)) == atm), None)
            if atm_call is not None:
                iv = atm_call.get("impliedVolatility")
                atm_iv = float(iv) if iv is not None else None
        otm_call_target = spot * 1.05
        otm_put_target = spot * 0.95
        otm_call_strike = _nearest_strike(call_strikes, otm_call_target)
        put_strikes = [float(p["strike"]) for p in puts if p.get("strike") is not None]
        otm_put_strike = _nearest_strike(put_strikes, otm_put_target)
        if otm_call_strike is not None and otm_put_strike is not None:
            otm_call = next(
                (c for c in calls if float(c.get("strike", 0)) == otm_call_strike), None
            )
            otm_put = next((p for p in puts if float(p.get("strike", 0)) == otm_put_strike), None)
            if otm_call is not None and otm_put is not None:
                civ = otm_call.get("impliedVolatility")
                piv = otm_put.get("impliedVolatility")
                if civ is not None and piv is not None:
                    rr25 = float(civ) - float(piv)

    return OptionsSnapshot(
        ticker=ticker,
        spot=spot,
        expiry=expiry,
        pcr_open_interest=_safe_div(float(put_oi), float(call_oi)),
        pcr_volume=_safe_div(float(put_vol), float(call_vol)),
        atm_iv=atm_iv,
        risk_reversal_25d=rr25,
        total_call_oi=call_oi,
        total_put_oi=put_oi,
        fetched_at=datetime.now(UTC),
    )


def fetch_options_snapshot(ticker: str) -> list[OptionsSnapshot]:
    """Fetch full options chain across all expirations for one ticker.

    Lazy-imports yfinance. Returns one OptionsSnapshot per expiry.
    Returns [] on any failure.
    """
    try:
        import yfinance as yf
    except ImportError:
        return []
    try:
        tk = yf.Ticker(ticker)
        spot_hist = tk.history(period="1d")
        spot = float(spot_hist["Close"].iloc[-1]) if not spot_hist.empty else None
        expiries = list(tk.options or [])
    except Exception:
        return []

    out: list[OptionsSnapshot] = []
    for expiry in expiries:
        try:
            chain = tk.option_chain(expiry)
        except Exception:
            continue
        # Convert pandas DataFrames to list[dict] for the pure metric calc.
        calls_df = getattr(chain, "calls", None)
        puts_df = getattr(chain, "puts", None)
        if calls_df is None or puts_df is None:
            continue
        try:
            calls = calls_df.to_dict(orient="records")
            puts = puts_df.to_dict(orient="records")
        except Exception:
            continue
        out.append(compute_metrics(ticker, expiry, spot, calls, puts))
    return out


# Ichor universe: NAS100 + SPX500 are tracked via index ETFs (QQQ + SPY).
WATCHED_TICKERS: tuple[str, ...] = ("SPY", "QQQ", "GLD", "DIA", "IWM")
