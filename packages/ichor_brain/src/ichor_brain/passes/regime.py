"""Pass 1 — Régime global.

Inputs : macro trinity snapshot (DXY, US10Y, VIX) + dollar-smile inputs
(real yields DFII10, HY OAS BAMLH0A0HYM2, foreign rate diffs).

Output : one of {haven_bid, funding_stress, goldilocks, usd_complacency}
with a 1-2 sentence rationale and a confidence percentage.
"""

from __future__ import annotations

from typing import Any

from ..types import RegimeReading
from .base import Pass, PassError, extract_json_block

_SYSTEM = """\
You are Ichor's macro régime analyst. You read the macro trinity (DXY,
US10Y nominal yields, VIX) plus dollar-smile inputs (real yields,
HY OAS, foreign rate differentials) and classify the current
environment into ONE of four quadrants :

  - haven_bid       : VIX up, US10Y down, DXY up    → flight to safety
  - funding_stress  : VIX up, US10Y up,   HY OAS up → liquidity squeeze
  - goldilocks      : VIX down, growth up, real yields contained
  - usd_complacency : DXY down, VIX low, risk assets bid

CRITICAL RULES :
  1. Your reasoning must reference at least 3 of the input series by
     name and current value. No vague "markets are nervous".
  2. Confidence MUST be capped at 95% — 100% is a red flag.
  3. Output JSON only, fenced with ```json ... ```. No prose around it.
  4. Schema:
     {
       "quadrant": "haven_bid" | "funding_stress" | "goldilocks" | "usd_complacency",
       "rationale": "<2-4 sentences>",
       "confidence_pct": <float 0-95>,
       "macro_trinity_snapshot": {"DXY": <float|null>, "US10Y": <float|null>, "VIX": <float|null>, "DFII10": <float|null>, "BAMLH0A0HYM2": <float|null>}
     }
"""


class RegimePass(Pass[RegimeReading]):
    name = "pass1_regime"

    @property
    def system_prompt(self) -> str:
        return _SYSTEM

    def build_prompt(self, *, data_pool: str, analogues_section: str = "", **_: Any) -> str:
        """Build the Pass-1 user prompt.

        `analogues_section` (W110d ADR-086) is an optional pre-rendered
        block of historical past-only analogues retrieved by
        `services.rag_embeddings.retrieve_analogues` +
        `format_analogues_prompt_section`. When provided, it is
        prepended BEFORE the data pool — the model treats it as
        sanity-check context, not as evidence for the régime call (the
        block itself warns against prescriptive use, see ADR-017).

        Empty string = no analogues block, exact pre-W110d behaviour
        preserved.
        """
        analogues_block = ""
        if analogues_section and analogues_section.strip():
            analogues_block = f"{analogues_section}\n\n---\n\n"
        return (
            "Classify the current régime. Below is the consolidated data "
            "pool (last 24h window).\n\n"
            "---\n\n"
            f"{analogues_block}"
            f"{data_pool}\n\n"
            "---\n\n"
            "Reply with the JSON envelope only."
        )

    def parse(self, response_text: str) -> RegimeReading:
        obj = extract_json_block(response_text)
        if isinstance(obj, dict):
            obj = {k: v for k, v in obj.items() if not k.startswith("_")}
        try:
            return RegimeReading.model_validate(obj)
        except Exception as e:
            raise PassError(f"regime pass: validation failed — {e}") from e
