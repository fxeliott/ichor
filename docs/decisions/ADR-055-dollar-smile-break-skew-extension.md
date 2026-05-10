# ADR-055: DOLLAR_SMILE_BREAK extension — add CBOE SKEW as 5th condition

- **Status**: Accepted
- **Date**: 2026-05-08
- **Supersedes**: extends ADR-043 (Dollar Smile Break original 4-of-4 gate)
- **Wave**: Phase II Layer 1 wave 27

## Context

ADR-043 ratified the DOLLAR_SMILE_BREAK alert with a 4-condition AND
gate against FRED-only macro signals (term premium, DXY, VIX, HY OAS).
The detector fires when "US itself becomes the source of instability" —
the regime that emerged in April 2025 when USD fell WITH stocks during
tariff panic.

Wave 24 (PR #63 / ADR-054) shipped a CBOE SKEW collector that
populates `cboe_skew_observations` daily from Yahoo Finance `^SKEW`.
SKEW measures the OOM (out-of-the-money) tail-risk component of S&P 500
returns that VIX (ATM-only) systematically misses. In a "broken smile"
regime the OOM tail bid is one of the cleanest tells: dealers price in
fat tails on USD-denominated equities even when ATM vol stays calm.

Pre-wave-27 the detector was blind to that signal. The 4 original
conditions can all hold without any tail premium being priced in; the
detector then fires for what is technically a "broken smile lite"
without confirmation in the option surface.

## Decision

Extend the AND gate from 4 to 5 conditions by adding:

```
condition 5: skew_z > +1.0  (CBOE SKEW elevated tail-risk)
```

The composite alert threshold becomes `ALERT_CONDITIONS_FLOOR = 5`.

### Graceful-None semantics during SKEW warm-up

The CBOE SKEW collector launched 2026-05-08 with ~22 days of history.
The z-score requires `_MIN_ZSCORE_HISTORY = 60` days. Until ~mid-July
2026 the SKEW z-score is `None` and the 5th condition would otherwise
fail every run, killing the alert entirely.

To preserve ADR-043 back-compat during this warm-up window, the SKEW
condition uses a new `graceful_none=True` flag in `_evaluate_condition`:
when `z is None`, the condition reports `passes=True`. Once the SKEW
table accumulates ≥60 days of history, the condition becomes a real
strict test.

Operationally:

| SKEW history       | 5th condition behaviour | Effective gate     |
| ------------------ | ----------------------- | ------------------ |
| <60 days (warm-up) | passes regardless       | 4-of-4 (= ADR-043) |
| ≥60 days, z ≤ +1.0 | fails                   | 4-of-5 (no fire)   |
| ≥60 days, z > +1.0 | passes                  | 5-of-5 (fires)     |

Crossover date: ~2026-07-08 (60 trading days after collector launch).

### Telemetry additions

`extra_payload` gains 3 new fields:

- `z_skew: float | None` — the raw SKEW z-score (or `None` during warm-up)
- `skew_warm: bool` — whether SKEW has enough history to evaluate
- `tail_amplified: bool` — `True` when `skew_warm` AND condition 5 passes

`tail_amplified=True` is the strict-er signal a trader should weigh
above the original 4-of-4 firing — it adds OOM option-surface
confirmation to the macro narrative.

`source` becomes `"FRED:THREEFYTP10+DTWEXBGS+VIXCLS+BAMLH0A0HYM2 + CBOE:SKEW"`.

### Catalog change

`AlertDef.default_threshold`: 4 → 5.
`label_template`: `"... ({value:.0f}/4)"` → `"... ({value:.0f}/5)"`.
`description` updated to document the 5-condition gate + warm-up note.

## Consequences

### Positive

- Tail-risk pricing now factored into the broken-smile detector. The
  alert is less ambiguous: a 5-of-5 firing with `tail_amplified=True`
  is materially stronger evidence than the original 4-of-4.
- Back-compat preserved: zero behavioural change during the SKEW
  warm-up window (until ~2026-07-08). Existing tests `test_evaluate_*`
  continue to pass with the SKEW skip-pass acting as a no-op.
- Specificity improves over time: once SKEW is warm, the gate is
  strict-er than ADR-043. Empirical false-positive rate should drop.
- Telemetry richer for downstream consumers (data_pool, Critic, trader
  bias card): `tail_amplified` is a single-bit signal of regime
  confidence.

### Negative

- The graceful-None pattern is **easy to forget**. Future authors
  adding new conditions must explicitly opt in to `graceful_none=True`
  if they want similar warm-up tolerance. Default remains
  `graceful_none=False` (None = fail).
- After 2026-07-08, the alert may be too strict if SKEW is structurally
  noisy (e.g. memorial day effects, low-volume holiday periods). May
  need a v3 ADR to relax the SKEW threshold from `+1.0` to `+0.5` if
  empirical FP rate drops below ~0.3% (vs the targeted 1-2%).

### Neutral

- `metric_name` unchanged: `dollar_smile_conditions_met`. Downstream
  consumers query the same metric but value range becomes 0..5 (was 0..4).
  Anyone writing percentile thresholds against this metric must
  recalibrate.

## Implementation

- `apps/api/src/ichor_api/services/dollar_smile_check.py` (~30 lines diff)
- `apps/api/src/ichor_api/alerts/catalog.py` (catalog AlertDef updated)
- `apps/api/tests/test_dollar_smile_check.py` (5 new tests; 19/19 pass)
- No migration required (no schema change, just metric value range).

## Verification

- `pytest test_dollar_smile_check.py`: 19 passed (was 14, +5 wave 27).
- Live run on Hetzner post-deploy: alert firing depends on actual
  market conditions; the test path verifies all 4 graceful + warm
  scenarios.

## Linked

- **ADR-043** Dollar Smile Break original 4-of-4 gate (this ADR
  supersedes the gate, preserves the underlying detection logic).
- **ADR-054** claude-runner stdin pipe (wave 23 prerequisite for
  reliable production batches).
- **PR #63** CBOE SKEW collector (Wave 24 prerequisite — provides the
  data source for the new condition).
- **PR #65** data_pool wiring (Wave 26 — surfaces SKEW + TFF to the
  4-pass orchestrator).
- **ADR-009** Voie D (Yahoo Finance public chart endpoint preserves
  the no-paid-API constraint).
