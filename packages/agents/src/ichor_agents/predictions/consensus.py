"""Cross-venue prediction-market consensus aggregator.

Pure-stdlib. Companion to ``divergence.py``: where the divergence detector
surfaces the *spread* between venues on the same event, the consensus
aggregator fuses them into a *single reliability-weighted probability* per
matched event — the clean primitive the downstream analysis engines consume
as a macro prior (e.g. "market-implied P(Fed cut in June) = 70 %").

Why reliability-weighted, not volume-weighted ?
  The three venues report volume in *incompatible units* — Polymarket in USD
  (real money), Kalshi in contract count over 24 h (real money,
  CFTC-regulated), Manifold in "mana" (play money). Multiplying a price by
  raw cross-venue volume would let one venue's unit scale silently dominate
  the blend — a fabricated comparison. Instead we weight by a fixed per-venue
  *reliability* prior: real-money venues carry the estimate, play-money
  Manifold is heavily discounted to a sentiment tilt. Per-venue volume is
  surfaced as context by ``_section_prediction_markets``, not folded into the
  number here.

ADR-017 : this is a *market-implied probability* (descriptive). No BUY/SELL,
entry, target, stop, or sizing is ever derived from it — the consumer treats
it as a macro prior, never a trade signal.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from .divergence import MatchedMarket, Venue

# Real-money venues (Polymarket USDC, Kalshi CFTC-regulated) carry the
# estimate; Manifold is play-money → discounted to a sentiment tilt. Tuned
# conservatively: a lone Manifold price nudges but never sets the consensus
# when a real-money venue is present (see module docstring worked example).
VENUE_RELIABILITY: dict[Venue, float] = {
    "polymarket": 1.0,
    "kalshi": 1.0,
    "manifold": 0.15,
}

# Used only to grade confidence: two agreeing real-money venues is a far
# stronger prior than a real-money + play-money pair.
_REAL_MONEY: frozenset[Venue] = frozenset({"polymarket", "kalshi"})

Confidence = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class ConsensusEstimate:
    """A single fused probability for one cross-venue-matched event."""

    representative_question: str
    consensus_prob: float  # reliability-weighted mean YES ∈ [0, 1]
    n_venues: int  # priced venues that contributed
    dispersion: float  # max - min YES across priced venues (0.0 if 1 priced)
    by_venue: dict[Venue, float]  # priced venue → its YES price
    market_ids: dict[Venue, str]  # priced venue → market_id (provenance)
    confidence: Confidence


def _grade(real_money_prices: list[float], all_prices: list[float]) -> tuple[float, Confidence]:
    """Return ``(dispersion, confidence)``.

    When two real-money venues are priced, both the reported dispersion and
    the confidence grade derive from *their* spread — play-money Manifold
    noise must not tank a real-money agreement (its divergence is surfaced
    separately by the divergence block). A single real-money anchor is always
    a low-confidence prior, with the full cross-venue spread reported.
    """
    if len(real_money_prices) >= 2:
        spread = max(real_money_prices) - min(real_money_prices)
        if spread <= 0.08:
            return spread, "high"
        if spread > 0.15:
            return spread, "low"
        return spread, "medium"
    return (max(all_prices) - min(all_prices)), "low"


def compute_consensus(
    matched: list[MatchedMarket],
    *,
    min_venues: int = 2,
    reliability: dict[Venue, float] | None = None,
) -> list[ConsensusEstimate]:
    """Fuse each matched event's per-venue YES prices into one
    reliability-weighted probability.

    A matched market contributes only if at least ``min_venues`` of its venues
    carry a price (otherwise there is nothing to fuse — surfaced honestly as
    absence rather than a single-venue echo). Results are sorted by confidence
    (high→low) then dispersion ascending, so the analysis engines see the most
    trustworthy priors first.
    """
    if min_venues < 1:
        raise ValueError("min_venues must be >= 1")
    weights = reliability if reliability is not None else VENUE_RELIABILITY

    out: list[ConsensusEstimate] = []
    for m in matched:
        # Defense-in-depth: the upstream venues (Polymarket / Manifold raw
        # float, legacy Kalshi cents) do not guarantee a clean [0, 1] price.
        # Drop NaN / inf / out-of-range as malformed (honest absence) so the
        # fused probability provably stays in [0, 1].
        priced: dict[Venue, float] = {
            v: p.yes_price
            for v, p in m.by_venue.items()
            if p.yes_price is not None and math.isfinite(p.yes_price) and 0.0 <= p.yes_price <= 1.0
        }
        if len(priced) < min_venues:
            continue
        total_w = sum(weights.get(v, 0.0) for v in priced)
        if total_w <= 0:
            continue  # an all-zero-weight blend is undefined → skip honestly
        consensus = sum(weights.get(v, 0.0) * price for v, price in priced.items()) / total_w
        prices = list(priced.values())
        rm_prices = [price for v, price in priced.items() if v in _REAL_MONEY]
        dispersion, confidence = _grade(rm_prices, prices)
        market_ids = {v: m.by_venue[v].market_id for v in priced}
        out.append(
            ConsensusEstimate(
                representative_question=m.representative_question,
                consensus_prob=consensus,
                n_venues=len(priced),
                dispersion=dispersion,
                by_venue=priced,
                market_ids=market_ids,
                confidence=confidence,
            )
        )

    _rank: dict[Confidence, int] = {"high": 0, "medium": 1, "low": 2}
    out.sort(key=lambda c: (_rank[c.confidence], c.dispersion))
    return out
