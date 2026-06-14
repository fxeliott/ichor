# SESSION LOG — 2026-06-14 · S06 · C-5 SHIPPED (dormant) + rates/volume/runner dispositions

> Model: Opus 4.8 (interactive). Re-fire #17 — owner: "active volume ; go rates ; go
> C-5 ; démarre le runner ; continue." Honest orchestration grounded in three
> fresh-context subagent maps (C-5 mechanism, rates primitive, rates web-doctrine) +
> RUNBOOK-014. Net: **C-5 BUILT + deployed DORMANT (flag-OFF, byte-identical)**; rates
> DEFERRED with reasoning (a naive build would be a fake edge); volume activation
> SEQUENCED after C-5; the Win11 runner is the one binding gate for live witnessing and
> is an owner action (denied to this session).

## The binding reality (verified this turn)

- **Win11 card-generation runner is DOWN / unreachable** (`claude_runner_reachable:
null`; latest `session_card_audit` = 2026-06-12). Probing/starting it from this
  session is **denied by the environment** (PowerShell + Bash local commands refused) →
  owner restart required (RUNBOOK-014, steps below).
- **Consequence**: no fresh cards ⇒ enabling any flag has no observable effect, and
  nothing is runtime-witnessable. Prediction features are validated by **sustained
  witness over real NY sessions** (multi-day) — not compressible into one turn (prompt
  ⑥ "seule la preuve par l'exécution réelle compte").

## Disposition of the five commands

### 1. "démarre le runner" → OWNER ACTION (guided; denied to me)

PowerShell on the Win11 box (RUNBOOK-014 §Recovery):

```powershell
curl http://127.0.0.1:8766/healthz                               # already up?
& "D:\Ichor\scripts\windows\start-claude-runner-standalone.bat"  # (re)launch
Start-Sleep 3 ; curl http://127.0.0.1:8766/healthz               # expect {"status":"ok"}
```

Then Hetzner `/healthz` shows `claude_runner_reachable: true`; the next pre-session cron
(06/12/17/22h Paris) generates fresh cards. Optional durability: register
`IchorRunnerWatchdog` (RUNBOOK-014 §Self-heal, 5-min, no admin).

### 2. "go C-5" → BUILT + DEPLOYED DORMANT (flag-OFF byte-identical)

The OOS conviction calibrator is now WIRED into the live verdict behind
`conviction_calibrator_oos_enabled` (fail-closed OFF). Justified by the existing witness
(calibration conclusively beats raw OOS on 368 real cards, Brier ≈ 0.30 → 0.25;
`SESSION_LOG_2026-06-14-s06-chantier-b-witness-real-result.md:19-54`).

Shipped (all flag-OFF → no behaviour change until enabled):

- `conviction_calibration.py`: pure `select_and_fit_live_calibrator(pairs)` — chronological
  split → `select_calibrator_oos` → if a family STRICTLY beats identity OOS on a
  conclusive (≥30) held-out split, REFIT the winner on the FULL history and return it,
  else `None` (keep raw). Self-adapts (re-decides + re-fits each call) so it tolerates a
  newly-activated dimension. `calibrate_conviction` added to the `SupportsApply` protocol.
- `session_verdict_builder.py`: async `_load_reconciled_p_up_y(session)` (pooled
  `(p_up,y)`, READ-ONLY, capped 5000 most-recent for durability) + the gated apply in
  `build_session_verdict` AFTER `_derive_direction_and_conviction` (only when
  `direction != "neutral"` AND the flag is on), `_bias = up→long / down→short`.
- `tests/test_conviction_calibrator_live.py`: 8 tests of the pure brain (honesty gate,
  shrink on over-confidence, ADR-017 no-flip / ADR-022 cap, determinism).

Invariants: ADR-017 (calibration only moves MAGNITUDE; a cross-side calibration collapses
conviction to 0, never flips), ADR-022 (cap-95), ADR-009 (pure brain; the only I/O is the
read-only pooled fetch, gated). Both golden harnesses (fuser 179 + card 32) stay
**byte-identical** structurally (they never exercise the async gate). Full suite **3680
passed / 36 skip**, ruff + mypy clean (no new errors), fresh adversarial verifier
**DÉCISION OK** (flag-OFF byte-identity proven, mapping forward-correct, honesty gate
correct, protocol-change safe).

**NOT enabled.** Enabling is the owner's product call AND requires the runner up +
**sustained re-witness** (the displayed conviction will honestly collapse toward ~50 % on
most days — that is the truth the data shows). Known minor (verifier): the "refit-on-all"
claim is correct in code but not pinned by a discriminating test (a benign coverage gap).

### 3. "active le volume" → SEQUENCED after C-5 (activating now is wrong + moot)

- **Moot now**: runner down → no fresh cards → flag flip has no effect.
- **Wrong order**: volume is non-directional and only RAISES conviction
  (`uncertainty_credit` ≥ 0); the witness showed raw conviction is OVER-confident, so
  activating volume BEFORE C-5 makes it MORE over-confident. Correct sequence: enable
  C-5 → witness → enable volume → re-witness (the on-the-fly C-5 fitter self-adapts to
  the new distribution).

### 4. "go rates" → DEFERRED with reasoning (a naive build would be a FAKE edge)

A directional rates DimensionVote on the **currently collected** data is **unsound**:

- Foreign 10Y series are **MONTHLY** (OECD MEI `IRLTLT01*M156N`; `data_pool.py:184-191`).
  A "Δ5-day change" of a monthly series ≈ 0 most days → the "differential change"
  collapses to **US-10Y momentum alone, mislabelled** — a hallucinated signal (violates
  "que du vrai").
- Web doctrine (Fed / St. Louis Fed / CFA, primary): the FX driver is **Δ(2Y)**
  front-end, NOT the 10Y (term-premium contaminated); `DGS2` + foreign 2Y daily are NOT
  collected. UIP/carry is empirically weak (R² ≈ 0.06-0.32), regime-dependent (risk-off
  flips JPY/CHF; a fiscal/term-premium yield rise can FLIP the sign). The subagent's
  `USD_JPY = -1` polarity CONTRADICTS primary sources (USD/JPY rises on US-yield strength).
- **Correct future path**: collect daily `DGS2` + foreign 2Y, signal = Δ(2Y differential)
  real-yield-decomposed, regime-gated; per-pair signs EUR/GBP/AUD = −1 / USD_JPY,USD_CAD
  = +1 on USD strength (risk-regime-gated). Until that data exists, refused.

## NEXT (fresh session, runner up)

1. Owner restarts the runner → fresh cards generate.
2. Enable `conviction_calibrator_oos_enabled` (DB flag) → deploy is already live →
   **sustained re-witness** (days) → confirm the displayed conviction is honest.
3. Enable `volume_dimension_vote_enabled` → re-witness on the new distribution.
4. Rates: a data-collection slice (daily `DGS2` + foreign 2Y + regime inputs) FIRST,
   then the sound Δ(2Y) directional producer.

Shipped on `main` this turn: the C-5 wiring (PR — see below). ssh ichor-hetzner =
root@prod; deploy = `gh workflow run deploy.yml --ref main -f tags=api` (push-deploy full
still broken on the observability docker pool — known, RUNBOOK material).
