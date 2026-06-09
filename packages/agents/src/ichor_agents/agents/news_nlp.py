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

from pydantic import BaseModel, Field, field_validator

from ..claude_runner import ClaudeRunnerConfig
from ..fallback import FallbackChain
from ..providers import CEREBRAS, GROQ
from ._free_text import truncate_free_text

EntityKind = Literal["company", "country", "person", "currency", "commodity"]


class Entity(BaseModel):
    kind: EntityKind
    name: str
    mentions: int = Field(ge=0)


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

    @field_validator("sentiment", mode="before")
    @classmethod
    def _normalize_news_tone_drift_on_sentiment(cls, v: object) -> object:
        """r172b calibrated-honesty normalizer — MIRROR of the r161
        ``_normalize_mixed_tone`` precedent at ``AssetSentiment.tone`` (line
        ~88 below), but in the REVERSE direction : Haiku low has been
        observed to emit the news-tone vocabulary ``{positive, negative,
        neutral}`` (which lives on the sibling ``AssetSentiment.tone``
        Literal) in this ``Narrative.sentiment`` field instead of the
        FX-trader directional vocabulary ``{bullish, bearish, mixed}``.

        Witnessed prod failure 2026-05-28 00:47:21 UTC on
        ``ichor-couche2@news_nlp.service`` :
        ``narratives.3.sentiment='positive'`` violating the Literal narrows
        to a Pydantic ValidationError that crashed the agent run
        (``ClaudeRunnerOutputError`` → fallback Cerebras+Groq skipped
        because credentials absent → ``AllProvidersFailed``). 7d aggregate
        post-r170 hooks-PS1-unlock = 25.6% news_nlp fail rate (R2 audit
        finding B1, 2026-05-28).

        Root cause : the LLM sees TWO sibling sentiment fields in the SAME
        ``NewsNlpAgentOutput`` schema with DIFFERENT vocabularies
        (``Narrative.sentiment`` directional vs ``AssetSentiment.tone``
        news-tone). Haiku low generalises the news-tone vocab from one
        field to the other (same generalisation class as the r161
        ``'mixed'`` drift, opposite direction). Prompt-only fix has
        proven insufficient across multiple rounds — structural defense
        beats prompt engineering (doctrine #12 anti-recidive).

        Doctrine #11 calibrated-honesty mapping policy : news-tone DOES
        NOT translate directly to directional bias (hot CPI = positive
        macro tone = bearish equities OR bullish bonds, depending on
        regime). Therefore we map ``{positive, negative, neutral} →
        'mixed'`` — honest acknowledgement that the LLM did not commit
        to a direction we can safely infer. The 'mixed' bucket already
        exists as a legitimate doctrine-#11 output (no schema surface
        drift). Information loss is preferred over fabricated direction.

        Fix mechanics (per doctrine #2 strict scope, mirror r161) : a
        ``mode='before'`` validator that maps the 3 news-tone tokens to
        ``'mixed'`` BEFORE the Literal narrows. Byte-identical for
        non-violating outputs (no consumer change). Pre-r172b ~25.6% 7d
        fail rate ; expected post-fix ~0% on this specific drift class.
        """
        if isinstance(v, str):
            normalized = v.strip().lower()
            if normalized in {"positive", "negative", "neutral"}:
                return "mixed"
        return v


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

    @field_validator("tone", mode="before")
    @classmethod
    def _normalize_mixed_tone(cls, v: object) -> object:
        """r161 calibrated-honesty normalizer — Haiku low has demonstrated
        drift emitting `'mixed'` tone (witnessed prod failure 2026-05-25
        20:47:41 CEST on ``ichor-couche2@news_nlp.service`` :
        ``asset_sentiment.1.tone='mixed'`` violating the Literal narrows
        to a 500-class Pydantic ValidationError that crashed the agent
        run).

        Root cause : the sibling ``Narrative.sentiment`` Literal at line
        38 above explicitly includes ``'mixed'`` as a valid value within
        the same NewsNlpAgentOutput schema — Haiku generalises this
        token from one field to the other. Sibling pattern applied to
        ``cb_nlp.CbNlp.bias`` (Literal of the same tri-state shape, same
        contamination risk).

        Fix mechanics (per doctrine #2 strict scope) : a ``mode="before"``
        validator that maps ``'mixed' → 'neutral'`` BEFORE the Literal
        narrows. Byte-identical for non-violating outputs (no consumer
        change), zero contract surface drift (ADR-023 tri-state
        semantics preserved), structural defense beats prompt
        engineering (which Haiku has drifted across r147-r155).
        """
        if isinstance(v, str) and v.strip().lower() == "mixed":
            return "neutral"
        return v


