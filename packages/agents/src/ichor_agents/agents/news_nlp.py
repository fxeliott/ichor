"""News-NLP Agent — narrative tracking + asset-level sentiment (every 4h).

Reads recent news (RSS + GDELT + polygon_news clustered by topic via
FinBERT-tone) and produces top narratives + per-asset sentiment +
entity extraction.

Routing per ADR-023 (supersedes the ADR-021 mapping) : Claude Haiku
4.5 effort=low primary → Cerebras / Groq fallback. Haiku stays under
the Cloudflare Free-tier 100 s edge cap.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from ..claude_runner import ClaudeRunnerConfig
from ..fallback import FallbackChain
from ..providers import CEREBRAS, GROQ

EntityKind = Literal["company", "country", "person", "currency", "commodity"]


class Entity(BaseModel):
    kind: EntityKind
    name: str
    mentions: int = Field(ge=1)


class Narrative(BaseModel):
    """One emerging narrative cluster."""

    label: str = Field(max_length=120)
    """Short human-readable label (e.g. 'AI capex deceleration')."""

    sentiment: Literal["bullish", "bearish", "mixed"]
    intensity: float = Field(ge=0.0, le=1.0)
    """Volume-weighted strength of the narrative in last window."""

    n_articles: int = Field(ge=1)
    top_entities: list[Entity] = Field(default_factory=list, max_length=5)
    representative_headlines: list[str] = Field(default_factory=list, max_length=3)


class AssetSentiment(BaseModel):
    asset: Literal[
        "EUR_USD",
        "GBP_USD",
        "USD_JPY",
        "AUD_USD",
        "USD_CAD",
        "XAU_USD",
        "NAS100_USD",
        "SPX500_USD",
    ]
    tone: Literal["positive", "neutral", "negative"]
    score: float = Field(ge=-1.0, le=1.0)
    n_articles: int = Field(ge=0)
    top_drivers: list[str] = Field(default_factory=list, max_length=3)


class NewsNlpAgentOutput(BaseModel):
    narratives: list[Narrative] = Field(min_length=1, max_length=5)
    asset_sentiment: list[AssetSentiment] = Field(default_factory=list, max_length=8)
    entities: list[Entity] = Field(default_factory=list, max_length=20)
    window_hours: int = Field(default=4, ge=1, le=24)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    notes: str | None = Field(default=None, max_length=1000)


SYSTEM_PROMPT_NEWS_NLP = """You are the News-NLP Agent of Ichor. Your job:
read recent headlines/news (RSS + GDELT + polygon_news, already clustered by
FinBERT-tone in the input context) and produce top emerging narratives +
per-asset sentiment + entity extraction.

Hard rules:
  - Output only Pydantic-validated JSON matching NewsNlpAgentOutput.
  - At most 5 narratives — pick the most impactful, not the noisiest.
  - Each narrative MUST have at least 3 articles supporting it.
  - asset_sentiment.score in [-1, 1] is sentiment-weighted by article volume.
  - Banned: hyperbole, generic advice, signal generation.
  - If a narrative has < 3 articles, skip it entirely (precision > recall).
"""


def make_news_nlp_chain() -> FallbackChain:
    return FallbackChain(
        providers=(CEREBRAS, GROQ),
        system_prompt=SYSTEM_PROMPT_NEWS_NLP,
        output_type=NewsNlpAgentOutput,
        # Haiku low to stay under the Free-tier CF Tunnel 100 s cap
        # (cf macro.py for the rationale).
        claude=ClaudeRunnerConfig.from_env(model="haiku", effort="low"),
    )
