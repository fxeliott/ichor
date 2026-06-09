"""Resilience — every Couche-2 agent ``notes`` self-heals on overrun (2026-06-09).

Witnessed prod failure on ``ichor-couche2@cb_nlp.service`` (2026-06-09 16:15
CEST): the runner SUCCEEDED (valid JSON, 2023 chars) but the LLM emitted a
``notes`` value > 1000 chars → ``string_too_long`` ValidationError →
``ClaudeRunnerOutputError`` → ``AllProvidersFailed`` (no Cerebras/Groq creds)
→ systemd exit 1, silently killing the central-bank rhetoric dimension every
fire. The ``_clamp_notes`` ``mode="before"`` validator (built on
:func:`truncate_free_text`) clamps the over-long string to the field cap so a
harmless overrun can never again kill the whole run — the same structural
defense as ``news_nlp._drop_invalid_assets`` and ``cb_nlp._normalize_mixed_bias``.
"""

from __future__ import annotations

import pytest
from ichor_agents.agents._free_text import truncate_free_text
from ichor_agents.agents.cb_nlp import CbNlpAgentOutput
from ichor_agents.agents.macro import MacroAgentOutput
from ichor_agents.agents.news_nlp import NewsNlpAgentOutput
from ichor_agents.agents.positioning import PositioningAgentOutput
from ichor_agents.agents.sentiment import SentimentAgentOutput

_OVERRUN = "x" * 5000  # well past both the 1000- and 800-char caps


# --- pure helper ---------------------------------------------------------


def test_truncate_passthrough_when_within_cap() -> None:
    assert truncate_free_text("abc", 5) == "abc"
    assert truncate_free_text("abcde", 5) == "abcde"  # len == cap → untouched


def test_truncate_clamps_overrun_to_cap_with_ellipsis() -> None:
    out = truncate_free_text("abcdef", 5)
    assert isinstance(out, str)
    assert len(out) == 5
    assert out.endswith("…")


def test_truncate_ignores_non_strings() -> None:
    assert truncate_free_text(None, 5) is None
    assert truncate_free_text(123, 5) == 123


# --- per-agent integration (reproduces the exact prod crash) -------------


def _cb_nlp(notes: object) -> CbNlpAgentOutput:
    return CbNlpAgentOutput.model_validate(
        {
            "stances": [
                {"cb": "FED", "stance": "neutral", "confidence": 0.5, "rate_path_skew": "neutral"}
            ],
            "notes": notes,
        }
    )


def test_cb_nlp_overrun_notes_does_not_crash() -> None:
    """The exact witnessed prod failure: a >1000-char note must clamp, not crash."""
    out = _cb_nlp(_OVERRUN)
    assert out.notes is not None
    assert len(out.notes) == 1000
    assert out.notes.endswith("…")


def test_macro_overrun_notes_clamped() -> None:
    out = MacroAgentOutput.model_validate(
        {
            "drivers": [
                {"theme": "monetary_policy", "bias": "neutral", "confidence": 0.5, "rationale": "r"}
            ],
            "overall_bias": "neutral",
            "overall_confidence": 0.5,
            "notes": _OVERRUN,
        }
    )
    assert out.notes is not None and len(out.notes) == 1000


def test_news_nlp_overrun_notes_clamped() -> None:
    out = NewsNlpAgentOutput.model_validate(
        {
            "narratives": [{"label": "x", "sentiment": "mixed", "intensity": 0.5, "n_articles": 3}],
            "notes": _OVERRUN,
        }
    )
    assert out.notes is not None and len(out.notes) == 1000


def test_positioning_overrun_notes_clamped_to_800() -> None:
    out = PositioningAgentOutput.model_validate({"notes": _OVERRUN})
    assert out.notes is not None and len(out.notes) == 800


def test_sentiment_overrun_notes_clamped_to_800() -> None:
    out = SentimentAgentOutput.model_validate(
        {"overall_retail_mood": "neutral", "contrarian_signal": "no_extreme", "notes": _OVERRUN}
    )
    assert out.notes is not None and len(out.notes) == 800


# --- non-violating outputs stay byte-identical ---------------------------


def test_short_notes_untouched() -> None:
    out = _cb_nlp("blackout window in effect")
    assert out.notes == "blackout window in effect"


def test_none_notes_stays_none() -> None:
    assert _cb_nlp(None).notes is None


@pytest.mark.parametrize(
    "model_factory",
    [
        lambda: PositioningAgentOutput.model_validate({}),
        lambda: SentimentAgentOutput.model_validate(
            {"overall_retail_mood": "neutral", "contrarian_signal": "no_extreme"}
        ),
    ],
)
def test_omitted_notes_defaults_none(model_factory: object) -> None:
    assert model_factory().notes is None  # type: ignore[operator]
