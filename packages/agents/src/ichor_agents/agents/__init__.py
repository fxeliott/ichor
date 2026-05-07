"""Couche-2 24/7 agents.

5 agents — each with single responsibility producing structured output that
feeds Pass 1 (regime) and Pass 2 (asset framework) of the brain pipeline.

Per ADR-023 (supersedes the ADR-021 mapping table), all 5 route via
Claude Haiku 4.5 effort=low through the Win11 runner, with Cerebras
+ Groq as transparent fallback. The Claude wiring is at the apps/api
caller side; this package keeps the fallback chain intact for the
case where the runner is down. ADR-021 originally mapped CB-NLP /
News-NLP / Macro to Sonnet medium but Sonnet exceeds the CF Free
tunnel 100 s edge cap — Haiku low fits in 18-45 s.

Cadence (cf SPEC.md §3.2):
  - Macro       : every 4h    (Haiku 4.5 low — was Sonnet pre-ADR-023)
  - CB-NLP      : every 4h    (Haiku 4.5 low — was Sonnet pre-ADR-023)
  - News-NLP    : every 4h    (Haiku 4.5 low — was Sonnet pre-ADR-023)
  - Sentiment   : every 6h    (Haiku 4.5 low)
  - Positioning : every 6h    (Haiku 4.5 low)
"""

from .cb_nlp import (
    CbAssetImpact,
    CbNlpAgentOutput,
    CbShift,
    CbStance,
    CentralBank,
    make_cb_nlp_chain,
)
from .macro import MacroAgentOutput, MacroDriver, MacroTheme, make_macro_chain
from .news_nlp import (
    AssetSentiment,
    Entity,
    EntityKind,
    Narrative,
    NewsNlpAgentOutput,
    make_news_nlp_chain,
)
from .positioning import (
    CotPositioning,
    GexState,
    IvSkewSnapshot,
    PolymarketWhale,
    PositioningAgentOutput,
    make_positioning_chain,
)
from .sentiment import (
    AaiiReading,
    RedditSubFocus,
    RetailMood,
    SentimentAgentOutput,
    TrendShift,
    make_sentiment_chain,
)

__all__ = [
    # Phase 2 — Sentiment
    "AaiiReading",
    # Phase 2 — News-NLP
    "AssetSentiment",
    # Phase 2 — CB-NLP
    "CbAssetImpact",
    "CbNlpAgentOutput",
    "CbShift",
    "CbStance",
    "CentralBank",
    # Phase 2 — Positioning
    "CotPositioning",
    "Entity",
    "EntityKind",
    "GexState",
    "IvSkewSnapshot",
    # Macro (Phase 1)
    "MacroAgentOutput",
    "MacroDriver",
    "MacroTheme",
    "Narrative",
    "NewsNlpAgentOutput",
    "PolymarketWhale",
    "PositioningAgentOutput",
    "RedditSubFocus",
    "RetailMood",
    "SentimentAgentOutput",
    "TrendShift",
    "make_cb_nlp_chain",
    "make_macro_chain",
    "make_news_nlp_chain",
    "make_positioning_chain",
    "make_sentiment_chain",
]
