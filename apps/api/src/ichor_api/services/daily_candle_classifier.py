"""r168b G4 — Daily candle classifier + Garman-Klass volatility helper.

Closes the r167 honest-gap on ``TradeabilityFlag = "range"`` literal
which currently returns ``always False`` (``tradeability_evaluator.py:335``).
When the previous daily candle shows an uncertainty/doji pattern AND
the realized volatility is materially compressed vs the trailing 30d
Garman-Klass baseline, the day is classified as ``range`` — Eliot's
discipline = no NY-session trade.

**Eliot's verbatim mandate** (Fathom 2026-05-25 §IV.4) : « Bougie
d'incertitude après baisse → fin baisse probable » + §VIII : « avoid
range markets ». G4 mechanises the second half : Ichor surfaces an
honest "ne trade pas aujourd'hui — marché en range" disclosure rather
than emitting a verdict that the trader would have to override.

Pattern #15 R59 doctrinal posture
==================================

Nison Japanese Candlesticks (1991) body/range thresholds 0.7/0.3 are
**RETAIL conventions, NOT peer-reviewed**. Marshall-Young-Rose 2006
*Journal of Banking & Finance* 30:2303-2323
DOI 10.1016/j.jbankfin.2005.08.001 ran the canonical empirical test of
candlestick patterns on DJIA 1992-2002 with bootstrap controls — found
**NO statistically significant excess returns** vs randomly generated
sequences. The 2012 Lu-Shiu-Liu *Review of Financial Economics*
follow-up found marginal Taiwan-only profitability ; Marshall-Young-
Cahan 2008 *RQFA* confirmed null result in Japan. The body/range
classification therefore ships with the explicit ``HONEST_SENTINEL =
"low_signal_confidence_candle"`` (4th axis in the calibrated-honesty
ladder after r150 ``single_source_direction`` + r153
``asymmetric_negativity_bias`` + r155 ``low_signal_confidence``).

The composite ``is_range_bound`` rule pairs the unreliable candle
classification with a **peer-reviewed volatility estimator** so the
"range" disclosure surfaces only when BOTH a soft-signal (candle) AND
a hard-signal (compressed realized vol) agree :

  - **Garman-Klass 1980** *Journal of Business* 53(1) 67-78
    DOI 10.1086/296072 — single-bar OHLC variance estimator,
    5-7× more efficient than close-to-close when full OHLC is
    available. Standard formula :

        σ²_GK = 0.5 · (ln(H/L))² − (2·ln(2) − 1) · (ln(C/O))²

  - The 0.8 compression ratio threshold is a **deterministic
    statistical convention** (one standard deviation rounded ;
    consistent with r168a G3 ±0.7σ band) NOT a peer-reviewed
    citation claim — Pattern #15 R59 immune by design.

Architecture (atomic, doctrine #2 strict scope)
================================================

This module ships THREE pure functions + ONE async DB read :

  * ``classify_daily_candle(prev_ohlc, curr_ohlc) -> DailyCandleClassification``
    Pure mechanical classification. Returns one of 6 literal kinds
    (``momentum_bull/bear/uncertainty/engulfing_bull/bear/neutral``)
    + 1-line rationale + body/range ratio + the HONEST_SENTINEL flag.

  * ``garman_klass_variance(o, h, l, c) -> float | None``
    Pure single-bar GK variance per the 1980 formula. Returns ``None``
    on degenerate input (non-positive price, h < l).

  * ``is_range_bound(session, asset, now_utc) -> (bool, reason)``
    Composite async rule consumed by ``tradeability_evaluator``. Reads
    the trailing 32 ``market_data`` rows for the asset, classifies
    the latest candle, computes the rolling 30d GK mean, and returns
    ``(True, reason)`` iff uncertainty candle AND GK vol below 80%
    trailing mean. Doctrine #11 honest fallback : returns
    ``(False, None)`` on insufficient data (false-negative preferred
    on a discipline gate where false-positive would block a normal
    trading day).

Doctrine alignment
==================

- **ADR-017** boundary : no BUY/SELL emission. The classification is
  descriptive metadata ; the trader interprets according to discipline.
- **Voie D** : ZERO Anthropic SDK consumption. Pure math + async SQL.
  Voie D streak +1 = 86 rounds.
- **Doctrine #2 strict scope** : single module wires a single literal
  (``TradeabilityFlag = "range"``). No new ADR, no new field exposed
  on ``SessionVerdict`` (r169+ candidate if frontend wants to surface
  the kind explicitly).
- **Doctrine #4 SSOT** : ``MarketDataBar`` imported canonical ;
  ``TradeabilityFlag`` Literal unchanged from r167 (this module just
  makes the ``"range"`` value reachable in the dispatch tree).
- **Doctrine #11 calibrated honesty** : HONEST_SENTINEL caveat in
  every classification output. ``(False, None)`` on data unavailable
  rather than fabricating a verdict.
- **Doctrine #12 anti-recidive** : Pattern #15 R59 pre-flight verified
  Marshall-Young-Rose 2006 *JBF* candlestick NULL result + Garman-Klass
  1980 peer-reviewed range-based volatility. No memory hallucination
  to propagate (lineage : r147 Bauer DP21003 catch + r150 PIVOT 1 VIX
  5y + r168a Whaley 1993 VIX>20 catch).

Empirical validation strategy
==============================

The classifier is testable as a pure function (no DB needed for
``classify_daily_candle`` + ``garman_klass_variance``). The composite
``is_range_bound`` is tested with mocked async session returning
deterministic OHLC fixtures. Post-deploy empirical witness on Hetzner
prod requires R-WITNESS-EMPIRICAL (r144 codified) : verify the
``range`` flag fires on at least one real trading day where market
WAS objectively range-bound (e.g., late August 2025 low-vol weeks).

Sources of truth
================
  - ``services/tradeability_evaluator.py:335`` — explicit wire-point
    comment ``# r168 G4 will set : await _is_range_bound_3_day(...)``
  - ``models/market_data.py:13-43`` — MarketDataBar ORM
  - Garman-Klass 1980 *J. Business* 53:67-78 DOI 10.1086/296072
  - Marshall-Young-Rose 2006 *J. Banking & Finance* 30:2303-2323
    DOI 10.1016/j.jbankfin.2005.08.001
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import MarketDataBar

log = structlog.get_logger(__name__)


# ─────────────────────────── Public Literal types ───────────────────────────


# Eliot §IV.4 verbatim taxonomy : the daily candle that just closed
# (D-1) frames the bias for the next NY session (D-day). 6 mechanical
# kinds covering the practitioner vocabulary ; future r169+ candidate
# = extend with hammer / shooting-star / harami once peer-reviewed
# support is documented (Lo-Mamaysky-Wang 2000 JoF kernel regression
# is the only credible academic anchor — and it's STATISTICAL, not
# pattern-based, so a re-architecture would be needed).
DailyCandleKind = Literal[
    "momentum_bull",  # body/range >= 0.7 AND close > open
    "momentum_bear",  # body/range >= 0.7 AND close < open
    "uncertainty",  # body/range < 0.3 (doji-like)
    "engulfing_bull",  # curr body > 1.5x prev body, sign flip bear→bull
    "engulfing_bear",  # curr body > 1.5x prev body, sign flip bull→bear
    "neutral",  # 0.3 <= body/range < 0.7 (mid-body, no clear pattern)
]


# HONEST_SENTINEL ladder — 4th axis per r155 codification.
# Mirrors r150 ``single_source_direction`` + r153
# ``asymmetric_negativity_bias`` + r155 ``low_signal_confidence``.
DailyCandleSentinel = Literal["low_signal_confidence_candle"]


@dataclass(frozen=True)
class DailyCandleClassification:
    """Output of ``classify_daily_candle`` — kind + rationale + body
    ratio + HONEST_SENTINEL flag.

    The ``honest_sentinel`` field is always populated (never None) for
    r168b — every output carries the Marshall-Young-Rose 2006 *JBF*
    caveat by construction. Future r169+ candidate : pair with a
    z-score self-calibrating body/range distribution over the asset's
    own trailing 60d distribution to lift the sentinel when the
    signal is statistically distinguishable from the asset's own
    history."""

    kind: DailyCandleKind
    rationale: str
    body_to_range_ratio: float
    honest_sentinel: DailyCandleSentinel


# ───────────────────────── Body/range thresholds ────────────────────────────


_BODY_RATIO_MOMENTUM: float = 0.7
"""Body/range >= 0.7 → momentum classification. Nison 1991 retail
convention. Marshall-Young-Rose 2006 *JBF* DOI 10.1016/j.jbankfin.
2005.08.001 empirically disproves statistical significance vs bootstrap
random series on DJIA 1992-2002. Kept here as a deterministic threshold
paired with HONEST_SENTINEL output discipline."""


_BODY_RATIO_UNCERTAINTY: float = 0.3
"""Body/range < 0.3 → uncertainty (doji-like). Same Nison retail
provenance, same Marshall-Young-Rose 2006 NULL-result caveat, same
HONEST_SENTINEL discipline."""


_ENGULFING_BODY_MULTIPLIER: float = 1.5
"""Current body must be 1.5x the previous body for engulfing detection
(single-source retail convention — no peer-reviewed academic anchor).
HONEST_SENTINEL applies."""


# ───────────────────────── Pure classifier ──────────────────────────────────


def classify_daily_candle(
    *,
    prev_ohlc: tuple[float, float, float, float] | None,
    curr_ohlc: tuple[float, float, float, float],
) -> DailyCandleClassification:
    """Classify the current daily candle given the previous candle for
    engulfing detection. Pure function — no DB access, deterministic.

    Priority order (first match wins) :
      1. **engulfing_bull** — prev bear, curr bull, body > 1.5x prev
      2. **engulfing_bear** — prev bull, curr bear, body > 1.5x prev
      3. **momentum_bull** — body/range >= 0.7, close > open
      4. **momentum_bear** — body/range >= 0.7, close < open
      5. **uncertainty** — body/range < 0.3
      6. **neutral** — mid-body (default)

    Args :
      prev_ohlc : (open, high, low, close) of D-2 candle, or None.
        When None, engulfing patterns cannot be detected ; the
        result falls back to momentum/uncertainty/neutral.
      curr_ohlc : (open, high, low, close) of D-1 candle (the daily
        candle that just closed before the D-day NY session).

    Returns :
      ``DailyCandleClassification`` with kind + rationale + body/range
      ratio + HONEST_SENTINEL flag.

    Doctrine #11 calibrated honesty : on degenerate candle (range == 0,
    high == low), returns ``uncertainty`` with rationale citing the
    degeneracy. NEVER raises — always returns a classification with
    the HONEST_SENTINEL flag intact.
    """
    open_, high, low, close = curr_ohlc
    body = abs(close - open_)
    rng = high - low

    # Degenerate candle (high == low) — vanishingly rare on liquid
    # FX/index daily bars but possible on illiquid extended-hours bars.
    if rng <= 0:
        return DailyCandleClassification(
            kind="uncertainty",
            rationale=f"degenerate candle (range=0, high={high}, low={low})",
            body_to_range_ratio=0.0,
            honest_sentinel="low_signal_confidence_candle",
        )

    body_ratio = body / rng

    # Engulfing detection (requires prev_ohlc with non-zero body).
    if prev_ohlc is not None:
        prev_open, _prev_high, _prev_low, prev_close = prev_ohlc
        prev_body = abs(prev_close - prev_open)
        prev_bull = prev_close > prev_open
        prev_bear = prev_close < prev_open
        curr_bull = close > open_
        curr_bear = close < open_

        if (
            prev_body > 0
            and body > prev_body * _ENGULFING_BODY_MULTIPLIER
            and prev_bull
            and curr_bear
        ):
            return DailyCandleClassification(
                kind="engulfing_bear",
                rationale=(
                    f"engulfing bear : body {body:.4f} > prev body "
                    f"{prev_body:.4f} × {_ENGULFING_BODY_MULTIPLIER}, "
                    "sign flip bull→bear"
                ),
                body_to_range_ratio=body_ratio,
                honest_sentinel="low_signal_confidence_candle",
            )
        if (
            prev_body > 0
            and body > prev_body * _ENGULFING_BODY_MULTIPLIER
            and prev_bear
            and curr_bull
        ):
            return DailyCandleClassification(
                kind="engulfing_bull",
                rationale=(
                    f"engulfing bull : body {body:.4f} > prev body "
                    f"{prev_body:.4f} × {_ENGULFING_BODY_MULTIPLIER}, "
                    "sign flip bear→bull"
                ),
                body_to_range_ratio=body_ratio,
                honest_sentinel="low_signal_confidence_candle",
            )

    # Momentum (body dominates range)
    if body_ratio >= _BODY_RATIO_MOMENTUM:
        if close > open_:
            return DailyCandleClassification(
                kind="momentum_bull",
                rationale=(
                    f"momentum bull : body/range={body_ratio:.2f} >= "
                    f"{_BODY_RATIO_MOMENTUM}, close>open"
                ),
                body_to_range_ratio=body_ratio,
                honest_sentinel="low_signal_confidence_candle",
            )
        if close < open_:
            return DailyCandleClassification(
                kind="momentum_bear",
                rationale=(
                    f"momentum bear : body/range={body_ratio:.2f} >= "
                    f"{_BODY_RATIO_MOMENTUM}, close<open"
                ),
                body_to_range_ratio=body_ratio,
                honest_sentinel="low_signal_confidence_candle",
            )

    # Uncertainty (small body relative to range — doji-like)
    if body_ratio < _BODY_RATIO_UNCERTAINTY:
        return DailyCandleClassification(
            kind="uncertainty",
            rationale=(
                f"uncertainty (doji-like) : body/range={body_ratio:.2f} < {_BODY_RATIO_UNCERTAINTY}"
            ),
            body_to_range_ratio=body_ratio,
            honest_sentinel="low_signal_confidence_candle",
        )

    # Neutral mid-body — default when no other rule fired.
    return DailyCandleClassification(
        kind="neutral",
        rationale=f"neutral mid-body : body/range={body_ratio:.2f}",
        body_to_range_ratio=body_ratio,
        honest_sentinel="low_signal_confidence_candle",
    )


# ───────────────────────── Garman-Klass 1980 ────────────────────────────────


def garman_klass_variance(open_: float, high: float, low: float, close: float) -> float | None:
    """Single-bar Garman-Klass 1980 *Journal of Business* 53(1) 67-78
    DOI 10.1086/296072 range-based variance estimator. 5-7× more
    efficient than close-to-close when full OHLC is available.

    Formula : σ²_GK = 0.5 · (ln(H/L))² − (2·ln(2) − 1) · (ln(C/O))²

    The first term captures the intraday range information ; the
    second term subtracts the squared close-to-open drift contribution.
    The coefficient (2·ln(2) − 1) ≈ 0.38629 is the analytic constant
    that makes the estimator drift-independent under Brownian motion
    assumptions.

    Returns :
      The variance σ² (NOT σ ; caller squares-root if standard
      deviation is needed). Returns ``None`` if any input is
      non-positive OR if high < low (degenerate bar). NEVER raises.
    """
    if min(open_, high, low, close) <= 0 or high < low:
        return None

    try:
        log_hl = math.log(high / low)
        log_co = math.log(close / open_)
    except (ValueError, ZeroDivisionError):
        return None

    return 0.5 * log_hl**2 - (2 * math.log(2) - 1) * log_co**2


# ───────────────────────── Composite range-bound rule ───────────────────────


_RANGE_GK_COMPRESSION_RATIO: float = 0.8
"""Current GK variance must be below 80% of the trailing 30d GK mean
for ``range`` classification. 0.8 is a deterministic threshold (~one
standard deviation below mean, statistical convention consistent with
r168a G3 ±0.7σ band). Future r169+ candidate : replace with z-score
self-calibrating over the asset's own GK variance distribution."""


