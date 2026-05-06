"""Sentiment Agent — retail / contrarian sentiment (every 6h).

Reads AAII Sentiment Survey (weekly), Reddit /r/wallstreetbets +
/r/forex + /r/stockmarket + /r/Gold (last 6h via PRAW), Google Trends
(pytrends watchlist) and produces a retail sentiment map + contrarian
extreme flags + emerging themes.

Routing : Claude Haiku 4.5 effort=low (ADR-021 + reaffirmed by
ADR-023) primary, Cerebras + Groq high-volume fallback. Haiku is
the cheapest premium model and fits the 6h cadence + the CF Free
tunnel budget.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from ..claude_runner import ClaudeRunnerConfig
from ..fallback import FallbackChain
from ..providers import CEREBRAS, GROQ_HIGH_VOLUME

RetailMood = Literal["euphoric", "bullish", "neutral", "bearish", "panic"]


class AaiiReading(BaseModel):
    bullish_pct: float = Field(ge=0.0, le=1.0)
    bearish_pct: float = Field(ge=0.0, le=1.0)
    neutral_pct: float = Field(ge=0.0, le=1.0)
    spread: float
    """bullish_pct - bearish_pct, in [-1, 1]. Extreme readings (+/- 0.4)
    are statistically contrarian per AAII historical data."""

    week_ending: datetime


class RedditSubFocus(BaseModel):
    subreddit: Literal["wallstreetbets", "forex", "stockmarket", "Gold"]
    mood: RetailMood
    top_tickers_mentioned: list[str] = Field(default_factory=list, max_length=10)
    n_posts_analyzed: int = Field(ge=0)
    extreme_flag: bool = False
    """True if mood + volume hits a contrarian extreme threshold."""


class TrendShift(BaseModel):
    """Google Trends watchlist shift."""

    query: str
    delta_24h: float
    """Percentile change vs the previous 24h baseline."""


class SentimentAgentOutput(BaseModel):
    aaii: AaiiReading | None = None
    reddit: list[RedditSubFocus] = Field(default_factory=list, max_length=4)
    google_trends_shifts: list[TrendShift] = Field(default_factory=list, max_length=10)
    overall_retail_mood: RetailMood
    contrarian_signal: Literal["fade_retail_bullish", "fade_retail_bearish", "no_extreme"]
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    notes: str | None = Field(default=None, max_length=800)


SYSTEM_PROMPT_SENTIMENT = """You are the Sentiment Agent of Ichor. Your job:
read AAII Sentiment Survey (weekly), Reddit posts (last 6h, /r/wallstreetbets,
/r/forex, /r/stockmarket, /r/Gold), and Google Trends watchlist deltas.
Produce a retail sentiment map + contrarian extreme flags.

Hard rules:
  - Output only Pydantic-validated JSON matching SentimentAgentOutput.
  - AAII spread in [-1, 1]: extreme = abs(spread) > 0.4 (rare but contrarian).
  - reddit.extreme_flag = True only if mood = euphoric/panic AND post volume
    is in top 10% of the trailing 30d distribution.
  - contrarian_signal = "fade_retail_bullish" if AAII spread > 0.4 OR if 2+
    subreddits flag euphoric extreme; "fade_retail_bearish" if symmetric.
  - Banned: signal generation ("buy", "sell"), hyperbole.
"""


def make_sentiment_chain() -> FallbackChain:
    # Haiku-class budget: high-volume cadence (every 6h × ~50 inputs).
    # Claude Haiku primary per ADR-021; Cerebras + Groq high-volume
    # model as fallback when the runner is down.
    return FallbackChain(
        providers=(CEREBRAS, GROQ_HIGH_VOLUME),
        system_prompt=SYSTEM_PROMPT_SENTIMENT,
        output_type=SentimentAgentOutput,
        claude=ClaudeRunnerConfig.from_env(model="haiku", effort="low"),
    )
