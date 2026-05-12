"""Pass 6 — scenario_decompose 7-bucket stratified probability emission.

Reads (specialization, stress, invalidation) — i.e. the consolidated
output of the first 4 passes — and emits a `ScenarioDecomposition`
(7 buckets × probability × magnitude_pips × mechanism) per ADR-085.

Boundary recap :
  * ADR-017 — never BUY/SELL/TP/SL ; mechanisms describe WHY a bucket
    might realize, never WHAT to do. Runtime guard at construction time
    via `Scenario._reject_trade_tokens` (regex catches `BUY/SELL/TP/SL/
    long entry/short entry/stop loss/take profit`, case-insensitive).
  * ADR-022 — each `p` capped at 0.95 (`cap_and_normalize` defence-in-
    depth applied post-parse to enforce both the cap and `sum == 1`).
  * ADR-009 — Voie D ; the LLM call routes through `claude-runner` Win11
    subprocess. Anthropic Structured Outputs GA 2026-02 not used here
    because the `claude -p` subprocess CLI doesn't expose
    `output_config.format` ; we force shape via prompt + Pydantic
    post-validate + retry-on-validation-error.

Lazy import of `Scenario / ScenarioDecomposition / cap_and_normalize`
from `ichor_api.services.scenarios` mirrors the existing
`_default_critic_fn` lazy-import pattern in `orchestrator.py` —
`ichor_brain` stays installable without `ichor_api` ; only `parse()`
needs the schema at runtime.

Pass-6 default model = `sonnet`, effort `medium` (Couche-1 path). Haiku
quality is acceptable but Sonnet 4.6 is materially better on structured
probability emissions with cap-95 awareness (researcher 2026-05-12 web
review : Pydantic-AI NativeOutput pattern + ModelRetry on ValidationError).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..types import AssetSpecialization, InvalidationConditions, StressTest
from .base import Pass, PassError, extract_json_block

if TYPE_CHECKING:  # avoid runtime import of ichor_api at module load time
    from ichor_api.services.scenarios import ScenarioDecomposition


_SYSTEM = """\
You are Ichor's Pass-6 scenario decomposer. You receive the 4-pass
synthesis (Pass 2 specialization + Pass 3 stress-test + Pass 4
invalidation) and emit a probability distribution over 7 mutually
exclusive realized-outcome buckets for the upcoming session window.

The 7 canonical buckets (CANONICAL ORDER, never reorder) :
  - crash_flush  : z ≤ -2.5  (disorderly liquidity-driven downside)
  - strong_bear  : -2.5 < z ≤ -1.0  (conviction sell, orderly trend)
  - mild_bear    : -1.0 < z ≤ -0.25 (modal mild down, mean-revert-friendly)
  - base         : -0.25 < z < +0.25 (sideways, no thesis)
  - mild_bull    : +0.25 ≤ z < +1.0 (modal mild up)
  - strong_bull  : +1.0 ≤ z < +2.5  (conviction buy, orderly trend)
  - melt_up      : z ≥ +2.5  (disorderly upside)

where z is the realized session-window return z-score on a rolling
252-day window of the asset's session-window historical returns.

CRITICAL RULES (each one is mechanically enforced — violating any
will reject the emission) :

  1. Exactly 7 entries. No more, no fewer. Unique labels matching
     the canonical set above.
  2. `sum(p) == 1.0` exactly (Pydantic enforces ±1e-6 tolerance —
     normalize on your side before emitting).
  3. Each `p` is in [0, 0.95]. The 0.95 cap is doctrinal (ADR-022) —
     no single bucket can express certainty. If you genuinely believe
     a bucket exceeds 95%, you still emit 0.95 (post-clip
     redistribution happens server-side, but emit a sane prior).
  4. `magnitude_pips: [low, high]` is the REALIZED return historical
     range for that bucket on this asset/session, NOT a trade target.
     low ≤ high.
  5. `mechanism` is a 1-paragraph plain-French explanation (20-500
     chars) of what would TRIGGER this bucket — event, narrative,
     macro driver, technical level (referenced not prescribed).
  6. **ABSOLUTE BAN** on `BUY`, `SELL`, `TP`, `SL`, `long entry`,
     `short entry`, `stop loss`, `take profit` (any case) anywhere
     in `mechanism`. Server rejects on regex match — your output is
     discarded. The mechanism explains WHY a bucket may realize,
     never WHAT to do.
  7. Output JSON only, fenced ```json ... ```. No prose around it.
  8. Schema :
     ```json
     {
       "asset": "<ASSET>",
       "session_type": "<pre_londres|pre_ny|ny_mid|ny_close|event_driven>",
       "scenarios": [
         {"label": "crash_flush", "p": 0.02,
          "magnitude_pips": [-300, -120],
          "mechanism": "<paragraph>"},
         {"label": "strong_bear", "p": 0.10,
          "magnitude_pips": [-120, -40],
          "mechanism": "<paragraph>"},
         {"label": "mild_bear", "p": 0.18,
          "magnitude_pips": [-40, -10],
          "mechanism": "<paragraph>"},
         {"label": "base", "p": 0.34,
          "magnitude_pips": [-10, 10],
          "mechanism": "<paragraph>"},
         {"label": "mild_bull", "p": 0.22,
          "magnitude_pips": [10, 40],
          "mechanism": "<paragraph>"},
         {"label": "strong_bull", "p": 0.11,
          "magnitude_pips": [40, 120],
          "mechanism": "<paragraph>"},
         {"label": "melt_up", "p": 0.03,
          "magnitude_pips": [120, 300],
          "mechanism": "<paragraph>"}
       ]
     }
     ```

