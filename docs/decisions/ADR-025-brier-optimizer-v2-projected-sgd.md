# ADR-025 — Brier optimizer V2: projected SGD on the per-factor drivers matrix

- **Date**: 2026-05-06
- **Status**: Accepted
- **Supersedes**: extends ADR-022 (probability bias models reinstated)
- **Superseded by**: —

## Context

Migration `0026_session_card_drivers.py` added a `drivers` JSONB column on
`session_card_audit` whose shape is
`list[{factor: str, contribution: float, evidence: str}]`. Each row holds
the per-factor contribution snapshot from
`services/confluence_engine.assess_confluence` at the moment the session
card was generated. The column was added explicitly to feed a V2 of the
Brier→weights optimizer (cf. ADR-022).

V1 (`cli/run_brier_optimizer.py`) only writes a *diagnostic* row that
aggregates `brier_contribution` across the lookback window — it does not
optimize per-factor weights. The math primitives in
`services/brier_optimizer.py` (`project_simplex_bounded`, `step_sgd`,
`run_optimization`, `persist_optimizer_run`) have always been ready ; what
was missing was the bridge from the JSONB drivers column to the
`(N_cards, N_factors)` matrix the primitives expect, plus the binary
outcomes vector.

This ADR captures the V2 sprint that closes that bridge.

## Decision

V2 is a new CLI `apps/api/src/ichor_api/cli/run_brier_optimizer_v2.py`
that runs alongside V1 (V1 stays unmodified — it still produces its
diagnostic row nightly). V2 adds three helpers to
`services/brier_optimizer.py` :

- `derive_realized_outcome(bias, conviction, brier)` — recovers the
  binary outcome `y ∈ {0, 1}` from the persisted Brier contribution via
  the identity `brier = (p_up − y)²` with `y ∈ {0, 1}`. Returns `None`
  when both candidates collapse (only happens at `p_up = 0.5`, neutral
  bias) — the row is then skipped.
- `drivers_to_signal_row(drivers, factor_names)` — pivots a JSONB row
  into a `(F,)` array of signals in `[0, 1]`. Sign convention :
  `signal = 0.5 + 0.5 * contribution` (with `contribution ∈ [-1, +1]`
  per `confluence_engine.Driver`). Missing factors fall back to `0.5`
  (neutral). Defensive against malformed entries (string contributions,
  non-dict items, unknown factor names) — they're skipped, not crashed.
- `aggregate_drivers_matrix(session, asset, regime, lookback_days)` —
  runs the SQL select on `session_card_audit` with non-null `drivers` +
  non-null `brier_contribution`, applies the two helpers above, and
  returns a `DriversMatrix` dataclass (`factor_names`, `factor_signals`,
  `outcomes`, `n_skipped_no_drivers`, `n_skipped_ambiguous_outcome`).
  Returns `None` if fewer than `min_obs=30` rows survive — projected
  SGD on tiny batches is meaningless.

The new CLI :

1. Reads env flag `ICHOR_API_BRIER_V2_ENABLED` (default `false`). When
   unset / false it logs a single line and exits 0 — V1 nightly cron
   stays untouched.
2. Lists distinct `(asset, regime)` groups in the lookback window.
3. For each group : builds the matrix, projects current active weights
   onto the canonical factor list (missing keys → equal-weight share),
   runs `run_optimization` (200 SGD steps, lr=0.05, momentum=0.9,
   simplex bounds [0.05, 0.5]).
4. Logs `n_obs / brier_before / brier_after / delta / converged`.
5. Flags adoption candidates when `delta < −MDE_DELTA` (MDE = 0.02,
   matches V1 holdout protocol).
6. With `--persist` : calls `persist_optimizer_run` with
   `algo='online_sgd'` (already whitelisted by migration 0024 CHECK,
   no schema change needed). Writes `adopted=False` rows ; promotion
   to `adopted=True` is gated on a future 21-day holdout job.

Persistence schema unchanged — V2 reuses `brier_optimizer_runs` rows
that V1 already writes. The `algo` column distinguishes
`'diagnostic_v1'` (V1) from `'online_sgd'` (V2).

