"""Pass 6 — scenario_decompose 7-bucket stratified probability emission.

Reads (specialization, stress, invalidation) — i.e. the consolidated
output of the first 4 passes — and emits a `ScenarioDecomposition`
(7 buckets × probability × magnitude_pips × mechanism × invalidations)
per ADR-085 + r161 Strand A extension (ADR-106 §175 Stride 1).

Boundary recap :
  * ADR-017 — never BUY/SELL/TP/SL ; mechanisms describe WHY a bucket
    might realize, never WHAT to do. Runtime guard at construction time
    via `Scenario._reject_trade_tokens` (regex catches `BUY/SELL/TP/SL/
    long entry/short entry/stop loss/take profit`, case-insensitive).
    r163 Strand C extends the same regex to `InvalidationCondition
    .description` via `_reject_trade_tokens_in_description` validator —
    the invalidation explains the macro/structural mechanism that
    contradicts the bucket, never a trade instruction.
  * ADR-022 — each `p` capped at 0.95 (`cap_and_normalize` defence-in-
    depth applied post-parse to enforce both the cap and `sum == 1`).
  * ADR-009 — Voie D ; the LLM call routes through `claude-runner` Win11
    subprocess. Anthropic Structured Outputs GA 2026-02 not used here
    because the `claude -p` subprocess CLI doesn't expose
    `output_config.format` ; we force shape via prompt + Pydantic
    post-validate + retry-on-validation-error.
  * ADR-106 §175 — Stride 1 foundational. The `invalidations` field on
    each `Scenario` is the schema-side foundation that Strand D
    (`scenario_invalidation_monitor.py`) + Strand E (alerts catalog) +
    Strand F (CRON 6×/jour Paris) consume to deliver the autonomous
    24/7 living-system Eliot's r161 directive demands. Strand C ships
    here = the system prompt that instructs the LLM to populate the
    field per bucket.

W105 architecture cleanup 2026-05-12 : `Scenario`, `ScenarioDecomposition`,
`cap_and_normalize`, `InvalidationCondition`, `INVALIDATION_METRIC_NAMES`
live canonically in `ichor_brain.scenarios` (sibling module) — `apps/api`
re-exports for the ORM + tests + CI guards. Pass-6 imports natively, no
lazy indirection needed.

Pass-6 default model = `opus`, effort `xhigh` (Couche-1 path — §11
full-Opus 2026-06-02, effort raised by ADR-110 engine doctrine
2026-06-11). Pass-6 feeds the SessionVerdict scenario decomposition
(the apex read), so it runs on the top model like the 4-pass. Voie D : same
Max 20x subscription, no API spend. Degrades gracefully under contention
(parse-retry then honest stale card).

r163 Strand C delivery (this commit) : the `_SYSTEM` prompt is extended
to instruct the LLM to populate the `invalidations` field per bucket.
Backward-compat preserved : the `Scenario.invalidations` field has a
default `[]` so any pre-r163 LLM emission (or a Sonnet 4.6 that simply
ignores the new instruction) still validates cleanly. Once empirically
proven that the LLM populates the field correctly across ≥3 production
sessions, Strand D-F can wire the monitor + cron and the verdict's
`derived_from_scenarios=true` populated path will flip the
`<SessionVerdictPanel>` from dormant fallback to LIVE state.
"""

from __future__ import annotations

from typing import Any

from ..scenarios import Scenario, ScenarioDecomposition, cap_and_normalize
from ..types import AssetSpecialization, InvalidationConditions, StressTest
from .base import Pass, PassError, extract_json_block

