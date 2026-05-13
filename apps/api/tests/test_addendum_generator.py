"""Phase D W116c — addendum_generator unit tests.

Pure-logic slices covered :

1. ADR-017 filter rejects forbidden tokens at output stage (defense-
   in-depth beyond the prompt's NO TRADE SIGNALS instruction).
2. `_build_user_prompt` includes the canonical fields (asset, regime,
   skill_delta, n, drift line).
3. `generate_addendum_text` Voie D contract :
   - Returns None on NaN inputs (defensive).
   - Returns None on call_fn exception (best-effort, no API fallback).
   - Returns None when LLM produces ADR-017-violating text.
   - Returns the typed _AddendumOut on happy path.
4. Pydantic envelope enforces length + importance bounds.
"""

from __future__ import annotations

import math
from typing import Any

import pytest
from ichor_api.services.addendum_generator import (
    MAX_ADDENDUM_CHARS,
    MIN_ADDENDUM_CHARS,
    _AddendumOut,
    _build_user_prompt,
    addendum_passes_adr017_filter,
    generate_addendum_text,
)

# ──────────────────────────── ADR-017 filter ──────────────────────────


def test_adr017_filter_passes_clean_addendum() -> None:
    """Probabilistic / directional language is fine."""
    text = (
        "Pocket EUR_USD/usd_complacency anti-skill : steelman should "
        "consider Fed put expectations re-pricing the DXY trend."
    )
    assert addendum_passes_adr017_filter(text)


def test_adr017_filter_rejects_buy_token() -> None:
    assert not addendum_passes_adr017_filter("Consider BUY pressure on EUR.")


def test_adr017_filter_rejects_sell_token() -> None:
    assert not addendum_passes_adr017_filter("Cards trend toward SELL signals.")


def test_adr017_filter_rejects_tp_sl_tokens() -> None:
    assert not addendum_passes_adr017_filter("TP near 1.20 likely.")
    assert not addendum_passes_adr017_filter("SL at 1.15 prudent.")


def test_adr017_filter_rejects_compound_phrases() -> None:
    """The W117 researcher-brief regex catches 'long at' / 'short at' /
    'take_profit' / 'entry price' / 'leverage'."""
    for forbidden in (
        "long at 1.18",
        "short at 1.10",
        "take_profit ladder",
        "stop loss tight",
        "entry price 1.15",
        "high leverage exposure",
    ):
        assert not addendum_passes_adr017_filter(f"Steelman: {forbidden} is the right reframe."), (
            f"Should reject : {forbidden!r}"
        )


def test_adr017_filter_case_insensitive() -> None:
    assert not addendum_passes_adr017_filter("buy now")
    assert not addendum_passes_adr017_filter("Sell pressure")


def test_adr017_filter_does_not_reject_buyer_lowercase_in_word() -> None:
    """`\\b(BUY|SELL)\\b` word-boundary only — the substring 'buyer'
    contains 'buy' but the regex doesn't match because 'r' is a word
    char. Same for 'seller'."""
    # NB : regex is case-insensitive but uses \b. 'buyer' = b-u-y-e-r,
    # so 'buy' inside it IS at a word boundary on the left but not on
    # the right (next char 'e' is a word char). So 'buy' inside 'buyer'
    # does NOT match \bbuy\b. The filter correctly passes.
    assert addendum_passes_adr017_filter("Discretionary buyers stepped in.")
    assert addendum_passes_adr017_filter("Seller flow continues.")


# ──────────────────────────── _build_user_prompt ──────────────────────────


def test_prompt_includes_canonical_fields() -> None:
    p = _build_user_prompt(
        asset="EUR_USD",
        regime="usd_complacency",
        skill_delta=-0.05,
        mean_pbs=2.45,
        mean_baseline_pbs=2.40,
        n_observations=13,
        latest_drift_event_at=None,
    )
    assert "EUR_USD" in p
    assert "usd_complacency" in p
    assert "n = 13" in p
    assert "0.0500" in p or "-0.0500" in p
    assert "anti-skill" in p.lower() or "anti_skill" in p.lower()


def test_prompt_distinguishes_anti_skill_vs_marginal() -> None:
    """Anti-skill (negative delta) gets the strong-anchor instruction.
    Positive marginal delta gets the secondary-counter-angle hint."""
    p_anti = _build_user_prompt(
        asset="GBP_USD",
        regime="usd_complacency",
        skill_delta=-0.10,
        mean_pbs=2.50,
        mean_baseline_pbs=2.40,
        n_observations=20,
        latest_drift_event_at=None,
    )
    p_marginal = _build_user_prompt(
        asset="EUR_USD",
        regime="usd_complacency",
        skill_delta=0.05,
        mean_pbs=2.30,
        mean_baseline_pbs=2.40,
        n_observations=20,
        latest_drift_event_at=None,
    )
    assert "ANTI-SKILL" in p_anti
    assert "Marginal skill" in p_marginal


