# ADR-116 — Benchmark gate CLI on reconciled history (Chantier A, slice-2)

- **Status:** Accepted — 2026-06-13
- **Deciders:** owner (delegated "fais tout, décide seul"), engine
- **Supersedes:** none
- **Related:** ADR-114 (benchmark_gate pure-core) · PLAN_DIRECTEUR §5 Chantier A ·
  ADR-017 · ADR-022 · ADR-009 (Voie D) · reconcile_outcomes / services.brier

## Context

ADR-114 shipped the pure-core benchmark gate (deterministic, I/O-free), but it
produces no report on real data — slice-1 explicitly deferred "the CLI that
joins verdicts with realised outcomes" to a slice that needs production data.
PLAN §5 gate A is "**the report exists and is reproducible**". This ADR is that
CLI: `apps/api/src/ichor_api/cli/run_benchmark_gate.py`.

## Decision

A CLI that reads historical session verdicts, joins their realised NY-window
outcomes, builds `VerdictOutcomeSample`s, and renders the in-sample +
walk-forward OOS reports via the unchanged `services.benchmark_gate`.

**Design decisions (the non-obvious ones):**

1. **Realised-return source = the reconciled `realized_open_session` /
   `realized_close_session` columns on `session_card_audit`**, NOT a fresh
   `polygon_intraday` query. Rationale: those columns are written by
   `cli/reconcile_outcomes.py` from Polygon intraday bars over the card's timing
   window and **persisted permanently** — immune to 1-min bar retention (the
   benchmark runs over _historical_ sessions, where raw bars may be gone). They
   are also the **same** realised outcome the Brier calibration already uses, so
   the benchmark is consistent with the existing track-record. This removes all
   timezone-window and missing-bar handling from this slice.
   `realized_return_pct = (close/open − 1) × 100`.

2. **Verdict source = `bias_direction` on the `pre_ny` card** — the read Ichor
   actually emitted (post `card_coherence`) to anticipate the NY session Eliot
   trades. Deduped to the latest card per `(asset, session_date)`.

3. **`bias_direction` (DB `long`/`short`/`neutral`) → pure-core
   `up`/`down`/`neutral`** mapping lives in the CLI (no upstream helper existed);
   fail-closed on an unknown value.

4. **Output = markdown** (stdout + optional `--output` file). **No new table, no
   migration** — the report is a reproducible artifact, not persisted state.
   (Re-runnable on demand; deterministic given the same reconciled rows.)

5. **I/O isolated**: pure transforms (`bias_to_direction`, `clamp_conviction`,
   `realized_return_pct`, `rows_to_samples`, `render_report`) are unit-tested
   with synthetic fixtures; the DB read is a thin async wrapper, tested with a
   stubbed session (no Postgres).

**Doctrine alignment:**

- **ADR-009 (Voie D):** zero LLM, zero spend — DB read + arithmetic.
- **ADR-017:** report prose is produced by `format_report_markdown` (already
  regex-guarded); the CLI adds only descriptive headers (no trade tokens; tested).
- **ADR-022:** `conviction_pct` clamped to 0..95 before the pure-core boundary.
- **ADR-114:** composes the pure-core unchanged.

## Consequences

- **+** PLAN gate A is reachable on real data: a reproducible report stating,
  with costs included, whether Ichor's verdict beats passive/naive baselines
  out-of-sample.
- **+** Unblocks the honest pursuit of Chantier B/C (gated behind A).
- **+** Composes the already-witnessed reconciliation — no new realised-data path
  to validate.
- **−** A **live run needs the production database** (`ICHOR_API_DATABASE_URL`);
  it cannot run in CI / locally without prod access. The live report is the
  witness, gated on deploy or a server-side run.
- **Risk:** realised-outcome history is young (~158 rows at 2026-05-13, verdicts
  from ~late May). The walk-forward OOS window will be short — `evaluate_walk_forward`
  may return `None` (insufficient), which the CLI surfaces honestly. Unreconciled
  rows (NULL realised) are skipped and counted, never imputed.

## Gate (pass/fail, falsifiable)

slice-2 code: CLI builds correct `VerdictOutcomeSample`s from reconciled rows
(unit-tested: mapping, clamp, return%, dedup, skip-unreconciled, honest empty);
composes the pure-core; ruff + mypy + tests green. (Met by this slice.)

slice-2 witness (future, needs prod DB): a server-side run emits a reproducible
report over the reconciled verdict history — beating baselines or honestly
reporting it does not, with `n_sessions` stated.
