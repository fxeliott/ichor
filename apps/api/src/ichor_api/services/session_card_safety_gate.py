"""ADR-017 + Critic verdict safety gate for session_card persist path.

Closes the gap identified by r50.5 wave-2 audit (subagents F + I) :
the boundary regex `is_adr017_clean` was wired only in
`services/addendum_generator.py:142` (W116c) and Pass 6
`scenarios._reject_trade_tokens` ; the main session_card path
`run_session_card._run -> persistence.to_audit_row` had ZERO
content-level safety check. Pass 1-5 outputs + Critic verdict
landed in `session_card_audit.claude_raw_response` JSONB +
`/v1/today` JSON without any regex enforcement.

This module provides the canonical fail-closed gate :

- ADR-017 violations (BUY/SELL/TP/SL/long entry/...) → REJECT (skip persist)
- Critic verdict == 'blocked' → REJECT (skip persist)

Both signals MUST be checked. ADR-017 is a hard contract (immutable
boundary, R/O across rounds), Critic verdict is per-card LLM-derived.

Usage :
    from ichor_api.services.session_card_safety_gate import (
        evaluate_safety_gate, SafetyGateDecision,
    )
    decision = evaluate_safety_gate(card)
    if decision.rejected:
        log.warning("session_card.safety_reject", **decision.log_fields())
        return 4
    # ...persist
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .adr017_filter import find_violations as _find_adr017_violations


class _CriticLike(Protocol):
    """Structural type for `card.critic` — verdict attribute only."""

    verdict: str


class _CardLike(Protocol):
    """Structural type for SessionCard — model_dump_json + critic only."""

    critic: _CriticLike

    def model_dump_json(self) -> str: ...


@dataclass(frozen=True)
class SafetyGateDecision:
    """Verdict of the session_card safety gate.

    Attributes :
        rejected : True if the card MUST NOT persist (any reason).
        adr017_violations : list of forbidden tokens found, empty if clean.
        critic_verdict : the Critic's verdict ('approved' / 'blocked' /
            'amendments' / etc.) — string-typed to avoid coupling to
            ichor_brain.types.CriticVerdict enum (which would force a
            cross-package import here).
        critic_blocked : True if Critic returned 'blocked'.
        primary_reason : 'adr017_token' | 'critic_blocked' | 'clean'.
            ADR-017 takes precedence over critic_blocked when both fire
            (boundary contract is the higher-severity signal).
    """

    rejected: bool
    adr017_violations: tuple[str, ...]
    critic_verdict: str
    critic_blocked: bool
    primary_reason: str

    def log_fields(self) -> dict[str, Any]:
        """Structured fields suitable for `log.warning(**fields)`."""
        return {
            "adr017_violation_count": len(self.adr017_violations),
            "adr017_violation_sample": list(self.adr017_violations[:5]),
            "critic_verdict": self.critic_verdict,
            "critic_blocked": self.critic_blocked,
            "reason": self.primary_reason,
        }


def evaluate_safety_gate(card: _CardLike) -> SafetyGateDecision:
    """Pure function : evaluate the safety gate on a SessionCard.

    No I/O, no DB, no logging — just returns the decision. Caller
    handles structlog WARNING + early-return + exit-code.
    """
    card_json = card.model_dump_json()
    violations = tuple(_find_adr017_violations(card_json))
    critic_verdict = card.critic.verdict
    critic_blocked = critic_verdict == "blocked"

    if violations:
        primary = "adr017_token"
        rejected = True
    elif critic_blocked:
        primary = "critic_blocked"
        rejected = True
    else:
        primary = "clean"
        rejected = False

    return SafetyGateDecision(
        rejected=rejected,
        adr017_violations=violations,
        critic_verdict=critic_verdict,
        critic_blocked=critic_blocked,
        primary_reason=primary,
    )
