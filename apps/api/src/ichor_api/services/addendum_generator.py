"""Phase D W116c — LLM addendum text generation (ADR-087, ADR-009 Voie D).

Routes via the existing Couche-2 `call_agent_task_async` path :
  → POST claude-runner.fxmilyapp.com/v1/agent-task/async
  → CF Tunnel → Win11 standalone uvicorn
  → subprocess `claude -p --model haiku-low` (ADR-023)
  → Max 20x plan, ZERO Anthropic API spend (ADR-009 Voie D).

Inputs (one per anti-skill pocket from W116b PBS post-mortem) :
  - asset, regime
  - skill_delta (negative = LLM forecaster worse than equal-weight)
  - mean_pbs, mean_baseline_pbs, n_observations
  - latest_drift_event_at (W114 ADWIN, optional)

Output : 1-3 sentence textual addendum injected into the next Pass-3
stress prompt for this pocket. ADR-017 boundary preserved at generation
(prompt forbids BUY/SELL/TP/SL/leverage tokens) AND at consumption
(StressPass.build_prompt does NOT trust generated text — it injects
as adversarial context, not as evidence).

Gated by feature flag `w116c_llm_addendum_enabled` (default False until
Sunday W116b cron populates source data + Eliot validates).
"""

from __future__ import annotations

import math
from typing import Any

import structlog
from pydantic import BaseModel, Field

log = structlog.get_logger(__name__)


# Max addendum body length — matches the W116 `pass3_addenda.content`
# CHECK constraint (8..4096 chars). Soft cap at 256 to keep the
# Pass-3 prompt budget tight (3 addenda × 256 chars = 768 chars
# overhead per stress prompt).
MAX_ADDENDUM_CHARS = 256
MIN_ADDENDUM_CHARS = 8


_SYSTEM_PROMPT = """\
You are Ichor's model-risk reviewer. You receive a post-mortem audit
row for ONE (asset, regime) pocket from the W116b PBS evaluator.

Your job : produce ONE short textual ADDENDUM that the next Pass-3
stress assembler will inject as adversarial context, to nudge the
steelman toward counter-claims the live forecaster has been
systematically missing.

CRITICAL CONSTRAINTS (NON-NEGOTIABLE) :
  1. Output JSON only, fenced with ```json ... ```. No prose around.
  2. Schema :
     {
       "addendum_text": "<8..256 chars, French OR English>",
       "importance": <0.0..1.0, your confidence the addendum captures the actual failure mode>
     }
  3. NO TRADE SIGNALS — ADR-017. The addendum MUST NOT contain :
     BUY, SELL, TP, SL, take_profit, stop_loss, leverage, long_at,
     short_at, entry_price. The addendum is a probabilistic /
     descriptive reminder, NEVER an order.
  4. Stay specific to the pocket : mention the asset and regime,
     reference the empirical anti-skill if present (negative
     skill_delta), suggest ONE concrete counter-claim angle.
  5. Be CONCISE. Pass-3 prompts are token-budget-constrained.
"""


class _AddendumOut(BaseModel):
    """Pydantic envelope for the LLM JSON response."""

    addendum_text: str = Field(..., min_length=MIN_ADDENDUM_CHARS, max_length=MAX_ADDENDUM_CHARS)
    importance: float = Field(..., ge=0.0, le=1.0)


# ADR-017 defense-in-depth regex — superset codified by ADR-087 §"LLM
# extension 1 W116c addendum generator". Round-28 (2026-05-13) extended
# the original W117 set to cover the trader-review HIGH finding : the
# pre-round-28 regex missed `LONG NOW`, `SHORT NOW`, numeric `TARGET
# 1.0850`, numeric `ENTRY 1.0850`, and `MARGIN CALL`. All eight test
# cases pinned in `test_addendum_generator.py:test_adr017_filter_*`.
#
# Strictness rationale : we WANT false positives over false negatives.
# An LLM that occasionally has a benign macro mention like "margin
# debt" filtered out is acceptable. An LLM that emits "TARGET 1.0850
# ENTRY 1.0900" and slips past the regex is NOT acceptable (it would
# be persisted to `pass3_addenda` and injected to Pass-3 stress next
# fire). Caller MUST gate `record_new_addendum` on
# `addendum_passes_adr017_filter()` and persist NOTHING when False.
_ADR017_FORBIDDEN_RE = __import__("re").compile(
    r"\b(BUY|SELL|"
    r"LONG\s+NOW|SHORT\s+NOW|LONG\s+AT|SHORT\s+AT|"
    r"ENTER\s+(?:LONG|SHORT)|"
    r"TP\d*|SL\d*|"
    r"take[\s_-]*profit|stop[\s_-]*loss|"
    r"TARGET[\s:]+\d+\.?\d*|ENTRY[\s:]+\d+\.?\d*|entry\s+price|"
    r"leverage|MARGIN\s+CALL"
    r")\b",
    __import__("re").IGNORECASE,
)