Cron : `scripts/hetzner/register-cron-brier-optimizer-v2.sh` registers a
new `ichor-brier-optimizer-v2.timer` at `03:45 Europe/Paris` (15 min
after V1) with `After=ichor-brier-optimizer.service` so V1 still runs
even if V2 fails.

## Justification

### Why a new CLI rather than a flag on V1

A flag (`--v2`) would couple the scheduling and the exit codes of the
two paths. Splitting into two CLIs lets ops disable V2 (env flag) or
roll it back (revert this ADR's commits) without touching V1's nightly
diagnostic. The two cron units run independently and post separate
`brier_optimizer_runs` rows distinguishable by `algo`.

### Why reverse-engineer outcomes instead of joining `polygon_intraday`

Joining adds a dependency on the bar source (which timeframe ? what
happens for assets without intraday bars in the window ?) and a
non-trivial SQL. The Brier identity inverse is exact for any
non-neutral card and only fails on `p_up = 0.5` rows that carry no
directional information anyway. The optimizer skips those rows
explicitly with a counter (`n_skipped_ambiguous_outcome`) so the
operator sees the skip rate.

### Why feature-flag gated

Drivers JSONB column landed 2026-05-05. Cards generated before that
date have `drivers IS NULL` — V2 just skips them. We expect ~30 days
of populated cards before the optimizer becomes statistically
meaningful (the `MIN_OBS_PER_GROUP=30` floor). The flag lets Eliot
delay activation until enough drivers-tagged cards have accumulated,
without merging dead code into the cron.

### Why `algo='online_sgd'` rather than `'online_sgd_v2'`

Migration 0013 originally whitelisted `('online_sgd', 'thompson_beta')`,
extended by 0024 with `'diagnostic_v1'`. The V2 algo IS projected
online SGD (the same as the V1 math primitives describe) — the only
difference is V2 actually runs them on real per-factor data instead
of a diagnostic. Adding a third algo string would force a fourth
migration for no semantic gain. Distinction by `notes` field if needed.

## Consequences

### Code

- Three new helpers in `apps/api/src/ichor_api/services/brier_optimizer.py`
  (≈140 lines added) — backwards compatible with V1.
- New CLI `apps/api/src/ichor_api/cli/run_brier_optimizer_v2.py`.
- 17 new pytest cases in `apps/api/tests/test_brier_optimizer_v2.py`
  (no DB dependency).
- New deployment script `scripts/hetzner/register-cron-brier-optimizer-v2.sh`.

### Operations

- A new env var to provision in `/etc/ichor/api.env` on Hetzner :
  `ICHOR_API_BRIER_V2_ENABLED=true` (when ready). Default unset.
- A new systemd timer `ichor-brier-optimizer-v2.timer` to deploy via
  the registration script.
- `brier_optimizer_runs` will start receiving `algo='online_sgd'` rows
  alongside the existing `'diagnostic_v1'` rows. Dashboards showing
  the optimizer history must group by `algo`.

### Holdout / adoption

This sprint does NOT ship the adoption-promotion job (the job that
flips `adopted=True` after 21 days of out-of-sample data confirms
`delta < -MDE`). That's a separate follow-up. V2 currently surfaces
adoption candidates in the cron log only.

### Future work

- 21-day holdout adoption job (separate sprint).
- Wire `confluence_engine.assess_confluence` to actually populate
  `SessionCard.drivers` end-to-end (currently brain pipeline still
  emits drivers but the persistence layer needs verification ; cards
  generated from 0026 onwards are the optimizer's training data).
- Per-regime weight resets when `concept_drift` flags a regime change.

## Verification

- Unit tests : 28 passed (`pytest tests/test_brier_optimizer_v2.py`).
- Regression : 806 passed in full apps/api suite, zero new failures.
- Lint : `ruff check` clean on the three modified files.
- Mypy : no new errors introduced (3 pre-existing V1 errors on numpy
  return types remain ; addressed in D.4 CI Wave 5).
