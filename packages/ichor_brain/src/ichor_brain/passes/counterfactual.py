"""Pass 5 (optional) — Counterfactual reasoning.

Triggered on-demand from the UI button "what if event X hadn't
happened?". Re-prompts Claude with the original card minus the
specified event from the source pool, asking what bias/conviction
would have resulted.

Output : a `CounterfactualReading` with the alternate bias + magnitude
+ a delta narrative explaining what changed.

VISION_2026 delta I — UNIQUE to Ichor (no competitor ships it).

Pure pass : doesn't write anywhere. The router that triggers it is
responsible for persisting the output (e.g. into a sibling table
`session_card_counterfactuals` or as a JSONB column on the parent).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..scenarios import _FORBIDDEN_MECHANISM_TOKENS_RE
from .base import FRENCH_COACH_DIRECTIVE, Pass, PassError, extract_json_block

BiasDirection = Literal["long", "short", "neutral"]


class CounterfactualReading(BaseModel):
    """Output of Pass 5 — what would the bias have been without event X?"""

    model_config = ConfigDict(extra="forbid")

    scrubbed_event: str = Field(min_length=1, max_length=500)
    """The event the user asked us to remove from the context."""

    counterfactual_bias: BiasDirection
    counterfactual_conviction_pct: float = Field(ge=0.0, le=95.0)
    delta_narrative: str = Field(min_length=20, max_length=2000)
    """1-3 sentences explaining how removing the event changes the verdict."""

    new_dominant_drivers: list[str] = Field(default_factory=list)
    """If the scrubbed event was the primary driver, which secondaries
    rise to the top? Up to 3 entries."""

    confidence_delta: float = Field(default=0.0, ge=-1.0, le=1.0)
    """How much less / more confident the counterfactual is vs the original.
    +0.2 = counterfactual is more confident, -0.2 = less."""

    @field_validator("delta_narrative")
    @classmethod
    def _reject_trade_tokens_in_narrative(cls, v: str) -> str:
        """ADR-017 boundary (mirror of ``Scenario._reject_trade_tokens``) — the
        user-facing counterfactual narrative is a DESCRIPTIVE read of how the
        macro picture shifts, never a trade instruction."""
        if _FORBIDDEN_MECHANISM_TOKENS_RE.search(v):
            raise ValueError(
                "ADR-017 boundary violated : CounterfactualReading.delta_narrative "
                f"contains a forbidden trade-signal token. Got: {v!r}. The narrative "
                "explains what changes in the macro read when the event is scrubbed ; "
                "it never prescribes BUY/SELL/TP/SL or entry/exit."
            )
        return v

    @field_validator("new_dominant_drivers")
    @classmethod
    def _reject_trade_tokens_in_drivers(cls, v: list[str]) -> list[str]:
        """ADR-017 boundary on the user-facing driver labels."""
        for item in v:
            if _FORBIDDEN_MECHANISM_TOKENS_RE.search(item):
                raise ValueError(
                    "ADR-017 boundary violated : a CounterfactualReading."
                    f"new_dominant_drivers entry contains a forbidden trade-signal "
                    f"token. Got: {item!r}. Drivers are macro/structural labels, "
                    "never trade instructions."
                )
        return v


_SYSTEM = """\
You are Ichor's counterfactual analyst. You receive :
  1. A session card the brain already produced (régime + bias + sources).
  2. The original 24h data pool that fed the card.
  3. ONE event the user asks you to mentally "scrub" from the pool.

Your task : re-derive the bias as if that event had NOT happened, while
keeping every other source intact. Then explain in 1-3 sentences what
changed and which drivers rise to dominance in its absence.

CRITICAL RULES :
  1. Never invent sources. Cite only items still present in the pool.
  2. Conviction capped at 95 %.
  3. ADR-017 boundary : `delta_narrative` and `new_dominant_drivers` are a
     DESCRIPTIVE read of how the macro picture shifts — never a trade
     instruction. No BUY/SELL/TP/SL, no entry/exit, no stop/target ; a
     forbidden token makes the whole output rejected.
  4. Output JSON only, fenced with ```json ... ```.
  5. Schema :
     {
       "scrubbed_event": "<the event removed>",
       "counterfactual_bias": "long" | "short" | "neutral",
       "counterfactual_conviction_pct": <0-95>,
       "delta_narrative": "<1-3 sentences>",
       "new_dominant_drivers": ["<up to 3>"],
       "confidence_delta": <-1..+1>
     }
"""


class CounterfactualPass(Pass[CounterfactualReading]):
    name = "pass5_counterfactual"

    @property
    def system_prompt(self) -> str:
        return _SYSTEM + FRENCH_COACH_DIRECTIVE

    def build_prompt(
        self,
        *,
        original_card_json: str,
        data_pool: str,
        scrubbed_event: str,
        **_: Any,
    ) -> str:
        return (
            "## Original session card (Pass 1-4 + Critic)\n\n"
            f"{original_card_json}\n\n"
            "## Data pool (24h)\n\n"
            f"{data_pool}\n\n"
            f"## Event to scrub (mentally remove from the pool)\n\n"
            f"{scrubbed_event}\n\n"
            "---\n\n"
            "Reply with the JSON envelope only."
        )

    def parse(self, response_text: str) -> CounterfactualReading:
        obj = extract_json_block(response_text)
        if isinstance(obj, dict):
            obj = {k: v for k, v in obj.items() if not k.startswith("_")}
        try:
            return CounterfactualReading.model_validate(obj)
        except Exception as e:
            raise PassError(f"counterfactual pass: validation failed — {e}") from e