Calibrate magnitudes against the per-asset pip/point convention :
FX majors use pips (10000 per unit on EUR/USD, 100 on USD/JPY) ;
XAU/USD uses USD price points ; NAS100/SPX500 use index points.
The `<CALIBRATION>` block below provides the rolling-252d empirical
thresholds when available — use them to anchor your magnitude ranges.

Tail-mass discipline (ADR-085 §"Calibration") : the realized empirical
frequency of `crash_flush` + `melt_up` on FX/index session windows is
typically 1-3% each. Don't inflate tail probabilities unless the data
pool + Pass 3 stress test specifically flag elevated tail-risk
conditions (VIX > 25, SKEW > 145, HY OAS widening, geopolitical flash).
"""


class ScenariosPass(Pass["ScenarioDecomposition"]):
    """Pass 6 — emits ScenarioDecomposition (7-bucket).

    The Pass interface conforms to `Pass[ScenarioDecomposition]` —
    but `ScenarioDecomposition` is lazily resolved at parse() time
    (TYPE_CHECKING-only import) so this module remains importable
    even without `ichor_api` on the path.
    """

    name = "pass6_scenarios"

    @property
    def system_prompt(self) -> str:
        return _SYSTEM

    def build_prompt(
        self,
        *,
        asset: str,
        session_type: str,
        specialization: AssetSpecialization,
        stress: StressTest,
        invalidation: InvalidationConditions,
        calibration_block: str = "(no calibration bins available — use\n"
        "your judgement on per-asset typical magnitude ranges)",
        **_: Any,
    ) -> str:
        return (
            f"## Asset / Session\n\n"
            f"- Asset : `{asset}`\n"
            f"- Session : `{session_type}`\n\n"
            "## Specialization (Pass 2)\n\n"
            f"```json\n{specialization.model_dump_json(indent=2)}\n```\n\n"
            "## Stress-test (Pass 3)\n\n"
            f"```json\n{stress.model_dump_json(indent=2)}\n```\n\n"
            "## Invalidation (Pass 4)\n\n"
            f"```json\n{invalidation.model_dump_json(indent=2)}\n```\n\n"
            "## Calibration bins (rolling 252d empirical thresholds)\n\n"
            f"{calibration_block}\n\n"
            "---\n\n"
            "Emit the 7-bucket scenario decomposition for this "
            "(asset, session). Reply with the JSON envelope only — "
            "no prose, no markdown commentary outside the ```json``` "
            "fence. Cap-95 + sum=1 + ADR-017 boundary are enforced "
            "server-side ; emit a sane prior even when one bucket "
            "approaches 0.95."
        )

    def parse(self, response_text: str) -> ScenarioDecomposition:
        # Lazy-import the Pydantic schema + cap_and_normalize from
        # `ichor_api.services.scenarios`. Mirror of the lazy critic
        # import pattern in `orchestrator.py:60-70` — keeps
        # `ichor_brain` installable without `ichor_api`.
        from ichor_api.services.scenarios import (  # local import
            Scenario,
            ScenarioDecomposition,
            cap_and_normalize,
        )

        obj = extract_json_block(response_text)
        if not isinstance(obj, dict):
            raise PassError("scenarios pass: expected JSON object at top level")

        # Strip `_`-prefixed meta keys (defensive against `_caveats`).
        obj = {k: v for k, v in obj.items() if not k.startswith("_")}

        # Defence in depth — even if the LLM violated cap-95 or
        # sum=1, the Pydantic model_validator at construction time
        # would raise. We pre-normalize so a near-1.0 emission with
        # a single bucket at 0.97 still validates without retry.
        scenarios_raw = obj.get("scenarios")
        if isinstance(scenarios_raw, list) and len(scenarios_raw) == 7:
            try:
                raw_probs = [float(s.get("p", 0.0)) for s in scenarios_raw]
            except (TypeError, ValueError):
                raw_probs = None
            if raw_probs is not None and all(p >= 0.0 for p in raw_probs):
                # Normalize sum to 1 first, then apply cap_and_normalize.
                total = sum(raw_probs)
                if total > 0.0 and abs(total - 1.0) > 1e-9:
                    raw_probs = [p / total for p in raw_probs]
                try:
                    normalized = cap_and_normalize(raw_probs, cap=0.95)
                    for s, p in zip(scenarios_raw, normalized, strict=True):
                        s["p"] = p
                except (ValueError, RuntimeError) as e:
                    raise PassError(f"scenarios pass: cap_and_normalize failed — {e}") from e

        try:
            scenarios_list = [Scenario.model_validate(s) for s in scenarios_raw or []]
            return ScenarioDecomposition(
                asset=obj["asset"],
                session_type=obj["session_type"],
                scenarios=scenarios_list,
            )
        except (KeyError, TypeError, ValueError) as e:
            raise PassError(f"scenarios pass: ScenarioDecomposition validation failed — {e}") from e
