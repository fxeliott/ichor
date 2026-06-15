# ADR-119 — Conviction-calibration out-of-sample witness (Chantier B, slice-4)

- **Status:** Accepted — 2026-06-13 · **UPDATE 2026-06-15** : the OOS calibrator is now WIRED into the live verdict behind `conviction_calibrator_oos_enabled` (fail-closed OFF) via S06 C-5 (`session_verdict_builder.py:729-751` + `conviction_calibration.select_and_fit_live_calibrator`). The "NOT live-wired" qualifier below describes the slice-4 (measurement-only) state, not current code.
- **Deciders:** owner (delegated "fais tout, décide seul"), engine (Opus 4.8)
- **Supersedes:** none
- **Extends:** ADR-117 (isotonic), ADR-118 (regularised isotonic + Platt + OOS selector)
- **Related:** ADR-116 (benchmark witness, IC95 honesty guard) · ADR-009 (Voie D) ·
  `services/conviction_calibration.select_calibrator_oos` ·
  `services/brier_optimizer.derive_realized_outcome` · `routers/calibration.py`

## Context

ADR-118 added the calibration _candidates_ (regularised isotonic, Platt) and a
cross-family OOS _selector_ — but nothing actually RAN them on the realised
track-record. The verdict's conviction was measured as poorly calibrated
(ADR-116, OOS Brier 0.38), the slice-1 fix overfit (ADR-117), and slice-2/3
proposed better-conditioned candidates — yet the decisive question remained
unanswered with data: **does any of these candidates beat the raw conviction
OUT-OF-SAMPLE, and is the sample large enough to trust the answer?**

The reconciled outcomes already exist in `session_card_audit`
(`brier_contribution` filled nightly by `cli/reconcile_outcomes`), and
`brier_optimizer.derive_realized_outcome` already reverse-engineers the binary
`y` from a card. Nothing combined them into a conviction-calibration witness.
(`routers/calibration.py` surfaces RAW reliability; `brier_optimizer_v2` does an
OOS-gated loop but for FACTOR weights, not the conviction. No duplicate.)

## Decision

Add `services/calibration_witness.py` (pure-core, Voie-D) + a **read-only** CLI
`cli/run_calibration_witness.py`.

- `run_calibration_witness(samples)` takes time-ordered `(asset, p_up, y)`,
  groups per asset plus a `POOLED` series, and for each does a **chronological**
  train/test split (fit on the earliest cards, score on the later ones — a real
  forward test, no leakage) through `select_calibrator_oos`. Each row reports
  `n_train`, `n_test`, raw vs selected Brier, whether the selection beats raw
  OOS, and a `conclusive` flag (test split ≥ 30 cards — the ADR-116 thin-sample
  honesty guard).
- `format_witness_markdown` renders a reproducible table and an HONEST verdict:
  it claims a wiring candidate **only** when a calibrator beats raw on a
  non-thin OOS split; otherwise it states plainly that the track-record is still
  too short to trust a correction (`any_conclusive_improvement`).
- The CLI rebuilds `(p_up, y)` from the persisted `(bias_direction,
conviction_pct, brier_contribution)` via the canonical
  `brier.conviction_to_p_up` + `brier_optimizer.derive_realized_outcome`,
  ordered oldest-first, and **writes nothing** (SELECT only).

**Scope: measurement only. NO live wiring.** The verdict still emits its raw
conviction. Wiring a winning calibrator stays a later GATED step (deploy +
sustained re-witness). Same discipline as ADR-117/118.

## Consequences

- **+** The learning loop is now _falsifiable end-to-end_: a single command
  answers "does re-calibration help OOS, and is it conclusive?" — and it is
  honest by construction (identity always a candidate; thin splits flagged).
- **+** It improves automatically as cards reconcile: re-run monthly and it will
  detect a real, conclusive winner the moment the history is long enough.
- **+** Pure-core fully unit-tested (12 tests); CLI thin, reuses canonical
  primitives, read-only; ruff + mypy clean; zero spend.
- **−** A real result needs prod data (read-only DB access); on the current thin
  history the honest expected output is "inconclusive — keep raw". That is the
  truthful answer, not a failure.
- **Risk:** a single chronological split on a short series is itself noisy;
  walk-forward / k-fold aggregation is the future hardening (ADR-118 Risk).

## Gate (pass/fail, falsifiable)

- slice-4 code: chronological split never leaks test into train; identity is
  always a candidate; a thin test split is flagged inconclusive; the markdown
  verdict only claims an edge on a conclusive improvement; CLI is read-only and
  reuses the canonical `(p_up, y)` derivation; ruff + mypy + 12 tests green.
  **(Met by this slice.)**
- real witness (owner/data-prod): run the CLI (or a read-only pull) against
  prod, report N honestly. Live wiring only after a sustained, conclusive OOS
  win + deploy + witness.
