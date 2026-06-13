# ADR-116 — Benchmark gate CLI: apex verdict over the real NY window (Chantier A, slice-2)

- **Status:** Accepted — 2026-06-13
- **Deciders:** owner (delegated "fais tout, décide seul"), engine
- **Supersedes:** none
- **Related:** ADR-114 (benchmark_gate pure-core) · ADR-106 (SessionVerdict) ·
  PLAN_DIRECTEUR §5 Chantier A · ADR-017 · ADR-022 · ADR-009 (Voie D) ·
  conviction_fusion / session_verdict_builder

## Context

ADR-114 shipped the pure-core benchmark gate (deterministic, I/O-free), but it
produces no report on real data. PLAN §5 gate A is "**the report exists and is
reproducible**". This ADR is the CLI that produces it:
`apps/api/src/ichor_api/cli/run_benchmark_gate.py`.

The first draft of this slice (caught by fresh adversarial review before merge)
fell into two "benchmark that lies by construction" traps. This ADR records the
**corrected** design.

## Decision

A CLI that, over historical `pre_ny` sessions, scores **the apex
`SessionVerdict` Ichor actually surfaced to the user** against the benchmark
baselines, on **Eliot's real NY trading window**, via the unchanged
`services.benchmark_gate`.

**Design decisions (the corrections):**

1. **Verdict = the apex direction + conviction the user sees** — NOT the per-card
   `bias_direction` column. The apex `/v1/verdict` derives direction from the 7
   Pass-6 scenario buckets fused with the synthesis snapshots frozen on the card
   (ADR-106 D2 + S04 `conviction_fusion`); `bias_direction` is a per-asset
   specialization read that can legitimately diverge (card_coherence demotes to
   neutral but never flips, so the two are not interchangeable). The CLI
   reproduces the apex EXACTLY by **reusing the canonical
   `session_verdict_builder._extract_synthesis_primitives` +
   `_derive_direction_and_conviction`** (importing these module-private helpers
   is deliberate: it guarantees the benchmark cannot silently drift from the
   verdict it claims to measure). Malformed/dormant scenarios (≠7 buckets) →
   `neutral`/0, mirroring the builder fallback.

2. **Realised return = the exact NY window Eliot trades** — 14:00→20:00 Paris
   (DST-correct via `market_session.PARIS`), recomputed from `polygon_intraday`
   1-min bars. NOT the `reconcile_outcomes` snapshot
   (`realized_open/close_session`), whose window is `[generated_at,
timing_window_end OR generated_at+8h]` ≈ 13:30→21:30 for a pre-NY card — a
   _different_ window than the one the report names (it would include ~30 min
   before entry and ~90 min after the 20h cut, or an arbitrary LLM window when
   `timing_window_end` is set). `realized_return_pct = (close/open − 1) × 100`
   over the bars in `[14:00, 20:00)` Paris; a window with `< _MIN_BARS` (30) bars
   is skipped (honest absence — e.g. SPY RTH opening after 14h Paris).

3. **One verdict per `(asset, NY session day)`** — the latest `pre_ny` card,
   deduped by `(asset, Paris session_date)`.

4. **Output = markdown** (stdout + optional `--output` file). **No new table, no
   migration** — the report is a reproducible artifact, not persisted state.

5. **I/O isolated**: pure helpers (`ny_window_utc`, `window_return_pct`,
   `card_verdict`, `dedup_latest_per_session`, `_session_date`, `_parse_since`,
   `render_report`) are unit-tested with synthetic fixtures; the DB reads are
   thin async wrappers, tested with a stubbed session (no Postgres).

**Doctrine alignment:**

- **ADR-009 (Voie D):** zero LLM, zero spend — DB read + arithmetic.
- **ADR-017:** report prose is produced by `format_report_markdown` (regex-guarded);
  the CLI adds only descriptive headers (no trade tokens; tested).
- **ADR-022:** conviction is the apex 0..95 value (defensively clamped).
- **ADR-114:** composes the pure-core unchanged.

## Consequences

- **+** The benchmark measures **what it names**: the user-facing apex verdict,
  on Eliot's actual 14h-20h NY window — no hidden window/verdict skew.
- **+** PLAN gate A reachable on real data; unblocks honest Chantier B/C.
- **−** A **live run needs the production database** (`ICHOR_API_DATABASE_URL`) —
  both `session_card_audit` (verdicts + snapshots) and `polygon_intraday` (1-min
  bars). It cannot run in CI / locally without prod access. The live report is
  the witness, gated on deploy or a server-side run.
- **−** Coupling: importing two module-private helpers from
  `session_verdict_builder`. Accepted — fidelity to the apex verdict is the whole
  point; a public re-export can follow if the coupling proves brittle.
- **Risk:** realised-outcome history is young (~158 cards at 2026-05-13, verdicts
  from ~late May) AND `polygon_intraday` 1-min retention may drop old bars → some
  historical sessions are skipped (counted honestly). The walk-forward OOS window
  will be short — `evaluate_walk_forward` may return `None` (insufficient), which
  the CLI surfaces honestly. Nothing is imputed.

## Gate (pass/fail, falsifiable)

slice-2 code: CLI reproduces the apex verdict per card (unit-tested: bullish/
bearish/balanced/malformed buckets), computes the 14h-20h window return
(DST-correct, min-bars skip, non-positive-open skip), dedups per session,
composes the pure-core; ruff + mypy + tests green. (Met by this slice.)

slice-2 witness (future, needs prod DB): a server-side run emits a reproducible
report over the real verdict + bar history — beating baselines or honestly
reporting it does not, with `n_sessions` stated.
