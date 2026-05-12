# ADR-087: Phase D — auto-improvement four loops (Couche 9 Learn closure)

**Status**: Accepted — architectural blueprint, implementation lands W113-W117

**Date**: 2026-05-12

**Supersedes**: none

**Extends**: [ADR-009](ADR-009-voie-d-no-api-consumption.md) (Voie D),
[ADR-017](ADR-017-reset-phase1-living-macro-entity.md) (boundary),
[ADR-022](ADR-022-probability-bias-models-reinstated.md) (probability-only
trainers + Critic gate), [ADR-023](ADR-023-couche2-haiku-not-sonnet-on-free-cf-tunnel.md)
(Couche-2 Haiku low), [ADR-081](ADR-081-doctrinal-invariant-ci-guards.md)
(CI guards), [ADR-085](ADR-085-pass-6-scenario-decompose-taxonomy.md)
(Pass-6 7-bucket), [ADR-086](ADR-086-rag-layer-past-only-bge-small.md)
(RAG layer)

## Context

The [ARCHITECTURE_CIBLE.md](../ARCHITECTURE_CIBLE.md) 10-layer
stratification scores **Couche 9 Learn = 1/10** as of 2026-05-12 —
the lowest of the 10 layers. The session-card persistence + Brier
scoring + scenario calibration are wired, but **none of the four
auto-improvement feedback loops actually close** :

1. **Brier optimizer V1** (`cli/run_brier_optimizer.py`) computes per
   `(asset, regime)` Brier and writes `brier_optimizer_runs` rows
   with `adopted=False` ; **no auto-promotion path** exists.
   `confluence_engine.py:599-628` reads `latest_active_weights` and
   falls back to equal-weight when no `adopted=True` row exists —
   which is always. Effect : **the optimizer runs nightly producing
   computations nobody consumes**.

2. **ADWIN concept drift** (`cli/run_concept_drift.py`) emits river
   ADWIN signals with the default `delta=0.002` ; output is logged
   but **`BIAS_BRIER_DEGRADATION` alert is wired to a sibling CLI
   `cli/run_brier_drift_check.py` not to the ADWIN output itself**.
   Feature drift on the 6-dim cross-asset matrix is not tracked.

3. **Post-mortem weekly** (`cli/run_counterfactual_batch.py` Sunday
   18h Paris) generates Claude Opus counterfactual narratives but
   **never feeds the result back into Pass-3 stress prompts** ; the
   narrative dies in a JSONB row consumed by zero downstream paths.

4. **Méta-prompt tuning** : `services/meta_prompt_tuner.py` exists as
   a V0 DSPy MIPROv2 scaffold + migration `0015_prompt_versions.py`
   wrote the schema. **No CLI binary, no cron timer, no DSPy
   declared as a dependency**. Pure scaffold.

A 2026 SOTA researcher subagent commissioned 2026-05-12 round 13
mapped the canonical solutions. This ADR ratifies the four
architectural decisions ahead of the wave implementations.

## Decisions

### D1 — Brier aggregator : Vovk Aggregating Algorithm (W113)