_RANGE_TRAILING_DAYS: int = 30
"""Trailing window for the GK variance mean baseline. Mirrors the
``hourly_volatility`` window used by ``tradeability_evaluator``
``low_volatility`` gate (Doctrine #4 SSOT cadence)."""


_RANGE_FETCH_BUFFER_DAYS: int = 45
"""Calendar-day buffer when querying ``market_data`` — covers weekend
+ holiday gaps so we reliably get 30 trading-day bars in the rolling
window. 45 calendar days ≈ 30 trading days post weekend pruning."""


_RANGE_MIN_BARS_REQUIRED: int = 31
"""Need at least 1 current candle + 30 trailing for the GK mean
baseline. Below this threshold the function returns ``(False, None)``
(honest absence — false-negative preferred on discipline gate)."""


async def is_range_bound(
    session: AsyncSession,
    *,
    asset: str,
    now_utc: datetime | None = None,
) -> tuple[bool, str | None]:
    """Composite range-bound classification for the r167
    ``TradeabilityFlag = "range"`` wire-point.

    Returns ``(True, reason)`` iff BOTH conditions hold :

      1. The latest D-1 daily candle is classified as ``uncertainty``
         (body/range < 0.3) per ``classify_daily_candle``.

      2. The current candle's Garman-Klass variance is below 80% of
         the trailing 30 trading-day GK mean baseline.

    Returns ``(False, None)`` otherwise OR on insufficient data
    (< 31 bars in the trailing 45 calendar-day window).

    Doctrine #11 calibrated honesty : false-negative preferred over
    false-positive on a discipline gate. If we can't be sure the market
    is range-bound, we let the trader decide (other tradeability gates
    may still surface a different honest-absence flag).

    Args :
      session : SQLAlchemy async session.
      asset : the priority asset code (EUR_USD / GBP_USD / XAU_USD /
              SPX500_USD / NAS100_USD).
      now_utc : evaluation time ; defaults to ``datetime.now(UTC)``.
    """
    if now_utc is None:
        now_utc = datetime.now(UTC)

    since = now_utc.date() - timedelta(days=_RANGE_FETCH_BUFFER_DAYS)
    stmt = (
        select(MarketDataBar)
        .where(
            MarketDataBar.asset == asset,
            MarketDataBar.bar_date >= since,
        )
        .order_by(MarketDataBar.bar_date.desc())
        .limit(32)
    )
    rows = list((await session.execute(stmt)).scalars().all())

    # Doctrine #11 honest fallback : insufficient data → (False, None).
    if len(rows) < _RANGE_MIN_BARS_REQUIRED:
        return (False, None)

    # Latest D-1 candle + previous for engulfing detection.
    curr_row = rows[0]
    prev_row = rows[1] if len(rows) >= 2 else None

    curr_ohlc = (curr_row.open, curr_row.high, curr_row.low, curr_row.close)
    prev_ohlc = (prev_row.open, prev_row.high, prev_row.low, prev_row.close) if prev_row else None

    classification = classify_daily_candle(prev_ohlc=prev_ohlc, curr_ohlc=curr_ohlc)

    # Gate 1 : uncertainty candle (else not range — return False).
    if classification.kind != "uncertainty":
        return (False, None)

    # Gate 2 : current GK variance must be compressed vs 30d mean.
    curr_gk = garman_klass_variance(*curr_ohlc)
    if curr_gk is None:
        return (False, None)

    trailing_gks: list[float] = []
    for r in rows[1 : 1 + _RANGE_TRAILING_DAYS]:
        gk = garman_klass_variance(r.open, r.high, r.low, r.close)
        if gk is not None:
            trailing_gks.append(gk)

    if not trailing_gks:
        return (False, None)

    trailing_mean = sum(trailing_gks) / len(trailing_gks)

    if curr_gk >= trailing_mean * _RANGE_GK_COMPRESSION_RATIO:
        return (False, None)

    reason = (
        f"range : uncertainty candle ({classification.rationale}) AND "
        f"Garman-Klass variance {curr_gk:.6f} < "
        f"{_RANGE_GK_COMPRESSION_RATIO} × trailing-30d mean "
        f"{trailing_mean:.6f}"
    )
    return (True, reason)


__all__ = [
    "DailyCandleClassification",
    "DailyCandleKind",
    "DailyCandleSentinel",
    "classify_daily_candle",
    "garman_klass_variance",
    "is_range_bound",
]
