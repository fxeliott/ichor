# ADR-085: Pass 6 scenario_decompose — 7-bucket stratified probability taxonomy

**Status**: Accepted — pre-implementation contract (code lands in W105)

**Date**: 2026-05-11

**Supersedes**: none

**Extends**: [ADR-017](ADR-017-reset-phase1-living-macro-entity.md) (boundary), [ADR-022](ADR-022-probability-bias-models-reinstated.md) (probability + conviction cap 95%), [ADR-081](ADR-081-doctrinal-invariant-ci-guards.md) (CI-guarded invariants), [ADR-083](ADR-083-ichor-v2-trader-grade-manifesto-and-gap-closure.md) D2 (Pass 6 decision)

## Context

The 4-pass orchestrator (Pass 1 regime → Pass 2 asset → Pass 3 stress → Pass 4 invalidation) emits a **direction + probability + conviction** per (asset, session). The audit 2026-05-11 G12 surfaced that this is too coarse for a "rêve ultime du trader" standard : a single probability lumps together "modal continuation +30 pips" and "tail crash -120 pips" in the same conviction figure.

[`packages/ichor_brain/.../session_scenarios.py:38-50`](../../packages/ichor_brain/src/ichor_brain/session_scenarios.py) today emits **3** SMC-style scenarios (Continuation / Reversal / Sideways) — useful but qualitative. [ICHOR_PLAN.md:209-217](../ICHOR_PLAN.md) promised **7 probability-weighted scenarios** stratified by magnitude. ADR-083 D2 ratified the shift.

## Decision

Add **Pass 6 `scenario_decompose`** to the orchestrator. For each (asset, session, regime) it emits a frozen list of 7 mutually-exclusive outcome buckets, each with a probability ∈ [0, 0.95] summing to 1.0 exactly. The 7 buckets are stratified by realized-magnitude z-score on a rolling 1-year window (per asset, per session).

### The 7 buckets

| Bucket        | Realized return z-score | Conceptual label                                     |
| ------------- | ----------------------- | ---------------------------------------------------- |
| `crash_flush` | z ≤ −2.5                | Disorderly liquidity-driven downside ; fat-left-tail |
| `strong_bear` | −2.5 < z ≤ −1.0         | Conviction sell, orderly trend                       |
| `mild_bear`   | −1.0 < z ≤ −0.25        | Modal mild down ; mean-revert friendly               |
| `base`        | −0.25 < z < +0.25       | Sideways / inside-day / no thesis                    |
| `mild_bull`   | +0.25 ≤ z < +1.0        | Modal mild up                                        |
| `strong_bull` | +1.0 ≤ z < +2.5         | Conviction buy, orderly trend                        |
| `melt_up`     | z ≥ +2.5                | Disorderly upside ; fat-right-tail                   |

**Bucket boundaries are calibrated per (asset, session_type)** from `polygon_intraday` realized returns at the (12h) session horizon, rolling 252 trading-days. They are persisted in `scenario_calibration_bins` (new table, migration 0039) so the same boundaries apply to all consumers.

### Schema (migration 0039, W105 candidate)

```sql
ALTER TABLE session_card_audit
  ADD COLUMN scenarios JSONB NOT NULL DEFAULT '[]'::jsonb;

CREATE TABLE scenario_calibration_bins (
  asset           TEXT NOT NULL,
  session_type    TEXT NOT NULL,
  computed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  bins_z_thresholds JSONB NOT NULL,       -- [-2.5, -1.0, -0.25, 0.25, 1.0, 2.5]
  bins_pip_thresholds JSONB NOT NULL,     -- per-asset translation to pips/points
  sample_n        INTEGER NOT NULL,
  PRIMARY KEY (asset, session_type, computed_at)
);
```

`scenarios` JSONB shape per session card :

```json
[
  { "label": "crash_flush", "p": 0.02, "magnitude_pips": [-300, -120], "mechanism": "..." },
  { "label": "strong_bear", "p": 0.1, "magnitude_pips": [-120, -40], "mechanism": "..." },
  { "label": "mild_bear", "p": 0.18, "magnitude_pips": [-40, -10], "mechanism": "..." },
  { "label": "base", "p": 0.34, "magnitude_pips": [-10, +10], "mechanism": "..." },
  { "label": "mild_bull", "p": 0.22, "magnitude_pips": [+10, +40], "mechanism": "..." },
  { "label": "strong_bull", "p": 0.11, "magnitude_pips": [+40, +120], "mechanism": "..." },
  { "label": "melt_up", "p": 0.03, "magnitude_pips": [+120, +300], "mechanism": "..." }
]
```

### Probability cap + normalization