Replace the V1/V2 SGD-on-confluence-weights with the **Vovk-Zhdanov
Aggregating Algorithm** (ICML 2008 — _"Prediction with expert advice
for the Brier game"_). The Brier loss is η-mixable with η=1 closed-form
optimal, yielding constant `O(log N)` regret vs the best single
expert in hindsight — strictly better than the `√(T log N)` bound of
generic EWA/Hedge.

**For Ichor with N=6 trainers** (lightgbm / xgboost / random_forest /
logistic / mlp / numpyro_bias per ADR-022), `O(log 6) ≈ 2.5` —
essentially free, tail regret never explodes.

**Architecture** :

- One **weight pocket per `(asset × regime_bucket)`** (7 buckets from
  the W104c master regime classifier).
- Update on every reconciled card :
  `w_i ← w_i · exp(-η · brier_i)` with `η=1`, then floor `w_i = max(w_i, 0.02)` (Herbster-Warmuth Fixed-Share), then renormalize.
- Cold-start a new pocket with `1/6` uniform + Dirichlet shrinkage
  toward global weights for the first 30 cards.
- Daily batch at 03:30 Paris (after W105g reconciler 02:00 Paris) on
  cards whose outcome resolved overnight.

**Persistence** : new table `brier_aggregator_weights(asset, regime,
weights JSONB, n_updates, updated_at)` (migration 0042 candidate).

**Promotion** : weights are **always active** under AA — there is no
holdout/champion-challenger gate. The mathematical guarantee replaces
the empirical gate. This is the key shift vs the V1 `adopted=False`
pattern that produced no promotions in 30 days.

**Why not River AA primitive** : River 4.15.0 ships online classifiers
and bagging/boosting ensembles but **no Vovk-style weighted-experts
primitive**. Custom ~50 LOC implementation is the right call.

### D2 — ADWIN drift : tiered response + lower delta (W114)

Lower the default ADWIN `delta` from `0.002` (River default — over-fires
on FX noise) to `0.001`. Use **two ADWIN instances per asset** :

- **Per-target Brier drift** (operationally critical) → feeds the
  `BIAS_BRIER_DEGRADATION` alert.
- **Per-feature drift on the 6-dim cross-asset matrix** (W79
  ADR-075) → early warning, lower priority.

**Tiered response on drift detection** :

| Tier | Detected                                        | Action                                                                                                                                                                    |
| ---- | ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1    | Drift on a SINGLE feature (e.g. SKEW only)      | log + ntfy alert, no model action                                                                                                                                         |
| 2    | Drift on target Brier for one asset             | freeze the current Vovk-AA pocket, spawn challenger pocket initialized uniform, shadow-run 14 days, promote if `brier_challenger < brier_incumbent` (champion/challenger) |
| 3    | Cross-asset drift on ≥3 features simultaneously | flag macro regime shift, force re-run of master regime classifier, **do NOT auto-retrain** — wait for human review                                                        |

**2026 alternatives evaluated** (BOCPD with Student-t observation
model — arXiv:2407.16376 ; UDD MC Dropout no-label drift — arXiv:2203.04769 ;
Trinity-Controller ADWIN 2026) **deferred to W11x+** unless drift
false-alarm rate exceeds 10/week post-W114.

### D3 — Post-mortem : Penalized Brier Score + addenda injector (W115)

Sunday 18h00 Paris (5h before Asia open Sunday 23h Paris). Anchor on
the institutional pattern : BlackRock Aladdin post-investment
analytics + Bridgewater AIA Labs + Two Sigma Venn all converge on
narrative-augmented squared-residual ranking, weekly batched, fed
forward into the next forecast cycle.

**Three-tier miss filter** :

- **Tier A (always analyze)** — skill score `< 0` vs climatology
  baseline (Murphy decomposition reliability term dominant — "you
  predicted worse than the historical base rate").
- **Tier B (top-N)** — Brier residual `> p95` of the week. Cap N=10
  to keep Opus context tight.
- **Tier C (pattern)** — 3+ misses same direction × same asset ×
  same regime within 7d → systemic miss, escalate.

**Critical 2024 caveat** (Ahmadian et al. arXiv:2504.04906) : raw
Brier doesn't satisfy the "superior property" — overconfident-wrong
can score better than uncertain-correct. Use **Penalized Brier Score
(PBS)** for the ranking, not raw Brier.

**Anti-hindsight guard** (Pre-mortem Forecasting BTF-2 benchmark,
arXiv:2604.26106) : the post-mortem agent must reconstruct **what
the data_pool looked like at forecast time**, not at post-mortem
time. Use the existing W105 source-stamping (`mechanisms[].sources`
references) — **never feed Opus the resolved outcome until step 2**.

**Output schema** :

```json
{
  "miss_id": "uuid",
  "asset": "EUR_USD",
  "regime": "usd_complacency",
  "brier_residual": 0.41,
  "pbs": 0.48,
  "pre_forecast_data_snapshot": "<reconstructed markdown>",
  "counterfactual_narrative": "<Opus 4.7 output, hindsight-isolated>",
  "identified_blind_spot": "...",
  "proposed_stress_addendum": "<200 tokens max — prefixed Hindsight only — do not treat as forward signal>",
  "trainer_brier_breakdown": {"lightgbm": 0.22, "xgboost": 0.19, ...}
}
```

**Addendum injection** : `proposed_stress_addendum` rate-limited to **3
most recent addenda per regime** when injected into Pass-3 prompt —
prevents prompt bloat + drift.

### D4 — Méta-prompt tuning : DSPy 3.2 + GEPA via custom BaseLM (W116)

**Voie D compatibility** : DSPy 3.2.0 (Sep 2025) removed adapter-level
litellm imports — subclass `dspy.BaseLM` with the existing
`claude-runner` HTTP endpoint (`/v1/agent-task`). No Anthropic SDK
call ; the optimizer LM hits Opus 4.7 via claude-runner ; the judge
LM hits Haiku low via the same path. Both stay inside Voie D
(ADR-009, ADR-023).

**Optimizer choice** : **GEPA** (Genetic-Pareto, arXiv:2507.19457,
ICLR 2026 Oral). Now exposed as `dspy.GEPA` and standalone
`pip install gepa`. GEPA outperforms MIPROv2 by +13 % and GRPO RL by
+20 % with **35× fewer rollouts** — perfect fit for a flat-rate
Max 20× budget. Crucially, GEPA reads **full execution traces**
(not just scalar metrics), aligning with the 4-pass system where
intermediate pass outputs are themselves signal.

**Cadence** : weekly batch Saturday 12h Paris (~ 2 h optimizer
budget on resolved cards from the previous week).

**ADR-017 boundary protection — three mechanical guards** :

1. **Metric penalty** — the GEPA scoring function includes a _hard
   zero_ term if the candidate prompt or its generated outputs match
   the regex `\b(BUY|SELL|TP|SL|TAKE PROFIT|STOP LOSS)\b`.
2. **Frozen invariant tokens** — ADR-017 sentinel sentences as
   `dspy.Hint` blocks the optimizer cannot rewrite (DSPy signature-
   level immutability).
3. **CI guard** — reuse W90 `test_invariants_ichor.py` tokenize-based
   BUY/SELL scan ; after every GEPA optimization run, the candidate
   prompt must pass before being persisted to `prompt_versions`.

**Persistence** : `prompt_versions` table already exists (migration 0015) ; activate it with GEPA-emitted prompt versions.

### D5 — Cross-cutting `auto_improvement_log` table (W113)

All four loops share **one Postgres table** for provenance + revert :

```sql
CREATE TABLE auto_improvement_log (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  loop_id     TEXT NOT NULL,             -- 'brier_aggregator' | 'adwin_drift' | 'post_mortem' | 'meta_prompt'
  ran_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  action      TEXT NOT NULL,             -- 'pocket_update' | 'tier2_freeze' | 'addendum_emitted' | 'prompt_version_promoted' etc.
  before_state JSONB,
  after_state  JSONB,
  brier_delta  NUMERIC(8,5),             -- nullable when not applicable
  approved     BOOLEAN NOT NULL DEFAULT TRUE,
  notes        TEXT
);
CREATE INDEX ON auto_improvement_log (loop_id, ran_at DESC);
```

Immutable trigger pattern (ADR-029 + ADR-077 family) — append-only,
no UPDATE/DELETE except via sanctioned-purge GUC. Migration 0042
candidate.

**Operational benefit** : every weight pocket update, every drift
freeze, every promoted prompt version is revertable in `< 30 s`
by reading the `before_state` JSONB (Mark Douglas position sizing
applied to ML ops).

## Implementation order

| Wave     | Loop                                                                                                                  | Effort | Depends on                                                                     |
| -------- | --------------------------------------------------------------------------------------------------------------------- | ------ | ------------------------------------------------------------------------------ |
| **W113** | Cross-cutting `auto_improvement_log` table + migration 0042 + ADR-081 invariant guard for the schema shape            | 0.5d   | migration only                                                                 |
| **W114** | Loop 2 ADWIN drift tier dispatcher (lowest cost, highest immediate signal)                                            | 1d     | W113                                                                           |
| **W115** | Loop 1 Brier aggregator (Vovk AA) + `brier_aggregator_weights` table + Vovk η=1 formula + per-(asset, regime) pockets | 2d     | W113 ; W114 (drift tier-2 freezes pocket)                                      |
| **W116** | Loop 3 post-mortem PBS + anti-hindsight reconstruction + addendum injector into Pass-3 prompt                         | 1d     | W115 (Brier trainer breakdown depends on aggregator surface)                   |
| **W117** | Loop 4 DSPy 3.2 + GEPA via custom `BaseLM`/claude-runner + Saturday 12h cron + ADR-017 regex penalty + CI guard       | 5d     | W115 + W116 (trainer Brier + post-mortem addenda are the GEPA training signal) |

**Total** : ~9.5 dev-days. Each wave atomic + revertable.

## Acceptance criteria

1. **W113** — `auto_improvement_log` table live Hetzner ; immutable
   trigger CI-guarded ; ADR-081 extension test `test_auto_improvement_log_immutable_trigger_present`.
2. **W114** — ADWIN delta = 0.001 ; two instances per asset ; tier-1/2/3
   dispatcher wired into alert catalog ; tier-2 freezes Vovk pocket on
   target Brier drift via `auto_improvement_log` row.
3. **W115** — Vovk AA pocket per (asset, regime) ; daily 03:30 cron ;
   `brier_aggregator_weights` consumed by `confluence_engine.py` (the
   `latest_active_weights` path NOW returns non-equal-weight rows) ;
   simplex invariant test ; CI guard test `test_brier_aggregator_weights_simplex`.
4. **W116** — Sunday 18h cron ; PBS-ranked top-10 misses per week ;
   `pre_forecast_data_snapshot` reconstructed (anti-hindsight test) ;
   Pass-3 receives at most 3 addenda per regime.
5. **W117** — GEPA Saturday 12h ; judge = Haiku low via claude-runner ;
   ADR-017 regex penalty CI-guarded ; promoted prompt versions land
   in `prompt_versions` table ; pre-promotion BUY/SELL tokenize scan
   blocks invalid candidates.

## Consequences

### Positive

- **Couche 9 score moves 1/10 → 7/10+** within 2 dev-weeks (all 4
  loops closed end-to-end).
- **Vovk AA mathematical guarantee** replaces the empirical 21-day
  holdout that never promoted — weights actually move.
- **DSPy GEPA + claude-runner** unlocks meta-prompt tuning **inside
  Voie D** (no Anthropic SDK consumption introduced) — the closest
  the project gets to self-improvement without crossing ADR-009.
- **`auto_improvement_log`** centralises provenance for the four
  loops + 30 s revert path. Mark Douglas "one trade = one revertable
  position" applied to ML ops.

### Accepted

- **5 dev-day W117 GEPA cost** is the largest unit of work in Phase D.
  Mitigation : land W113-W116 first (4.5 dev-days, Couche 9 reaches
  6/10), then re-evaluate W117 priority vs other unblocks.
- **Vovk AA is a frequentist-minimax algorithm** — no posterior
  credibility intervals on weights. If we later want to report
  meta-uncertainty, swap for a Dirichlet posterior in a successor
  ADR.
- **ADWIN delta=0.001 is empirical** — tune against a 4-week
  stationary segment in W114 acceptance.
- **PBS adoption** swaps the conventional Brier ranking for a
  penalty-augmented one — calibration interpretability slightly
  decreases ; mitigation : surface both raw Brier and PBS on the
  `/calibration` page.

## Web references absorbed (researcher subagent 2026-05-12)

- [Vovk & Zhdanov — Prediction with expert advice for the Brier game (ICML 2008)](https://dl.acm.org/doi/abs/10.1145/1390156.1390295)
- [Cesa-Bianchi & Lugosi — Prediction, Learning, and Games](https://www.semanticscholar.org/paper/Prediction,-learning,-and-games-Cesa-Bianchi-Lugosi/0538e399046c74d95124c715760aa51ab4716dce)
- [Expert Aggregation for Financial Forecasting (arXiv 2111.15365)](https://arxiv.org/html/2111.15365)
- [Adaptive-Delta ADWIN 2025 — Balancing Sensitivity & Stability](https://www.researchgate.net/publication/397309076_Adaptive-Delta_ADWIN_for_Balancing_Sensitivity_and_Stability_in_Streaming_IDS)
- [Bayesian Autoregressive BOCPD with time-varying parameters (arXiv 2407.16376)](https://arxiv.org/html/2407.16376v1)
- [Uncertainty Drift Detection — MC Dropout no-label drift (arXiv 2203.04769)](https://arxiv.org/pdf/2203.04769)
- [Penalized Brier Score (Ahmadian et al. arXiv 2504.04906)](https://arxiv.org/html/2504.04906v4)
- [Pre-mortem Forecasting BTF-2 benchmark (arXiv 2604.26106)](https://arxiv.org/html/2604.26106)
- [DSPy 3.2.0 — BaseLM decoupling from litellm](https://github.com/stanfordnlp/dspy/releases/tag/3.2.0)
- [GEPA — Genetic-Pareto reflective prompt optimization (arXiv 2507.19457, ICLR 2026 Oral)](https://arxiv.org/abs/2507.19457)
- [BlackRock Aladdin Preqin Feb 2026 — post-investment analytics surface](https://www.blackrock.com/aladdin/press-release-blackrock-aladdin-drives-private-markets-transparency)
- [Bridgewater AIA Labs — Dalio principles to algorithmic intelligence](https://www.hedgeco.net/news/03/2026/bridgewater-dalios-principles-to-algorithmic-intelligence-the-road-to-5billion.html)
