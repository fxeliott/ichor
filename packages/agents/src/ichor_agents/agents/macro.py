"""Macro Agent — analyzes FRED, ECB, BoJ data continuously (every 4h).

Produces structured output with directional bias + confidence per major
macro driver. Consumed by the Bias Aggregator (Couche 3 ML).

Routing per ADR-021: Claude Sonnet 4.6 (primary, via runner) →
Cerebras Llama 3.3-70B → Groq Llama 3.3-70B-versatile (last resort).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from ..claude_runner import ClaudeRunnerConfig
from ..fallback import FallbackChain
from ..providers import CEREBRAS, GROQ

MacroTheme = Literal[
    "monetary_policy",
    "growth_data",
    "inflation_data",
    "labor_market",
    "fiscal_policy",
    "geopolitics",
    "credit_conditions",
    "commodity_supply",
]


class MacroDriver(BaseModel):
    theme: MacroTheme
    bias: Literal["risk_on", "risk_off", "neutral"]
    confidence: float = Field(ge=0.0, le=1.0)
    """Calibrated probability the bias is correct over the next 6h horizon."""
    rationale: str = Field(max_length=500)
    sources_cited: list[str] = Field(default_factory=list, max_length=5)


class MacroAgentOutput(BaseModel):
    drivers: list[MacroDriver] = Field(min_length=1, max_length=8)
    overall_bias: Literal["risk_on", "risk_off", "neutral"]
    overall_confidence: float = Field(ge=0.0, le=1.0)
    horizon_hours: int = Field(default=6, ge=1, le=72)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    notes: str | None = Field(default=None, max_length=1000)


SYSTEM_PROMPT_MACRO = """You are the Macro Agent of Ichor. Your job: read the
provided macro data context (FRED prints, ECB minutes, BoJ statements, fiscal
announcements) and produce a structured directional bias.

Hard rules:
  - Output only Pydantic-validated JSON matching the MacroAgentOutput schema.
  - Cite every claim by source name + date (e.g., "FRED CPIAUCSL, 2026-04-15").
  - Confidence MUST be a calibrated probability — use 0.5 when truly uncertain.
  - If the input context is missing data for a theme, omit that driver entirely
    rather than fabricating one.
  - Banned: hyperbole ("explosion", "krach", "incredible"), generic advice
    ("be careful"), forward-looking guarantees ("will rise").
"""


def make_macro_chain() -> FallbackChain:
    return FallbackChain(
        providers=(CEREBRAS, GROQ),
        system_prompt=SYSTEM_PROMPT_MACRO,
        output_type=MacroAgentOutput,
        # ADR-021 originally mapped this to Sonnet, but the Free-tier
        # Cloudflare Tunnel between Hetzner and the Win11 runner caps
        # request duration at ~100 s and Sonnet medium routinely runs
        # 60-120 s on a 5 KB prompt. Haiku 4.5 is well under the budget
        # (~30-40 s) and quality is sufficient for Couche-2 batch
        # analysis. Revisit once the tunnel runs on a paid plan.
        claude=ClaudeRunnerConfig.from_env(model="haiku", effort="low"),
    )