def test_prompt_renders_drift_line_when_present() -> None:
    p = _build_user_prompt(
        asset="XAU_USD",
        regime="haven_bid",
        skill_delta=-0.02,
        mean_pbs=2.50,
        mean_baseline_pbs=2.45,
        n_observations=8,
        latest_drift_event_at="2026-05-12T03:30:00+02:00",
    )
    assert "Latest W114 ADWIN drift event" in p
    assert "2026-05-12" in p


def test_prompt_no_drift_line_when_absent() -> None:
    p = _build_user_prompt(
        asset="XAU_USD",
        regime="haven_bid",
        skill_delta=-0.02,
        mean_pbs=2.50,
        mean_baseline_pbs=2.45,
        n_observations=8,
        latest_drift_event_at=None,
    )
    assert "W114 silent on this pocket" in p


# ──────────────────────────── generate_addendum_text ──────────────────────────


@pytest.mark.asyncio
async def test_generate_returns_none_on_nan_inputs() -> None:
    """Defensive : if PBS / skill_delta are NaN (bad upstream data),
    skip the LLM call entirely."""
    result = await generate_addendum_text(
        asset="EUR_USD",
        regime="usd_complacency",
        skill_delta=math.nan,
        mean_pbs=2.40,
        mean_baseline_pbs=2.40,
        n_observations=10,
        latest_drift_event_at=None,
        runner_cfg=None,
        call_fn=_make_unused_call_fn(),  # type: ignore[arg-type]
    )
    assert result is None


@pytest.mark.asyncio
async def test_generate_returns_none_on_runner_exception() -> None:
    """Voie D contract : if claude-runner fails (530 storm, network
    blip, etc.), return None — DO NOT fall back to Anthropic API."""

    async def _boom(**_kw: Any) -> Any:
        raise RuntimeError("simulated 530 storm")

    result = await generate_addendum_text(
        asset="EUR_USD",
        regime="usd_complacency",
        skill_delta=-0.05,
        mean_pbs=2.45,
        mean_baseline_pbs=2.40,
        n_observations=13,
        latest_drift_event_at=None,
        runner_cfg=None,
        call_fn=_boom,
    )
    assert result is None


@pytest.mark.asyncio
async def test_generate_returns_none_on_adr017_violation() -> None:
    """LLM may obey the JSON schema but smuggle a forbidden token.
    Defense-in-depth : regex filter rejects."""

    async def _bad_llm(**_kw: Any) -> _AddendumOut:
        return _AddendumOut(
            addendum_text="EUR has BUY pressure from positioning data.",
            importance=0.8,
        )

    result = await generate_addendum_text(
        asset="EUR_USD",
        regime="usd_complacency",
        skill_delta=-0.05,
        mean_pbs=2.45,
        mean_baseline_pbs=2.40,
        n_observations=13,
        latest_drift_event_at=None,
        runner_cfg=None,
        call_fn=_bad_llm,
    )
    assert result is None


@pytest.mark.asyncio
async def test_generate_happy_path_returns_typed_envelope() -> None:
    async def _good_llm(**_kw: Any) -> _AddendumOut:
        return _AddendumOut(
            addendum_text=(
                "EUR/USD anti-skill in usd_complacency : Pass-3 steelman "
                "should probe DXY mean-reversion vs Fed put divergence."
            ),
            importance=0.72,
        )

    result = await generate_addendum_text(
        asset="EUR_USD",
        regime="usd_complacency",
        skill_delta=-0.05,
        mean_pbs=2.45,
        mean_baseline_pbs=2.40,
        n_observations=13,
        latest_drift_event_at=None,
        runner_cfg=None,
        call_fn=_good_llm,
    )
    assert result is not None
    assert "EUR/USD anti-skill" in result.addendum_text
    assert 0.0 <= result.importance <= 1.0


# ──────────────────────────── _AddendumOut Pydantic ──────────────────────────


def test_envelope_rejects_too_short_text() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _AddendumOut(
            addendum_text="x" * (MIN_ADDENDUM_CHARS - 1),
            importance=0.5,
        )


def test_envelope_rejects_too_long_text() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _AddendumOut(
            addendum_text="x" * (MAX_ADDENDUM_CHARS + 1),
            importance=0.5,
        )


def test_envelope_rejects_importance_out_of_range() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _AddendumOut(addendum_text="x" * 20, importance=1.5)
    with pytest.raises(ValidationError):
        _AddendumOut(addendum_text="x" * 20, importance=-0.1)


def test_envelope_caps_match_constants() -> None:
    """ADR-087 W116 `pass3_addenda.content` CHECK is [8, 4096] ; W116c
    soft-caps at [8, 256] for prompt-budget reasons. Pin both."""
    assert MIN_ADDENDUM_CHARS == 8
    assert MAX_ADDENDUM_CHARS == 256


# ──────────────────────────── test helpers ──────────────────────────


def _make_unused_call_fn():
    """Sentinel : crashes if called. Use to assert no LLM call."""

    async def _boom(**_kw: Any) -> Any:
        raise AssertionError("call_fn should NOT be called in this branch")

    return _boom
