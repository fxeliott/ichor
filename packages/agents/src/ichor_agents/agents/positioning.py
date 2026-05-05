"""Positioning Agent — institutional + dealer positioning (every 6h).

Reads COT positions (latest weekly), FlashAlpha GEX live, Polymarket
whales (>$10K bets), IV skew options chains (yfinance), and produces
positioning extremes per asset + dealer gamma flip risk + smart money
divergence vs retail.

Per ADR-021, routes via Claude Haiku 4.5 (primary) with Cerebras
fallback.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from ..fallback import FallbackChain
from ..providers import CEREBRAS, GROQ_HIGH_VOLUME

Asset = Literal[
    "EUR_USD",
    "GBP_USD",
    "USD_JPY",
    "AUD_USD",
    "USD_CAD",
    "XAU_USD",
    "NAS100_USD",
    "SPX500_USD",
]


class CotPositioning(BaseModel):
    asset: Asset
    non_commercial_net: int
    """Net non-commercial (specs) positioning, contracts."""

    week_over_week_change: int
    extreme_pct: float = Field(ge=0.0, le=100.0)
    """Percentile of current net within last 5y distribution.
    >85 or <15 are typical contrarian extremes."""

    flag: Literal["long_extreme", "short_extreme", "neutral"]


class GexState(BaseModel):
    asset: Literal["NAS100_USD", "SPX500_USD"]
    dealer_net_gex_usd: float
    gamma_flip_level: float
    distance_to_flip_pct: float
    """Spot vs gamma_flip distance, signed (+ above flip)."""

    risk: Literal["range_likely", "trend_amplification", "flip_imminent"]


class PolymarketWhale(BaseModel):
    market_slug: str
    question: str
    bet_size_usd: float
    side: Literal["yes", "no"]
    fetched_at: datetime


class IvSkewSnapshot(BaseModel):
    asset: Asset
    risk_reversal_25d: float
    """25-delta risk reversal: positive = call premium > put premium."""

    iv_atm_pct: float


class PositioningAgentOutput(BaseModel):
    cot: list[CotPositioning] = Field(default_factory=list, max_length=8)
    gex: list[GexState] = Field(default_factory=list, max_length=2)
    polymarket_whales: list[PolymarketWhale] = Field(default_factory=list, max_length=10)
    iv_skews: list[IvSkewSnapshot] = Field(default_factory=list, max_length=8)
    smart_money_divergence: list[str] = Field(default_factory=list, max_length=5)
    """List of human-readable divergence flags (e.g. 'COT specs short EUR/USD
    while AAII retail bullish — fade retail')."""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    notes: str | None = Field(default=None, max_length=800)


SYSTEM_PROMPT_POSITIONING = """You are the Positioning Agent of Ichor. Your
job: read COT (latest weekly Tuesday 15:30 ET release), FlashAlpha dealer
GEX (twice-daily SPX/NDX), Polymarket whale bets > $10K (last 6h), and IV
skew options chains. Produce structured positioning extremes + dealer
gamma flip risk + smart money divergence flags.

Hard rules:
  - Output only Pydantic-validated JSON matching PositioningAgentOutput.
  - cot.flag = "long_extreme" if extreme_pct > 85, "short_extreme" if < 15.
  - gex.risk = "flip_imminent" if abs(distance_to_flip_pct) < 0.3.
  - smart_money_divergence flags ≤ 5 strongest signals only — precision > recall.
  - Banned: signal generation, hyperbole.
"""


def make_positioning_chain() -> FallbackChain:
    return FallbackChain(
        providers=(CEREBRAS, GROQ_HIGH_VOLUME),
        system_prompt=SYSTEM_PROMPT_POSITIONING,
        output_type=PositioningAgentOutput,
    )