def _build_user_prompt(
    *,
    asset: str,
    regime: str,
    skill_delta: float,
    mean_pbs: float,
    mean_baseline_pbs: float,
    n_observations: int,
    latest_drift_event_at: str | None,
) -> str:
    """Pure helper — same inputs always produce same prompt text."""
    drift_line = (
        f"- Latest W114 ADWIN drift event : {latest_drift_event_at}\n"
        if latest_drift_event_at
        else "- No recent drift event (W114 silent on this pocket).\n"
    )
    skill_diagnosis = (
        "ANTI-SKILL : the live forecaster is performing WORSE than the "
        "no-info equal-weight baseline on this pocket. Anchor the "
        "addendum on this empirical fact."
        if skill_delta < 0.0
        else "Marginal skill : the forecaster's edge is small. The "
        "addendum should sharpen a SECONDARY counter-angle that may "
        "be under-weighted in current Pass-2 prompts."
    )
    return (
        f"## Pocket audit row\n\n"
        f"- Asset / regime : `{asset}` / `{regime}`\n"
        f"- Observations : n = {n_observations}\n"
        f"- Mean PBS : {mean_pbs:.4f} (baseline equal-weight : {mean_baseline_pbs:.4f})\n"
        f"- Skill delta : {skill_delta:+.4f} "
        f"({'positive = LLM > baseline' if skill_delta > 0 else 'negative = LLM < baseline'})\n"
        f"{drift_line}\n"
        f"## Diagnosis\n\n{skill_diagnosis}\n\n"
        f"---\n\n"
        f"Generate ONE addendum per the schema. Stay ≤ 256 chars, "
        f"NO trade signals (ADR-017)."
    )


def addendum_passes_adr017_filter(text: str) -> bool:
    """Defensive : `False` if the addendum contains any ADR-017
    forbidden token. Caller MUST gate `record_new_addendum` on this."""
    return _ADR017_FORBIDDEN_RE.search(text) is None


async def generate_addendum_text(
    *,
    asset: str,
    regime: str,
    skill_delta: float,
    mean_pbs: float,
    mean_baseline_pbs: float,
    n_observations: int,
    latest_drift_event_at: str | None,
    runner_cfg: Any,
    call_fn: Any | None = None,
) -> _AddendumOut | None:
    """Call the LLM (via Couche-2 claude-runner path) to generate one
    addendum. Returns None on any failure mode (ADR-009 Voie D — must
    NOT fall back to Anthropic API ; just skip the row).

    `call_fn` is injectable for tests. Defaults to
    `ichor_agents.claude_runner.call_agent_task_async`.
    """
    if not math.isfinite(skill_delta) or not math.isfinite(mean_pbs):
        return None

    if call_fn is None:
        # Lazy import : keep this module importable without
        # `ichor_agents` installed in every venv (tests run with stub).
        from ichor_agents.claude_runner import call_agent_task_async

        call_fn = call_agent_task_async

    user_prompt = _build_user_prompt(
        asset=asset,
        regime=regime,
        skill_delta=skill_delta,
        mean_pbs=mean_pbs,
        mean_baseline_pbs=mean_baseline_pbs,
        n_observations=n_observations,
        latest_drift_event_at=latest_drift_event_at,
    )

    try:
        result = await call_fn(
            cfg=runner_cfg,
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_type=_AddendumOut,
        )
    except Exception as e:  # noqa: BLE001 — best-effort, Voie D
        log.warning(
            "addendum_generator.runner_failed",
            asset=asset,
            regime=regime,
            error=str(e),
        )
        return None

    # Pydantic already enforced length + importance range. Apply the
    # ADR-017 regex as a SECOND layer (defense-in-depth — the LLM
    # could obey the schema but smuggle a forbidden token).
    if not addendum_passes_adr017_filter(result.addendum_text):
        log.warning(
            "addendum_generator.adr017_violation",
            asset=asset,
            regime=regime,
            sample=result.addendum_text[:80],
        )
        return None

    return result