# Canonical asset universe for AssetSentiment.asset — used by the resilience
# validator below to DROP hallucinated asset codes (2026-06-05) rather than let
# one bad row fail the whole agent output.
_VALID_NEWS_ASSETS: frozenset[str] = frozenset(
    {"EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD", "XAU_USD", "NAS100_USD", "SPX500_USD"}
)


class NewsNlpAgentOutput(BaseModel):
    narratives: list[Narrative] = Field(min_length=1, max_length=5)
    asset_sentiment: list[AssetSentiment] = Field(default_factory=list, max_length=8)
    entities: list[Entity] = Field(default_factory=list, max_length=20)
    window_hours: int = Field(default=4, ge=1, le=24)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("notes", mode="before")
    @classmethod
    def _clamp_notes(cls, v: object) -> object:
        """Self-heal an over-long free-text ``notes`` instead of crashing the
        whole agent run (same class as the witnessed ``cb_nlp`` 2026-06-09
        failure, twin of ``_drop_invalid_assets`` below). See
        :mod:`ichor_agents.agents._free_text`."""
        return truncate_free_text(v, 1000)

    @field_validator("asset_sentiment", mode="before")
    @classmethod
    def _drop_invalid_assets(cls, v: object) -> object:
        """Resilience — witnessed prod failure 2026-06-05 on
        ``ichor-couche2@news_nlp.service`` : the runner SUCCEEDED (valid JSON,
        3194 chars) but the LLM hallucinated an invalid asset code
        (``asset_sentiment.2.asset='USD_USD'``), so the ``asset`` Literal
        narrowed to a whole-output ``ValidationError`` →
        ``ClaudeRunnerOutputError`` → ``AllProvidersFailed`` → the ENTIRE
        Couche-2 agent run FAILED. One hallucinated row must not kill the whole
        agent. Drop dict entries whose ``asset`` is not in the canonical 8
        (mirrors the ``_normalize_mixed_tone`` precedent — structural defense
        beats prompt engineering). Non-dict / valid entries pass through so the
        per-item ``AssetSentiment`` validation still runs.
        """
        if not isinstance(v, list):
            return v
        return [
            item
            for item in v
            if not (isinstance(item, dict) and item.get("asset") not in _VALID_NEWS_ASSETS)
        ]


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

VOCABULARY DISCIPLINE (r172b — schema-confusion drift fix) :
  - `narratives[*].sentiment` MUST be one of {"bullish", "bearish", "mixed"}
    — this is the FX-trader DIRECTIONAL vocabulary. Use "bullish" when the
    narrative implies upward price pressure on the dominant affected
    asset(s) ; "bearish" for downward ; "mixed" when the narrative cuts
    both ways (e.g., hot CPI = bullish USD + bearish risk assets) OR when
    direction cannot be inferred safely.
  - `asset_sentiment[*].tone` MUST be one of {"positive", "neutral",
    "negative"} — this is the NEWS-TONE vocabulary (article corpus
    qualitative read on the asset). Use "positive" when news flow is
    constructive ; "negative" when adversarial ; "neutral" when balanced.
  - DO NOT cross-contaminate the two vocabularies. "positive" is INVALID
    on `narratives[*].sentiment`. "bullish" is INVALID on
    `asset_sentiment[*].tone`. Pydantic validators normalise drift but
    cost an information round-trip.
"""


def make_news_nlp_chain() -> FallbackChain:
    return FallbackChain(
        providers=(CEREBRAS, GROQ),
        system_prompt=SYSTEM_PROMPT_NEWS_NLP,
        output_type=NewsNlpAgentOutput,
        # Haiku low to stay under the Free-tier CF Tunnel 100 s cap
        # (cf macro.py for the rationale).
        claude=ClaudeRunnerConfig.from_env(model="opus", effort="low"),
    )
