"""S04 atomic #4 — per-asset news tone surfaced from the news_nlp payload.

`news_nlp` emits a per-asset `asset_sentiment` array (tone / score / n_articles
/ top_drivers) that `_summarize_payload` previously DROPPED, so a card only ever
showed global narratives. These tests pin the now-surfaced per-asset tone, the
cross-asset fallback, the ADR-017 scrubbing of free-text drivers, and the
asset-threading through `render_couche2_block`.

Mostly pure-function tests (no DB); one render test uses an AsyncMock session.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from ichor_api.services.adr017_filter import is_adr017_clean
from ichor_api.services.couche2_persistence import (
    _news_asset_sentiment_line,
    _summarize_payload,
    render_couche2_block,
)

_NEWS_PAYLOAD = {
    "narratives": [
        {"label": "US-Iran Hormuz risk", "sentiment": "risk-off", "intensity": 0.62},
    ],
    "asset_sentiment": [
        {
            "asset": "USD_JPY",
            "tone": "negative",
            "score": -0.45,
            "n_articles": 3,
            "top_drivers": ["BOJ rate hike to 1% expected", "JPY PPI accelerating"],
        },
        {
            "asset": "EUR_USD",
            "tone": "positive",
            "score": 0.28,
            "n_articles": 3,
            "top_drivers": ["German industrial production rebound", "Quiet EU session"],
        },
        {
            "asset": "XAU_USD",
            "tone": "neutral",
            "score": 0.05,
            "n_articles": 2,
            "top_drivers": ["US-Iran Strait of Hormuz tensions"],
        },
    ],
}


# --------------------------------------------------------------------------- #
# _news_asset_sentiment_line — per-asset filter + fallback                    #
# --------------------------------------------------------------------------- #
def test_asset_line_filters_to_requested_asset() -> None:
    line = _news_asset_sentiment_line(_NEWS_PAYLOAD["asset_sentiment"], "EUR_USD")
    assert "News tone (EUR_USD)" in line
    assert "positive" in line and "+0.28" in line
    assert "German industrial production rebound" in line
    # the other assets' tone must NOT leak into the per-asset line
    assert "USD_JPY" not in line and "XAU_USD" not in line
    assert "not a signal" in line


def test_asset_line_cross_asset_fallback_when_asset_none() -> None:
    line = _news_asset_sentiment_line(_NEWS_PAYLOAD["asset_sentiment"], None)
    assert "cross-asset" in line
    # top rows are labelled with their asset code
    assert "USD_JPY:" in line and "EUR_USD:" in line


def test_asset_line_fallback_when_asset_absent_from_payload() -> None:
    # GBP_USD not in the payload → fall back to cross-asset top rows, no crash
    line = _news_asset_sentiment_line(_NEWS_PAYLOAD["asset_sentiment"], "GBP_USD")
    assert "cross-asset" in line


def test_asset_line_empty_returns_blank() -> None:
    assert _news_asset_sentiment_line([], "EUR_USD") == ""


def test_asset_line_handles_missing_score_and_drivers() -> None:
    rows = [{"asset": "EUR_USD", "tone": "neutral", "n_articles": 0}]
    line = _news_asset_sentiment_line(rows, "EUR_USD")
    assert "n/a" in line  # score missing → n/a
    assert "drivers" not in line  # no drivers → no drivers clause


# --------------------------------------------------------------------------- #
# ADR-017 — free-text drivers must be scrubbed                                #
# --------------------------------------------------------------------------- #
def test_driver_with_trade_word_is_scrubbed_clean() -> None:
    rows = [
        {
            "asset": "XAU_USD",
            "tone": "positive",
            "score": 0.4,
            "n_articles": 5,
            # a real headline could carry 'buy'/'sell-off' verbatim
            "top_drivers": ["Buy-the-dip flows into gold", "equity sell-off accelerates"],
        }
    ]
    line = _news_asset_sentiment_line(rows, "XAU_USD")
    assert is_adr017_clean(line), f"ADR-017 leak: {line}"


def test_full_news_summary_is_adr017_clean() -> None:
    out = _summarize_payload("news_nlp", _NEWS_PAYLOAD, "EUR_USD")
    assert is_adr017_clean(out)


# --------------------------------------------------------------------------- #
# _summarize_payload — news branch threads asset + keeps narratives           #
# --------------------------------------------------------------------------- #
def test_summarize_news_keeps_narratives_and_adds_asset_tone() -> None:
    out = _summarize_payload("news_nlp", _NEWS_PAYLOAD, "EUR_USD")
    assert "Top narratives" in out  # pre-existing behaviour preserved
    assert "News tone (EUR_USD)" in out  # new per-asset line


def test_summarize_news_no_asset_sentiment_still_renders_narratives() -> None:
    payload = {"narratives": _NEWS_PAYLOAD["narratives"], "asset_sentiment": []}
    out = _summarize_payload("news_nlp", payload, "EUR_USD")
    assert "Top narratives" in out
    assert "News tone" not in out  # nothing to surface


def test_summarize_other_kinds_ignore_asset() -> None:
    # asset is news-only; other kinds must behave exactly as before
    out = _summarize_payload(
        "sentiment", {"overall_retail_mood": "greedy", "contrarian_signal": "no_extreme"}, "EUR_USD"
    )
    assert "Retail mood: greedy" in out


# --------------------------------------------------------------------------- #
# render_couche2_block — threads asset into the news summary                   #
# --------------------------------------------------------------------------- #
async def test_render_block_threads_asset_into_news() -> None:
    now = datetime.now(UTC)
    news_row = SimpleNamespace(
        agent_kind="news_nlp", model_used="haiku", ran_at=now, payload=_NEWS_PAYLOAD
    )

    def _result_for(kind: str) -> MagicMock:
        r = MagicMock()
        r.scalar_one_or_none.return_value = news_row if kind == "news_nlp" else None
        return r

    # latest_per_kind queries in this order: cb_nlp, news_nlp, sentiment, positioning
    session = MagicMock()
    session.execute = AsyncMock(
        side_effect=[_result_for(k) for k in ("cb_nlp", "news_nlp", "sentiment", "positioning")]
    )
    md, sources = await render_couche2_block(session, "EUR_USD")
    assert "News tone (EUR_USD)" in md
    assert any(s.startswith("couche2:news_nlp@") for s in sources)
    assert is_adr017_clean(md)