Each `p_k` is **capped at 0.95** per ADR-022 (cap-95 conviction invariant — no individual bucket can express certainty). When the Pass-6 LLM emits a vector whose max exceeds 0.95, we **proportional-clip** :

```python
def cap_and_normalize(probs: list[float], cap: float = 0.95) -> list[float]:
    """ADR-085 §cap. Clip max to cap, redistribute excess proportionally
    on the remaining buckets. Preserves order, transparent, deterministic."""
    p = list(probs)
    while max(p) > cap:
        i = p.index(max(p))
        excess = p[i] - cap
        p[i] = cap
        rest = sum(p) - cap
        if rest > 0:
            for j in range(len(p)):
                if j != i:
                    p[j] += excess * p[j] / rest
    return p
```

Alternative considered : Dirichlet smoothing (Bayesian prior). Rejected because less transparent and tunes a hyperparameter (α) that the researcher 2026-05-11 confirmed has no canonical institutional convention.

### Brier scoring — multi-class adaptation

Per **Murphy 1973** ("A new vector partition of the probability score", _J. Appl. Meteorol._ 12 : 595–600), the K-class Brier score is :

```
B = (1/N) · Σ_i Σ_k (p_{i,k} − o_{i,k})²
```

where `o_{i,k} ∈ {0, 1}` is the one-hot realized outcome (which bucket the session actually ended in, computed by the realized-outcome reconciler against `polygon_intraday`). Range [0, 2]. Lower is better. Decomposable via Murphy 1973 into Reliability + Resolution + Uncertainty.

The reconciler `apps/api/src/ichor_api/cli/reconcile_outcomes.py` (W108 candidate) maps realized returns to the correct bucket using the same z-score thresholds + per-asset calibration in `scenario_calibration_bins`, then writes the one-hot outcome to a new column `realized_scenario_bucket` on `session_card_audit`.

Skill score relative to uniform baseline (`p_k = 1/7` for all k) :

```
skill = 1 − B_ichor / B_uniform
```

Target : `skill ≥ 0.05` on rolling 90d per (asset, session) within 6 months of W105 ship — i.e. Ichor beats a uniform-prior 7-bucket forecast by 5 % Brier. Anything below means the 7-bucket emission is not adding information vs the prior — a clear "calibrate or retire" signal.

## ADR-017 boundary (re-affirmed)

Pass 6 emits **descriptive probability over realized-outcome buckets**. It does NOT emit :

