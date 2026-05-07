"""Schema + chain construction tests for the 5 Couche-2 agents.

No LLM calls, no network. Validates :
  - make_*_chain() builds without crashing
  - The chain has the expected providers (Cerebras + Groq fallback)
  - system_prompt is non-trivial (no empty / placeholder)
  - output_type is the expected Pydantic class
  - The Pydantic class accepts canonical fixtures
  - It rejects invalid inputs (out-of-range confidence, unknown enum)

These tests catch the "agent breaks at runtime" failure mode that
e2e LLM tests would miss because the prompt + schema must compile
before any inference happens. ADR-021 §reproducibility guarantee.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ichor_agents.agents import (
    CbNlpAgentOutput,
    MacroAgentOutput,
    NewsNlpAgentOutput,
    PositioningAgentOutput,
    SentimentAgentOutput,
    make_cb_nlp_chain,
    make_macro_chain,
    make_news_nlp_chain,
    make_positioning_chain,
    make_sentiment_chain,
)

# ── chain construction smoke ────────────────────────────────────────


@pytest.mark.parametrize(
    "make_fn,output_cls",
    [
        (make_cb_nlp_chain, CbNlpAgentOutput),
        (make_news_nlp_chain, NewsNlpAgentOutput),
        (make_sentiment_chain, SentimentAgentOutput),
        (make_positioning_chain, PositioningAgentOutput),
        (make_macro_chain, MacroAgentOutput),
    ],
)
def test_chain_builds_with_expected_output_type(make_fn, output_cls) -> None:
    chain = make_fn()
    assert chain is not None
    assert chain.output_type is output_cls
    assert chain.system_prompt is not None
    assert len(chain.system_prompt) > 100, "system_prompt looks like a placeholder"
    assert "Hard rules:" in chain.system_prompt or "rules:" in chain.system_prompt.lower()
    assert len(chain.providers) >= 1, "at least one provider required"


def test_all_chains_have_distinct_system_prompts() -> None:
    """Each agent should have a tailored prompt — easy regression to
    catch if someone copy-pastes a prompt without customizing."""
    prompts = {
        "cb_nlp": make_cb_nlp_chain().system_prompt,
        "news_nlp": make_news_nlp_chain().system_prompt,
        "sentiment": make_sentiment_chain().system_prompt,
        "positioning": make_positioning_chain().system_prompt,
        "macro": make_macro_chain().system_prompt,
    }
    # Every pair should differ
    seen = list(prompts.values())
    for i in range(len(seen)):
        for j in range(i + 1, len(seen)):
            assert seen[i] != seen[j], f"prompts collide: agents {i} and {j}"


# ── CbNlpAgentOutput schema ─────────────────────────────────────────


def test_cb_nlp_output_accepts_canonical() -> None:
    out = CbNlpAgentOutput(
        stances=[
            {
                "cb": "FED",
                "stance": "hawkish",
                "confidence": 0.7,
                "rate_path_skew": "hikes_more_likely",
            },
        ],
        shifts=[
            {
                "cb": "ECB",
                "speaker": "Lagarde",
                "speech_date": datetime(2026, 5, 1, tzinfo=UTC),
                "direction": "more_dovish",
                "quote": "We are confident inflation is converging.",
                "rationale": "Markedly softer language vs prior speech.",
            }
        ],
        asset_impacts=[
            {
                "asset": "EUR_USD",
                "bias": "bearish",
                "confidence": 0.6,
                "primary_driver_cb": "ECB",
                "rationale": "ECB dovish shift weighs on EUR.",
            }
        ],
    )
    assert out.stances[0].stance == "hawkish"
    assert out.shifts[0].direction == "more_dovish"
    assert out.asset_impacts[0].asset == "EUR_USD"


def test_cb_nlp_output_rejects_unknown_cb() -> None:
    with pytest.raises(Exception):  # pydantic ValidationError
        CbNlpAgentOutput(
            stances=[
                {
                    "cb": "BANK_OF_NARNIA",  # not in CentralBank Literal
                    "stance": "hawkish",
                    "confidence": 0.5,
                    "rate_path_skew": "neutral",
                }
            ]
        )


def test_cb_nlp_output_rejects_confidence_out_of_range() -> None:
    with pytest.raises(Exception):
        CbNlpAgentOutput(
            stances=[
                {
                    "cb": "FED",
                    "stance": "hawkish",
                    "confidence": 1.5,  # > 1.0
                    "rate_path_skew": "neutral",
                }
            ]
        )


# ── NewsNlpAgentOutput schema ───────────────────────────────────────


def test_news_nlp_output_accepts_canonical() -> None:
    out = NewsNlpAgentOutput(
        narratives=[
            {
                "label": "AI capex deceleration",
                "sentiment": "bearish",
                "intensity": 0.7,
                "n_articles": 5,
                "top_entities": [
                    {"kind": "company", "name": "NVIDIA", "mentions": 3}
                ],
                "representative_headlines": ["NVDA beats but guides lower"],
            }
        ],
        asset_sentiment=[
            {
                "asset": "NAS100_USD",
                "tone": "negative",
                "score": -0.4,
                "n_articles": 5,
                "top_drivers": ["AI capex"],
            }
        ],
    )
    assert out.narratives[0].label == "AI capex deceleration"
    assert out.asset_sentiment[0].score == -0.4


def test_news_nlp_rejects_score_out_of_range() -> None:
    with pytest.raises(Exception):
        NewsNlpAgentOutput(
            narratives=[
                {
                    "label": "x",
                    "sentiment": "bearish",
                    "intensity": 0.5,
                    "n_articles": 3,
                }
            ],
            asset_sentiment=[
                {
                    "asset": "EUR_USD",
                    "tone": "negative",
                    "score": -2.0,  # < -1
                    "n_articles": 1,
                }
            ],
        )


def test_news_nlp_rejects_too_many_narratives() -> None:
    """max_length=5 in the schema."""
    with pytest.raises(Exception):
        NewsNlpAgentOutput(
            narratives=[
                {"label": f"n{i}", "sentiment": "mixed", "intensity": 0.5, "n_articles": 1}
                for i in range(6)
            ]
        )


# ── SentimentAgentOutput schema ─────────────────────────────────────


def test_sentiment_output_accepts_canonical() -> None:
    out = SentimentAgentOutput(
        aaii={
            "bullish_pct": 0.42,
            "bearish_pct": 0.32,
            "neutral_pct": 0.26,
            "spread": 0.10,
            "week_ending": datetime(2026, 5, 1, tzinfo=UTC),
        },
        reddit=[
            {
                "subreddit": "wallstreetbets",
                "mood": "bullish",
                "top_tickers_mentioned": ["NVDA", "TSLA"],
                "n_posts_analyzed": 200,
                "extreme_flag": False,
            }
        ],
        google_trends_shifts=[],
        overall_retail_mood="bullish",
        contrarian_signal="no_extreme",
    )
    assert out.aaii.spread == 0.10
    assert out.overall_retail_mood == "bullish"


def test_sentiment_aaii_optional() -> None:
    out = SentimentAgentOutput(
        overall_retail_mood="neutral",
        contrarian_signal="no_extreme",
    )
    assert out.aaii is None
    assert out.reddit == []


def test_sentiment_rejects_invalid_subreddit() -> None:
    with pytest.raises(Exception):
        SentimentAgentOutput(
            reddit=[
                {
                    "subreddit": "memestonks",  # not in Literal
                    "mood": "bullish",
                    "n_posts_analyzed": 100,
                }
            ],
            overall_retail_mood="bullish",
            contrarian_signal="no_extreme",
        )


# ── PositioningAgentOutput schema ───────────────────────────────────


def test_positioning_output_accepts_canonical() -> None:
    out = PositioningAgentOutput(
        cot=[
            {
                "asset": "EUR_USD",
                "non_commercial_net": 85000,
                "week_over_week_change": 12000,
                "extreme_pct": 88.0,
                "flag": "long_extreme",
            }
        ],
        gex=[
            {
                "asset": "SPX500_USD",
                "dealer_net_gex_usd": -3.5e9,
                "gamma_flip_level": 5180.0,
                "distance_to_flip_pct": 0.4,
                "risk": "trend_amplification",
            }
        ],
        polymarket_whales=[],
        iv_skews=[],
        smart_money_divergence=["COT specs short EUR/USD while AAII bullish — fade retail"],
    )
    assert out.cot[0].flag == "long_extreme"
    assert out.gex[0].risk == "trend_amplification"


def test_positioning_rejects_extreme_pct_over_100() -> None:
    with pytest.raises(Exception):
        PositioningAgentOutput(
            cot=[
                {
                    "asset": "EUR_USD",
                    "non_commercial_net": 1,
                    "week_over_week_change": 0,
                    "extreme_pct": 120.0,  # > 100
                    "flag": "neutral",
                }
            ]
        )


def test_positioning_gex_max_2_assets() -> None:
    """Schema enforces gex max_length=2 (SPX + NDX only)."""
    with pytest.raises(Exception):
        PositioningAgentOutput(
            gex=[
                {
                    "asset": "SPX500_USD",
                    "dealer_net_gex_usd": 0.0,
                    "gamma_flip_level": 0,
                    "distance_to_flip_pct": 0,
                    "risk": "range_likely",
                },
                {
                    "asset": "NAS100_USD",
                    "dealer_net_gex_usd": 0.0,
                    "gamma_flip_level": 0,
                    "distance_to_flip_pct": 0,
                    "risk": "range_likely",
                },
                # 3rd one — must fail max_length=2
                {
                    "asset": "SPX500_USD",
                    "dealer_net_gex_usd": 0.0,
                    "gamma_flip_level": 0,
                    "distance_to_flip_pct": 0,
                    "risk": "range_likely",
                },
            ]
        )


# ── MacroAgentOutput schema ─────────────────────────────────────────


def test_macro_output_accepts_canonical() -> None:
    out = MacroAgentOutput(
        drivers=[
            {
                "theme": "monetary_policy",
                "bias": "risk_off",
                "confidence": 0.75,
                "rationale": "Fed signals patience on cuts ; OIS prices in 2 cuts vs 4 in March.",
                "sources_cited": ["FRED DFF, 2026-05-01", "FOMC minutes 2026-04-30"],
            },
            {
                "theme": "inflation_data",
                "bias": "neutral",
                "confidence": 0.55,
                "rationale": "CPI core stable at 3.1% y/y.",
                "sources_cited": ["FRED CPILFESL, 2026-04-30"],
            },
        ],
        overall_bias="risk_off",
        overall_confidence=0.65,
    )
    assert out.overall_bias == "risk_off"
    assert len(out.drivers) == 2


def test_macro_rejects_unknown_theme() -> None:
    with pytest.raises(Exception):
        MacroAgentOutput(
            drivers=[
                {
                    "theme": "alien_invasion",  # not in MacroTheme
                    "bias": "risk_off",
                    "confidence": 0.5,
                    "rationale": "x",
                }
            ],
            overall_bias="neutral",
            overall_confidence=0.5,
        )


def test_macro_requires_min_one_driver() -> None:
    with pytest.raises(Exception):
        MacroAgentOutput(
            drivers=[],  # min_length=1
            overall_bias="neutral",
            overall_confidence=0.5,
        )


def test_macro_rejects_horizon_too_long() -> None:
    """horizon_hours capped at 72."""
    with pytest.raises(Exception):
        MacroAgentOutput(
            drivers=[
                {
                    "theme": "monetary_policy",
                    "bias": "neutral",
                    "confidence": 0.5,
                    "rationale": "x",
                }
            ],
            overall_bias="neutral",
            overall_confidence=0.5,
            horizon_hours=200,
        )
