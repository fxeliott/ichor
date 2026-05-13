"""Pass 3 — Bull case stress-test (devil's advocate).

Forces honest probability calibration : the model is asked to argue
the OPPOSITE of Pass 2's bias and rate the strongest counter-claims.
The revised conviction may move down (rare to move up).
"""

from __future__ import annotations

from typing import Any

from ..types import AssetSpecialization, StressTest
from .base import Pass, PassError, extract_json_block

_SYSTEM = """\
You are Ichor's adversarial reviewer. You receive an asset-specialization
output (Pass 2) and the same data pool. Your job is to STEELMAN the
opposite bias.

CRITICAL RULES :
  1. Produce 2 to 5 counter-claims, each with a strength_pct in [0, 100].
  2. Cite at least one source per counter-claim (URL or series_id).
  3. Adjust conviction : revised_conviction_pct must equal Pass 2's
     conviction MINUS the strongest counter-claim's strength × 0.5,
     floored at 0, capped at 95. Show the arithmetic in `notes`.
  4. Output JSON only, fenced with ```json ... ```. No prose.
  5. Schema :
     {
       "counter_claims": [{"claim": "<string>", "strength_pct": <0-100>, "sources": ["<url|series_id>"]}],
       "revised_conviction_pct": <0-95>,
       "notes": "<arithmetic + 1-2 sentences>"
     }
"""


class StressPass(Pass[StressTest]):
    name = "pass3_stress"

    @property
    def system_prompt(self) -> str:
        return _SYSTEM

    def build_prompt(
        self,
        *,
        specialization: AssetSpecialization,
        asset_data: str,
        addenda_section: str = "",
        **_: Any,
    ) -> str:
        """Compose the Pass-3 stress prompt.

        `addenda_section` (W116c, ADR-087 Phase D) is an optional pre-
        rendered block of operator addenda — short directional reminders
        derived from the W116b post-mortem PBS evaluator. When non-empty,
        injected BEFORE the steelman instruction so the model takes them
        as adversarial context (NOT prescriptive evidence — they bias the
        counter-claim selection, not the final probability).

        Empty string = pre-W116c byte-identical behaviour. The caller
        (`apps/api`) queries
        `services.pass3_addendum_injector.select_active_addenda` and
        renders to the section text, gated behind the
        `pass3_addenda_injection_enabled` feature flag (default False
        until W116c populates the table with LLM-generated content).
        """
        addenda_block = (
            f"## Operator addenda (Phase D W116b post-mortem)\n\n{addenda_section}\n\n"
            if addenda_section.strip()
            else ""
        )
        return (
            "## Pass 2 specialization (the bias to challenge)\n\n"
            f"```json\n{specialization.model_dump_json(indent=2)}\n```\n\n"
            "## Data pool (same as Pass 2)\n\n"
            f"{asset_data}\n\n"
            f"{addenda_block}"
            "---\n\n"
            "Steelman the OPPOSITE bias. Reply with the JSON envelope only."
        )

    def parse(self, response_text: str) -> StressTest:
        obj = extract_json_block(response_text)
        if isinstance(obj, dict):
            obj = {k: v for k, v in obj.items() if not k.startswith("_")}
        try:
            return StressTest.model_validate(obj)
        except Exception as e:
            raise PassError(f"stress pass: validation failed — {e}") from e