- Trade direction (long/short/neutral remains in Pass 2's `bias`)
- Entry / exit / TP / SL / position size / leverage
- Buy / sell / order / position recommendations

The `magnitude_pips` interval on each bucket is **realized return historical range**, not a price target. A trader reading "crash_flush p=2%, range [-300, -120] pips" learns the _tail risk magnitude conditional on the regime_, not a setup to execute.

CI guard (ADR-081 extension W105 candidate) :

- `len(scenarios) == 7` exact
- `set(s.label for s in scenarios) == {7 canonical buckets}`
- `abs(sum(s.p for s in scenarios) − 1.0) < 1e-6`
- `all(0.0 ≤ s.p ≤ 0.95 for s in scenarios)` (cap-95 per bucket)
- no `BUY|SELL|TP|SL` tokens in any `s.mechanism` (regex grep)

## Researcher 2026 findings — caveats (sources verified)

The researcher (autonomous subagent 2026-05-11) confirmed :

1. **No institutional precedent for 7-bucket FX/session stratification**. Goldman Sachs publishes 3-category bear-market framework ([Bear Market Anatomy 2025](https://www.gspublishing.com/content/research/en/reports/2025/04/08/0bf285f5-8d4a-478c-843f-4b4ea81256d5.html)). BlackRock Capital Market Assumptions use ±1σ bands ([BlackRock CMA](https://www.blackrock.com/ca/institutional/en/insights/charts/capital-market-assumptions)). IMF Global Financial Stability Report uses baseline + 1-2 adverse ([IMF GFSR Oct 2025 Ch1 Annex](https://www.imf.org/-/media/Files/Publications/GFSR/2025/October/English/ch1annex.ashx)). **Ichor's 7-bucket extension is original** ; magnitudes must be back-tested against per-asset realized history.

2. **Brier multi-class is well-defined**. Murphy 1973 canonical, decomposition extended by Siegert 2017 ([RMetS](https://rmets.onlinelibrary.wiley.com/doi/abs/10.1002/qj.2985)) and Stephenson-Coelho-Jolliffe 2008 ([Cambridge](https://www.cambridge.org/core/journals/judgment-and-decision-making/article/weighted-brier-score-decompositions-for-topically-heterogenous-forecasting-tournaments/8172E04F2DBC601DA5D953D4685CA346)) into 5 components.

3. **Bayesian predictive synthesis** (IMF WP/2025/105, ["Scenario Synthesis"](https://www.imf.org/-/media/files/publications/wp/2025/english/wpiea2025105-print-pdf.pdf)) suggests weighting scenarios by concordance with a reference statistical distribution (Growth-at-Risk quantile regression). Ichor could adopt this in v2 (W113+) once we have enough realized history per (asset, session) to compute a credible 5th-percentile reference. **Out of scope for W105**.

4. **Conviction cap proportional clipping** has no canonical reference but is the most transparent and auditable option vs Dirichlet smoothing. Aligned with Ichor's "every numeric assertion source-stamped" doctrinal floor.

## Acceptance criteria (W105 ship gate)

1. Migration 0039 deployed Hetzner ; `scenarios` JSONB nullable false default empty array.
2. `scenario_calibration_bins` populated for all 6 assets × 4 session types (24 rows minimum, refresh weekly).
3. Pass 6 LLM prompt designed with 7-bucket structured output (Pydantic schema enforced).
4. Cap-and-normalize applied before persist.
5. CI guard tests added to `test_invariants_ichor.py` extension : `test_pass6_scenarios_sum_to_one`, `test_pass6_scenarios_cap_95`, `test_pass6_scenarios_no_buy_sell_tokens`.
6. Reconciler `realized_scenario_bucket` column populated by W108 batch job.
7. Brier-7-bucket scoreboard surfaced on `/calibration` page (extension of W101 scoreboard).
8. Skill score `≥ 0.05` on at least 1 (asset, session) rolling 90d within 6 months — else trigger calibration review.

## Implementation order (W105 sub-waves)

| Sub-wave | Title                                                                               | Effort |
| -------- | ----------------------------------------------------------------------------------- | ------ |
| W105a    | Migration 0039 + `scenario_calibration_bins` table + ORM model                      | 0.5d   |
| W105b    | `services/scenario_calibration.py` — z-score thresholds + per-asset pip translation | 1d     |
| W105c    | `packages/ichor_brain/.../passes/scenarios.py` — Pass-6 implementation              | 2d     |
| W105d    | Pass-6 wired into orchestrator + RunnerCall.tool_config                             | 0.5d   |
| W105e    | Cap-and-normalize + sum-to-1 enforcement                                            | 0.5d   |
| W105f    | CI guards extension `test_invariants_ichor.py`                                      | 0.5d   |
| W105g    | Reconciler `realized_scenario_bucket` + Brier 7-bucket compute                      | 1d     |
| W105h    | `/calibration` page extension : 7-bucket reliability diagram per asset              | 1d     |

**Total** : 7-8 dev-days. Aligned with ADR-082 W105 estimate.

## Open questions (decisions taken pending Eliot validation)

- Use realized **z-score of intraday return on the session window** (12h close-to-close) as the bucket key, NOT the daily close. The session window is the trading-day-relevant horizon for Eliot's Londres/NY momentum strategy.
- Calibration window = **252 trading days rolling** (institutional convention for FX, per researcher).
- Refresh `scenario_calibration_bins` **weekly Sunday** (Sunday 00:00 UTC cron alongside the realized-outcome reconciler).
- The 7 labels are kept verbatim from `ICHOR_PLAN.md:209-217` to preserve traceability with the founding plan.

## References

- ADR-017 (boundary — no BUY/SELL)
- ADR-022 (conviction cap 95%)
- ADR-081 (CI-guarded doctrinal invariants)
- ADR-083 D2 (Pass 6 7-stratified ratified)
- [ICHOR_PLAN.md:209-217](../ICHOR_PLAN.md) (7-bucket source-of-truth)
- [ICHOR_AUDIT_2026-05-11_12_GAPS.md G12](../audits/ICHOR_AUDIT_2026-05-11_12_GAPS.md)
- Murphy 1973 — "A new vector partition of the probability score" _J. Appl. Meteorol._ 12 : 595–600
- [Brier score — Wikipedia](https://en.wikipedia.org/wiki/Brier_score)
- [Siegert 2017 — RMetS](https://rmets.onlinelibrary.wiley.com/doi/abs/10.1002/qj.2985)
- [IMF WP/2025/105 — Bayesian Scenario Synthesis](https://www.imf.org/-/media/files/publications/wp/2025/english/wpiea2025105-print-pdf.pdf)
- [BlackRock CMA](https://www.blackrock.com/ca/institutional/en/insights/charts/capital-market-assumptions)
- [Goldman Sachs Bear Market Anatomy 2025](https://www.gspublishing.com/content/research/en/reports/2025/04/08/0bf285f5-8d4a-478c-843f-4b4ea81256d5.html)
