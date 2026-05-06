"""CB-NLP Agent — central bank rhetoric analysis (every 4h).

Reads recent CB speeches/communiqués from Fed, ECB, BoE, BoJ, SNB, PBoC
and produces hawkish/dovish scores per CB + key shifts identified +
projected impact per rate-sensitive asset.

Routing per ADR-023 (which supersedes ADR-021's mapping table) :
Claude Haiku 4.5 effort=low (primary) → Cerebras Llama 3.3-70B →
Groq Llama 3.3-70B-versatile (last-resort). ADR-021 originally
prescribed Sonnet medium but the Free-tier Cloudflare Tunnel caps
requests at ~100 s and Sonnet medium routinely exceeds that on a
~5 KB CB-speeches context. Haiku 4.5 stays well under the budget
(~30 s) and quality is sufficient for structured rhetoric scoring.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from ..claude_runner import ClaudeRunnerConfig
from ..fallback import FallbackChain
from ..providers import CEREBRAS, GROQ

CentralBank = Literal["FED", "ECB", "BOE", "BOJ", "SNB", "PBOC", "RBA", "BOC"]
Stance = Literal["hawkish", "neutral", "dovish"]


class CbShift(BaseModel):
    """One identified rhetoric shift in a recent speech / minutes."""

    cb: CentralBank
    speaker: str
    speech_date: datetime
    direction: Literal["more_hawkish", "more_dovish", "no_change"]
    quote: str = Field(max_length=500)
    rationale: str = Field(max_length=600)


class CbStance(BaseModel):
    cb: CentralBank
    stance: Stance
    confidence: float = Field(ge=0.0, le=1.0)
    last_speech_at: datetime | None = None
    rate_path_skew: Literal["cuts_more_likely", "neutral", "hikes_more_likely"]
    """Market-implied path skew vs the CB's current rhetoric."""


class CbAssetImpact(BaseModel):
    """Projected directional impact per Ichor asset."""

    asset: Literal[
        "EUR_USD",
        "GBP_USD",
        "USD_JPY",
        "AUD_USD",
        "USD_CAD",
        "XAU_USD",
        "NAS100_USD",
        "SPX500_USD",
    ]
    bias: Literal["bullish", "bearish", "neutral"]
    confidence: float = Field(ge=0.0, le=1.0)
    primary_driver_cb: CentralBank
    rationale: str = Field(max_length=400)


class CbNlpAgentOutput(BaseModel):
    stances: list[CbStance] = Field(min_length=1, max_length=8)
    shifts: list[CbShift] = Field(default_factory=list, max_length=10)
    asset_impacts: list[CbAssetImpact] = Field(default_factory=list, max_length=8)
    horizon_hours: int = Field(default=24, ge=1, le=168)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    notes: str | None = Field(default=None, max_length=1000)


SYSTEM_PROMPT_CB_NLP = """You are the Central-Bank NLP Agent of Ichor. Your
job: read recent CB speeches/communiqués (FOMC, ECB, BoE, BoJ, SNB, PBoC, RBA,
BoC) and produce a structured stance map + identified rhetoric shifts +
asset impact projections.

Hard rules:
  - Output only Pydantic-validated JSON matching CbNlpAgentOutput.
  - Quote rationale MUST be a verbatim ≤ 500 char excerpt from the speech.
  - Only include CBs with a speech/communiqué in the last 7 days.
  - `confidence` is a calibrated probability — use 0.5 when truly uncertain.
  - rate_path_skew compares the CB's current rhetoric to OIS-implied path
    over the next 6 months (use the FRED OIS data context provided).
  - Banned: hyperbole, generic advice, signal generation ("buy", "sell").
"""


def make_cb_nlp_chain() -> FallbackChain:
    return FallbackChain(
        providers=(CEREBRAS, GROQ),
        system_prompt=SYSTEM_PROMPT_CB_NLP,
        output_type=CbNlpAgentOutput,
        # Haiku low instead of ADR-021 Sonnet medium: Free-tier CF
        # Tunnel times out at ~100 s and Sonnet medium often exceeds
        # that on the 5 KB CB-speeches context. Haiku 4.5 stays under
        # the budget and produces well-structured rhetoric scoring.
        claude=ClaudeRunnerConfig.from_env(model="haiku", effort="low"),
    )
