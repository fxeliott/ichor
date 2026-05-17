"""Tests for the session_card safety gate (r51 P0.1 + P0.2).

Closes gap identified by r50.5 wave-2 audit : the ADR-017 boundary
regex `is_adr017_clean` was wired only in `addendum_generator.py` +
Pass 6 `_reject_trade_tokens` ; the main session_card persist path
had ZERO content-level safety check on Pass 1-5 outputs, and the
Critic verdict was purely cosmetic.

These tests pin the gate's behavior so future refactors don't
silently re-open the gap.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from ichor_api.services.session_card_safety_gate import (
    evaluate_safety_gate,
)

# ----- Test doubles ---------------------------------------------------


@dataclass(frozen=True)
class _FakeCritic:
    """Minimal Protocol-compatible stand-in for `card.critic`."""

    verdict: str


@dataclass(frozen=True)
class _FakeCard:
    """Minimal Protocol-compatible stand-in for `SessionCard`.

    `model_dump_json` returns a JSON blob that the safety gate will
    scan via `find_violations`.
    """

    payload: dict
    critic: _FakeCritic

    def model_dump_json(self) -> str:  # noqa: D401
        return json.dumps(self.payload)


def _clean_card(verdict: str = "approved") -> _FakeCard:
    """A card with no ADR-017 violations and the given verdict."""
    return _FakeCard(
        payload={
            "asset": "EUR_USD",
            "session_type": "ny_mid",
            "bias_direction": "long",
            "conviction_pct": 62,
            "regime": {"quadrant": "usd_complacency", "confidence_pct": 78},
            "mechanisms": [
                {
                    "claim": "ECB-Fed rate-differential narrowing supports EUR via Engel-West channel.",
                    "source": "FRED:DGS10",
                }
            ],
            "catalysts": ["FOMC speech 19:00 CET"],
            "narrative": "Pre-trade research note. No order generation.",
        },
        critic=_FakeCritic(verdict=verdict),
    )


# ----- Tests : clean cards pass ---------------------------------------


def test_clean_approved_card_is_not_rejected() -> None:
    """Happy path : clean content + Critic approved → no rejection."""
    card = _clean_card(verdict="approved")
    decision = evaluate_safety_gate(card)
    assert decision.rejected is False
    assert decision.primary_reason == "clean"
    assert decision.adr017_violations == ()
    assert decision.critic_blocked is False


def test_clean_amendments_card_is_not_rejected() -> None:
    """Critic 'amendments' verdict is NOT blocked → persist OK."""
    card = _clean_card(verdict="amendments")
    decision = evaluate_safety_gate(card)
    assert decision.rejected is False
    assert decision.primary_reason == "clean"


# ----- Tests : Critic blocked → reject --------------------------------


def test_clean_card_with_critic_blocked_is_rejected() -> None:
    """Critic 'blocked' verdict alone (no ADR-017 token) → REJECT.

    This is the gap that r50.5 wave-2 subagent F identified : Critic
    verdict was previously purely cosmetic, blocked cards persisted
    exactly like approved.
    """
    card = _clean_card(verdict="blocked")
    decision = evaluate_safety_gate(card)
    assert decision.rejected is True
    assert decision.critic_blocked is True
    assert decision.primary_reason == "critic_blocked"
    assert decision.adr017_violations == ()


# ----- Tests : ADR-017 violations → reject ----------------------------


@pytest.mark.parametrize(
    "buy_or_sell_token",
    ["BUY", "SELL", "buy", "sell"],
)
def test_card_with_buy_sell_token_in_mechanism_is_rejected(
    buy_or_sell_token: str,
) -> None:
    """ADR-017 contractual : ANY card containing BUY/SELL must NOT persist.

    Even if Critic approves (rule-based reviewer doesn't check tokens
    per r50.5 wave-2 subagent I finding), the gate catches it.
    """
    card = _FakeCard(
        payload={
            "mechanisms": [
                {
                    "claim": f"Strong setup — {buy_or_sell_token} EUR @ 1.0850",
                    "source": "internal",
                }
            ],
            "critic": "approved",
        },
        critic=_FakeCritic(verdict="approved"),
    )
    decision = evaluate_safety_gate(card)
    assert decision.rejected is True
    assert decision.primary_reason == "adr017_token"
    assert len(decision.adr017_violations) >= 1
    assert decision.critic_blocked is False


@pytest.mark.parametrize(
    "trade_token",
    ["TP1", "SL2", "STOP-LOSS", "TAKE-PROFIT"],
)
def test_card_with_TP_SL_token_is_rejected(trade_token: str) -> None:
    """ADR-091 §Invariant 2 hard-zero : TP/SL/STOP-LOSS/TAKE-PROFIT
    are absolute-banned tokens (per addendum_generator regex superset
    + Pass 6 _reject_trade_tokens). Must also be caught here."""
    card = _FakeCard(
        payload={
            "narrative": f"Setup includes {trade_token} marker",
        },
        critic=_FakeCritic(verdict="approved"),
    )
    decision = evaluate_safety_gate(card)
    assert decision.rejected is True
    assert decision.primary_reason == "adr017_token"
    assert len(decision.adr017_violations) >= 1


def test_adr017_violation_takes_precedence_over_critic_blocked() -> None:
    """If BOTH signals fire, primary_reason is adr017_token (boundary
    contract has higher severity than per-card LLM verdict)."""
    card = _FakeCard(
        payload={"mechanisms": [{"claim": "BUY EUR USD now"}]},
        critic=_FakeCritic(verdict="blocked"),
    )
    decision = evaluate_safety_gate(card)
    assert decision.rejected is True
    assert decision.primary_reason == "adr017_token"
    assert decision.critic_blocked is True
    assert len(decision.adr017_violations) >= 1


# ----- Tests : log_fields() returns expected shape --------------------


def test_log_fields_shape_for_rejected_card() -> None:
    """`log_fields()` must produce structlog-compatible kwargs without
    explosive payloads (sample is capped at 5 violations)."""
    card = _FakeCard(
        payload={
            "mechanisms": [{"claim": f"BUY EUR @ {1.0850 + i * 0.001}"} for i in range(20)],
        },
        critic=_FakeCritic(verdict="approved"),
    )
    decision = evaluate_safety_gate(card)
    fields = decision.log_fields()

    assert isinstance(fields, dict)
    assert fields["adr017_violation_count"] >= 1
    assert isinstance(fields["adr017_violation_sample"], list)
    assert len(fields["adr017_violation_sample"]) <= 5
    assert fields["critic_verdict"] == "approved"
    assert fields["critic_blocked"] is False
    assert fields["reason"] == "adr017_token"


def test_log_fields_shape_for_clean_card() -> None:
    """Clean card log_fields should still serialize cleanly."""
    card = _clean_card(verdict="approved")
    decision = evaluate_safety_gate(card)
    fields = decision.log_fields()

    assert fields["adr017_violation_count"] == 0
    assert fields["adr017_violation_sample"] == []
    assert fields["critic_verdict"] == "approved"
    assert fields["critic_blocked"] is False
    assert fields["reason"] == "clean"


# ----- Tests : SafetyGateDecision is immutable ------------------------


def test_safety_gate_decision_is_frozen() -> None:
    """SafetyGateDecision is a frozen dataclass — mutation forbidden
    so callers can't accidentally flip `rejected` after the fact."""
    card = _clean_card()
    decision = evaluate_safety_gate(card)
    with pytest.raises((AttributeError, Exception)):
        decision.rejected = True  # type: ignore[misc]
