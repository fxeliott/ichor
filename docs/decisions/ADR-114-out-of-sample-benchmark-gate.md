# ADR-114 — Out-of-sample benchmark gate (Chantier A, slice-1 pure-core)

- **Status:** Accepted (slice-1 pure-core) — 2026-06-13
- **Deciders:** owner (delegated), engine
- **Supersedes:** none
- **Related:** PLAN_DIRECTEUR §5 Chantier A · ADR-106 (SessionVerdict contract) ·
  ADR-022 (cap-95) · ADR-017 (no BUY/SELL boundary) · ADR-009 (Voie D)

## Context

PLAN*DIRECTEUR §5 ranks **Chantier A (benchmark & trading-grade validation)
FIRST**, before B and C: *"enriching a system without an out-of-sample
benchmark produces narrative, not edge"\_ (PLAN §5, "Why this order").
Chantier A is the hard prerequisite that conditions every later edge claim,
and it directly answers the owner's most-repeated S06 demand: a verdict that
is **real anticipation, not a 50/50 coin-flip** — which is only provable by
measuring whether the `SessionVerdict` directional read beats passive and
naive baselines **out-of-sample**.

Before this ADR there was **no benchmark module** in the codebase (grep
`buy_and_hold|walk_forward|benchmark_gate` over `apps/api/src` returns only
incidental matches — a comment in `collectors/market_data.py`, local
`baseline` helpers in the Brier optimiser / post-mortem). The prediction-
quality machinery that DID exist (`predictions_audit`, `brier_feedback`,
`run_post_mortem_pbs`, `empirical_reaction_beta`) measures **calibration**,
not **edge versus a passive alternative**.

## Decision

Introduce a **pure-core, deterministic, I/O-free** benchmark module
`apps/api/src/ichor_api/services/benchmark_gate.py` that scores a sequence of
`(asset, NY-session-day)` verdict/outcome samples against baselines, with
transaction costs and a walk-forward out-of-sample protocol.

**Gate semantics (PLAN §5 gate A, verbatim):** the gate is that **the report
exists and is reproducible, NOT that Ichor wins.** The module therefore
reports beat / no-beat **honestly** (doctrine #11 calibrated honesty) and
fabricates no win.

**Scope of slice-1 (this ADR):** the pure-core only — dataclasses, metric
functions (directional hit-rate, win-rate, total/mean return, Brier
calibration of conviction), baselines (`always_long` = the buy-and-hold
analog for a daily-reset window strategy + classic single-entry
buy-and-hold scalar + causal `persistence`), the walk-forward split helper,
and the `evaluate_*` aggregators producing a frozen `BenchmarkReport`.
The CLI that joins `session_card_audit` verdicts with realised NY-window
returns from Polygon intraday and writes the report is **slice-2** (it needs
production realised data; deferred to a deploy+witness checkpoint).

**Doctrine alignment:**

- **ADR-017:** the module scores DIRECTION + CONVICTION only. It maps a
  directional read to a hypothetical signed window return **for measurement**,
  never to an order. The report's `honest_verdict` prose is regex-guarded
  against BUY/SELL/TP/SL (mirror of `_FORBIDDEN_VERDICT_TOKENS_RE`).
- **ADR-009 (Voie D):** zero LLM call, zero network, zero spend — pure
  arithmetic over a dataset.
- **ADR-022 (cap-95):** Brier reads `conviction_pct` on the 0..95 scale and
  treats it as the probability the directional read is correct.
- **Anti-leakage by design:** baselines are causal by construction
  (`persistence` uses the prior session only; `always_long` uses none),
  so the walk-forward out-of-sample evaluation cannot leak future data.

## Consequences

- **+** Chantier A's falsifiable gate becomes reachable: a reproducible report
  that states, with costs included, whether Ichor's verdict beats passive and
  naive baselines out-of-sample.
- **+** Unblocks the honest pursuit of Chantier B (learning loop) and C
  (dimension voting), which the PLAN gates behind A.
- **+** Pure-core is fully unit-testable with synthetic fixtures (no DB),
  verified at runtime via `uv run pytest` — real execution, not syntax.
- **−** Slice-1 does not yet produce a report on real data; the headline
  beat/no-beat number waits on slice-2 (CLI + production realised data) and a
  deploy+witness checkpoint.
- **Risk:** the realised-outcome history is young (verdicts began ~r161, late
  May 2026). Slice-2 must report `n_sessions` honestly and refuse to over-claim
  a verdict on a thin window (the report carries `n_sessions`; a small-N report
  is a valid, honest "insufficient out-of-sample history yet").

## Gate (pass/fail, falsifiable)

slice-1: `benchmark_gate.py` pure-core exists; its metrics and baselines are
proven correct against hand-computed fixtures; `uv run pytest` green; ruff +
mypy clean. (Met by this slice.)

slice-2 (future): the CLI emits a reproducible report over real walk-forward
sessions, costs included — beating baselines or honestly reporting it does not.
