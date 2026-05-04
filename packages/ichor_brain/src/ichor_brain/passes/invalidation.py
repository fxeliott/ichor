"""Pass 4 — Invalidation conditions.

Per Tetlock superforecaster research, the single most predictive habit
is explicit pre-commitment to "this thesis is wrong if X". This pass
turns the (specialization, stress) pair into a list of invalidation
triggers with thresholds and source URLs.
"""

from __future__ import annotations

from typing import Any

from ..types import AssetSpecialization, InvalidationConditions, StressTest
from .base import Pass, PassError, extract_json_block


_SYSTEM = """\
You are Ichor's invalidation-pre-commitment author. You receive the
specialization (Pass 2) and the stress-test (Pass 3). You output the
list of conditions that, if observed during the session, INVALIDATE
the bias.

CRITICAL RULES :
  1. Provide at least one condition. Three is the typical sweet spot.
  2. Each condition has a numeric or unambiguous textual threshold.
     "DXY breaks above 105.50", "VIX prints > 22", "ECB Lagarde says
     'restrictive for longer'" — never "if things change".
  3. Each condition MUST cite the source (Bloomberg ticker, FRED series
     id, calendar event id, news URL).
  4. Default review window : 8 hours. Override only if the catalyst
     forces a tighter window.
  5. Output JSON only, fenced with ```json ... ```. No prose.
  6. Schema :
     {
       "conditions": [{"condition": "<string>", "threshold": "<string|float>", "source": "<id|url>"}],
       "review_window_hours": <int 1-168>
     }
"""


class InvalidationPass(Pass[InvalidationConditions]):
    name = "pass4_invalidation"

    @property
    def system_prompt(self) -> str:
        return _SYSTEM

    def build_prompt(
        self,
        *,
        specialization: AssetSpecialization,
        stress: StressTest,
        **_: Any,
    ) -> str:
        return (
            "## Specialization (Pass 2)\n\n"
            f"```json\n{specialization.model_dump_json(indent=2)}\n```\n\n"
            "## Stress-test (Pass 3)\n\n"
            f"```json\n{stress.model_dump_json(indent=2)}\n```\n\n"
            "---\n\n"
            "Author the invalidation conditions. Reply with the JSON envelope only."
        )

    def parse(self, response_text: str) -> InvalidationConditions:
        obj = extract_json_block(response_text)
        if isinstance(obj, dict):
            obj = {k: v for k, v in obj.items() if not k.startswith("_")}
        try:
            return InvalidationConditions.model_validate(obj)
        except Exception as e:
            raise PassError(f"invalidation pass: validation failed — {e}") from e