_SYSTEM = """\
You are Ichor's Pass-6 scenario decomposer. You receive the 4-pass
synthesis (Pass 2 specialization + Pass 3 stress-test + Pass 4
invalidation) and emit a probability distribution over 7 mutually
exclusive realized-outcome buckets for the upcoming session window,
EACH BUCKET CARRYING ITS OWN MEASURABLE INVALIDATION CONDITIONS
(r163 Strand C — closes ADR-106 Stride 1 foundational layer).

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
     in `mechanism` OR in `invalidations[*].description`. Server
     rejects on regex match — your output is discarded. Both
     `mechanism` and `invalidations[*].description` explain WHY a
     bucket may realize OR be invalidated, NEVER WHAT to do.
  7. Output JSON only, fenced ```json ... ```. No prose around it.
  8. Schema (with `invalidations` field per bucket, r163 Strand C) :
     ```json
     {
       "asset": "<ASSET>",
       "session_type": "<pre_londres|pre_ny|ny_mid|ny_close|event_driven>",
       "scenarios": [
         {"label": "crash_flush", "p": 0.02,
          "magnitude_pips": [-300, -120],
          "mechanism": "<paragraph>",
          "invalidations": [
            {"metric_name": "VIX", "threshold": 18.0,
             "direction": "below", "severity": "hard",
             "description": "<paragraph>"}
          ]},
         {"label": "strong_bear", "p": 0.10,
          "magnitude_pips": [-120, -40],
          "mechanism": "<paragraph>",
          "invalidations": [
            {"metric_name": "FRED_DGS10", "threshold": 4.50,
             "direction": "below", "severity": "soft",
             "description": "<paragraph>"}
          ]},
         {"label": "mild_bear", "p": 0.18,
          "magnitude_pips": [-40, -10],
          "mechanism": "<paragraph>",
          "invalidations": []},
         {"label": "base", "p": 0.34,
          "magnitude_pips": [-10, 10],
          "mechanism": "<paragraph>",
          "invalidations": [
            {"metric_name": "DXY", "threshold": 108.0,
             "direction": "crosses_above", "severity": "hard",
             "description": "<paragraph>"}
          ]},
         {"label": "mild_bull", "p": 0.22,
          "magnitude_pips": [10, 40],
          "mechanism": "<paragraph>",
          "invalidations": []},
         {"label": "strong_bull", "p": 0.11,
          "magnitude_pips": [40, 120],
          "mechanism": "<paragraph>",
          "invalidations": [
            {"metric_name": "POLY_FED_CUTS_2026", "threshold": 0.40,
             "direction": "below", "severity": "hard",
             "description": "<paragraph>"}
          ]},
         {"label": "melt_up", "p": 0.03,
          "magnitude_pips": [120, 300],
          "mechanism": "<paragraph>",
          "invalidations": []}
       ]
     }
     ```
  9. **Invalidations field (r163 Strand C, ADR-106 Stride 1)** :
     each bucket carries 0..5 `InvalidationCondition` entries. An
     invalidation is a measurable threshold that, IF BREACHED in
     subsequent live data, contradicts the bucket's mechanism and
     either fully invalidates it (`severity: "hard"` → conviction
     auto-redistributes), partially invalidates it (`severity:
     "soft"` → conviction reduced, no redistribution), or merely
     surfaces context shift (`severity: "note"` → user surface only).

     Empty list `[]` is a LEGITIMATE doctrine #11 calibrated-honesty
     output for buckets whose mechanism is too narrative-driven to
     map to a measurable threshold (e.g., `mild_bear` "consolidation
     after London EUR weakness" — no single numeric tripwire). The
     trader Hewi Capital framework reading capacity is 3-5
     invalidations per bucket ; do NOT enumerate every adjacent
     risk. Quality > quantity. Prefer 1-2 high-leverage
     invalidations on the directional buckets (crash_flush,
     strong_bear, strong_bull, melt_up) where the mechanism IS
     measurable, and `[]` on the modal mid-buckets (mild_bear, base,
     mild_bull) where the mechanism is narrative.

     `metric_name` MUST be one of the canonical 33-entry whitelist
     (see INVALIDATION CONDITIONS section below). Server rejects
     any metric_name not in the set — the LLM cannot invent a
     metric Ichor has no collector for.

     `direction` is the comparison operator :
       - `above`         : current value > threshold
       - `below`         : current value < threshold
       - `crosses_above` : previous tick was below AND current tick
                           is above (state transition detection)
       - `crosses_below` : previous tick was above AND current tick
                           is below (state transition detection)

     `severity` tier :
       - `hard` : scenario fully invalidated → conviction → 0,
                  probability auto-redistributed via cap_and_normalize
       - `soft` : scenario partially invalidated → conviction reduced
                  (no auto-redistribution ; consumer decides)
       - `note` : informational only, surface "context changed" to
                  user without modifying probability

     `description` is a plain-French (or plain-English) one-sentence
     explanation of WHY the breach contradicts the bucket. 10-200
     chars. ADR-017 boundary applies (regex-checked).

INVALIDATION CONDITIONS — canonical metric_name whitelist (33 entries,
grouped by collector source). The LLM MUST use one of these verbatim ;
any other metric_name is rejected at construction time :

  Cross-asset FX + DXY (6, polygon_intraday + FRED) :
    DXY, EURUSD, GBPUSD, USDJPY, USDCAD, AUDUSD

  Equity indices (2, polygon_intraday) :
    SPX500, NAS100

  Commodities (3, polygon_intraday + FRED proxies) :
    XAUUSD, BRENT, WTI

  Rates + curve (6, FRED) :
    FRED_DGS10    (10-year Treasury yield)
    FRED_DGS2     (2-year Treasury yield)
    FRED_DGS30    (30-year Treasury yield)
    FRED_DFII10   (10-year TIPS yield, real)
    FRED_T10Y2Y   (10Y minus 2Y spread)
    FRED_T10YIE   (10-year breakeven inflation)

  Vol / risk (4, FRED + CBOE) :
    VIX, VVIX, SKEW, MOVE

  Credit / liquidity (3, FRED) :
    FRED_BAMLH0A0HYM2  (HY OAS spread)
    FRED_NFCI          (NFCI financial conditions)
    FRED_DTWEXBGS      (Trade-weighted dollar index)

  Inflation / growth (3, FRED) :
    FRED_CPIAUCSL, FRED_PCEPI, FRED_PAYEMS

  Geopolitical event keyword (3, news_nlp + GDELT polled) :
    EVENT_HORMUZ_VOLUME_PCT
    EVENT_IRAN_CEASEFIRE_STATUS
    EVENT_TRUMP_TARIFF_STATUS

  Polymarket probability markets (3) :
    POLY_FED_CUTS_2026
    POLY_FED_HIKE_2026
    POLY_RECESSION_2026

THRESHOLD UNIT CONVENTION (use the metric's natural unit) :
  - Yields (FRED_DGS*, FRED_DFII10, FRED_T10Y2Y, FRED_T10YIE) :
    percent points, e.g., 4.50 for 4.50%
  - Vol indices (VIX, VVIX, SKEW, MOVE) : index points, e.g., 25.0
  - FX pairs (DXY, EURUSD, GBPUSD, USDJPY, USDCAD, AUDUSD) :
    DXY index points (e.g., 108.0) OR cross spot (e.g., 1.0850
    for EURUSD)
  - Commodities (XAUUSD, BRENT, WTI) : USD per oz / barrel
  - Equity indices (SPX500, NAS100) : index points (e.g., 5800)
  - Polymarket (POLY_*) : probability in [0, 1] (e.g., 0.45)
  - Inflation/growth (FRED_CPIAUCSL/PCEPI/PAYEMS) : the most-
    recent ALFRED first-vintage observation in its native unit
  - Geopolitical events (EVENT_*) : percent (0..100) for VOLUME_PCT
    style, or coarse status string mapped to 0/1 for STATUS series

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


class ScenariosPass(Pass[ScenarioDecomposition]):
    """Pass 6 — emits ScenarioDecomposition (7-bucket).

    The schema lives in `ichor_brain.scenarios` so this is a proper
    `Pass[ScenarioDecomposition]` generic — no lazy resolution.
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
