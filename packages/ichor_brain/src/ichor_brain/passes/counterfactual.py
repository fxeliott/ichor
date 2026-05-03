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

from pydantic import BaseModel, ConfigDict, Field

from .base import Pass, PassError, extract_json_block


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
  3. Output JSON only, fenced with ```json ... ```.
  4. Schema :
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
        return _SYSTEM

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
        try:
            return CounterfactualReading.model_validate(obj)
        except Exception as e:
            raise PassError(
                f"counterfactual pass: validation failed — {e}"
            ) from e
