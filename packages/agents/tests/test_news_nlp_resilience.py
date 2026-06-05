"""Resilience — NewsNlpAgentOutput drops hallucinated asset codes (2026-06-05).

Witnessed prod failure on ``ichor-couche2@news_nlp.service``: the runner
SUCCEEDED (valid JSON, 3194 chars) but the LLM emitted
``asset_sentiment[2].asset='USD_USD'`` (not a real pair) → the ``asset``
Literal narrowed to a whole-output ``ValidationError`` →
``ClaudeRunnerOutputError`` → ``AllProvidersFailed`` → the ENTIRE Couche-2 agent
run FAILED. The ``_drop_invalid_assets`` validator drops such rows so one
hallucination cannot kill the whole run (structural defense > prompt eng.).
"""

from __future__ import annotations

from ichor_agents.agents.news_nlp import NewsNlpAgentOutput

_NARR = {"label": "x", "sentiment": "mixed", "intensity": 0.5, "n_articles": 3}


def _row(asset: str) -> dict:
    return {"asset": asset, "tone": "neutral", "score": 0.0, "n_articles": 3, "top_drivers": []}


def test_drops_hallucinated_asset_code_usd_usd() -> None:
    """The exact prod failure: a 'USD_USD' row must be dropped, not crash."""
    out = NewsNlpAgentOutput.model_validate(
        {
            "narratives": [_NARR],
            "asset_sentiment": [_row("EUR_USD"), _row("XAU_USD"), _row("USD_USD")],
        }
    )
    assert [a.asset for a in out.asset_sentiment] == ["EUR_USD", "XAU_USD"]


def test_keeps_all_valid_assets_untouched() -> None:
    out = NewsNlpAgentOutput.model_validate(
        {"narratives": [_NARR], "asset_sentiment": [_row("EUR_USD"), _row("NAS100_USD")]}
    )
    assert [a.asset for a in out.asset_sentiment] == ["EUR_USD", "NAS100_USD"]


def test_all_invalid_assets_yields_empty_not_crash() -> None:
    """An all-hallucinated list must still validate — yields [] (no crash)."""
    out = NewsNlpAgentOutput.model_validate(
        {"narratives": [_NARR], "asset_sentiment": [_row("USD_USD"), _row("FOO_BAR")]}
    )
    assert out.asset_sentiment == []
