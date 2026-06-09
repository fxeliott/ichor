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
    assert len(out.notes) <= 1000  # load-bearing invariant: never exceeds cap, never crashes
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
    assert out.notes is not None and len(out.notes) <= 1000


def test_news_nlp_overrun_notes_clamped() -> None:
    out = NewsNlpAgentOutput.model_validate(
        {
            "narratives": [{"label": "x", "sentiment": "mixed", "intensity": 0.5, "n_articles": 3}],
            "notes": _OVERRUN,
        }
    )
    assert out.notes is not None and len(out.notes) <= 1000


def test_positioning_overrun_notes_clamped_to_800() -> None:
    out = PositioningAgentOutput.model_validate({"notes": _OVERRUN})
    assert out.notes is not None and len(out.notes) <= 800


def test_sentiment_overrun_notes_clamped_to_800() -> None:
    out = SentimentAgentOutput.model_validate(
        {"overall_retail_mood": "neutral", "contrarian_signal": "no_extreme", "notes": _OVERRUN}
    )
    assert out.notes is not None and len(out.notes) <= 800


# --- nested free-text fields also self-heal (verifier CHALLENGE 3) --------


def test_cb_shift_overrun_fields_clamped() -> None:
    """CbShift.quote(500)/rationale(600) are NOT prompt-bounded — same crash class."""
    out = CbNlpAgentOutput.model_validate(
        {
            "stances": [
                {"cb": "FED", "stance": "neutral", "confidence": 0.5, "rate_path_skew": "neutral"}
            ],
            "shifts": [
                {
                    "cb": "ECB",
                    "speaker": "Lagarde",
                    "speech_date": "2026-06-09T12:00:00Z",
                    "direction": "no_change",
                    "quote": _OVERRUN,
                    "rationale": _OVERRUN,
                }
            ],
        }
    )
    assert len(out.shifts[0].quote) <= 500
    assert len(out.shifts[0].rationale) <= 600


def test_cb_asset_impact_overrun_rationale_clamped() -> None:
    out = CbNlpAgentOutput.model_validate(
        {
            "stances": [
                {"cb": "FED", "stance": "neutral", "confidence": 0.5, "rate_path_skew": "neutral"}
            ],
            "asset_impacts": [
                {
                    "asset": "EUR_USD",
                    "bias": "neutral",
                    "confidence": 0.5,
                    "primary_driver_cb": "ECB",
                    "rationale": _OVERRUN,
                }
            ],
        }
    )
    assert len(out.asset_impacts[0].rationale) <= 400


def test_macro_driver_overrun_rationale_clamped() -> None:
    out = MacroAgentOutput.model_validate(
        {
            "drivers": [
                {
                    "theme": "monetary_policy",
                    "bias": "neutral",
                    "confidence": 0.5,
                    "rationale": _OVERRUN,
                }
            ],
            "overall_bias": "neutral",
            "overall_confidence": 0.5,
        }
    )
    assert len(out.drivers[0].rationale) <= 500


def test_narrative_overrun_label_clamped() -> None:
    out = NewsNlpAgentOutput.model_validate(
        {
            "narratives": [
                {"label": _OVERRUN, "sentiment": "mixed", "intensity": 0.5, "n_articles": 3}
            ]
        }
    )
    assert len(out.narratives[0].label) <= 120


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


# --- hardcore adversarial scenarios (Eliot: "test scénarios hardcore") ----


@pytest.mark.parametrize(
    "value,max_len",
    [
        pytest.param("", 100, id="empty"),
        pytest.param("   ", 100, id="ws-only-within-cap"),
        pytest.param("a" * 100, 100, id="exactly-cap"),
        pytest.param("a" * 99, 100, id="just-under"),
        pytest.param("a" * 101, 100, id="just-over"),
        pytest.param("é" * 5000, 1000, id="precomposed-multibyte"),
        pytest.param("😀" * 5000, 800, id="astral-emoji"),
        pytest.param("x" * 1_000_000, 1000, id="one-megabyte"),
        pytest.param("\n\t " * 5000, 500, id="control-and-ws"),
        pytest.param("acheter EUR maintenant " * 500, 1000, id="adr017-token-spam"),
    ],
)
def test_truncate_never_exceeds_cap_and_stays_str(value: str, max_len: int) -> None:
    """The single load-bearing invariant under adversarial input: result is a
    str of length <= cap, and the call never raises."""
    out = truncate_free_text(value, max_len)
    assert isinstance(out, str)
    assert len(out) <= max_len


def test_truncate_trailing_whitespace_at_cut_shrinks_below_cap() -> None:
    # cut point lands inside a run of spaces → rstrip yields < cap (still valid)
    out = truncate_free_text("abcd" + " " * 20 + "efgh", 10)
    assert out == "abcd…"
    assert len(out) <= 10


@pytest.mark.parametrize("bad", [None, 123, 1.5, True, [], {}, b"bytes", object()])
def test_truncate_passes_non_str_through_unchanged(bad: object) -> None:
    assert truncate_free_text(bad, 100) is bad


def test_truncate_nonpositive_cap_is_total() -> None:
    assert truncate_free_text("anything", 0) == ""
    assert truncate_free_text("", 0) == ""
    assert truncate_free_text("x", -5) == ""


def test_cb_nlp_emoji_and_token_overrun_notes_does_not_crash() -> None:
    """Realistic adversarial cb_nlp note: emoji + ADR-017 token spam, > 1000 chars."""
    out = _cb_nlp("😀 acheter EUR maintenant " * 500)
    assert out.notes is not None
    assert len(out.notes) <= 1000
