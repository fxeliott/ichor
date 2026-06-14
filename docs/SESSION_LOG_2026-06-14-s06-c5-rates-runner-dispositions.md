# SESSION LOG — 2026-06-14 · S06 · C-5 / rates / volume-activation / runner — analysis + dispositions

> Model: Opus 4.8 (interactive). Re-fire #17 — owner: "active volume ; go rates ; go
> C-5 ; démarre le runner ; continue." This turn is the HONEST orchestration of those
> five, grounded in three fresh-context subagent maps (C-5 mechanism, rates primitive,
> rates web-doctrine) + RUNBOOK-014. Net: one binding gate (the Win11 runner) blocks
> all live witnessing; two of the five are deferred WITH REASONING (not skipped); C-5
> is designed + justified, ready for a fresh+runner-up build.

## The binding reality (verified this turn)

- **Win11 card-generation runner is DOWN / unreachable** (`claude_runner_reachable:
null`; latest `session_card_audit` = 2026-06-12). Probing/starting it from this
  session is **denied by the environment** (PowerShell + Bash local-network/process
  commands refused) → owner must restart it (RUNBOOK-014, steps below).
- **Consequence**: with no fresh cards, NOTHING (C-5, volume, rates) produces any
  observable effect, and nothing can be runtime-witnessed. Prediction features are
  validated by **sustained witness over real NY sessions** (multi-day) — not
  compressible into one turn. Honest per prompt ⑥ ("seule la preuve par l'exécution
  réelle compte").

## Disposition of the five commands

### 1. "démarre le runner" → OWNER ACTION (guided; denied to me)

Quickest path (RUNBOOK-014 §Recovery), copy-paste in PowerShell on the Win11 box:

```powershell
curl http://127.0.0.1:8766/healthz                      # is it already up?
& "D:\Ichor\scripts\windows\start-claude-runner-standalone.bat"   # (re)launch
Start-Sleep 3 ; curl http://127.0.0.1:8766/healthz      # expect {"status":"ok",...}
```

Then on Hetzner: `curl .../healthz` should show `claude_runner_reachable: true`, and the
next pre-session cron (06/12/17/22h Paris) generates fresh cards. Optional durability:
register `IchorRunnerWatchdog` (RUNBOOK-014 §Self-heal, 5-min self-heal, no admin).

### 2. "go C-5" → JUSTIFIED + DESIGNED; build deferred to fresh+runner-up (witnessability)

**Justification (already verified, not re-needed)**: the calibration conclusively beats
raw OOS on 368 real directional cards (Brier ≈ 0.30 → 0.25), robust across splits
(`SESSION_LOG_2026-06-14-s06-chantier-b-witness-real-result.md:19-54`). C-5 is an
HONESTY fix (kills the "85 % that is really ~50 %"), not a manufactured edge.

**Complete wiring design (ready to execute)** — mechanism mapped at file:line:

- `select_calibrator_oos(train, test)` → `CalibratorSelection` (label + OOS Brier +
  `improved`); the fit is **FROZEN/on-the-fly** (no DB persistence table)
  (`conviction_calibration.py`). To APPLY, fit the winning family
  (`ConvictionCalibrator` isotonic / `PlattCalibrator`) and call
  `.calibrate_conviction(bias, conviction_pct)` (chain: conviction → p_up → calibrated
  p_up → conviction; ADR-017 no-flip + ADR-022 cap-95 already enforced inside).
- `_derive_direction_and_conviction` (`session_verdict_builder.py:154`) is **sync, no
  session** → the calibration must live in the async `build_session_verdict` (it has
  `session`), applied to `conviction_pct` AFTER the `_derive(...)` call, mirroring the
  dimension-votes gate (`:659-671`).
- New service `async fit_live_conviction_calibrator(session) -> SupportsApply | None`:
  reuse `_load_samples` query (`run_calibration_witness.py:39-68`) → `select_calibrator_oos`
  on a chronological split → if `improved AND conclusive (≥30)`, fit the winner on all
  samples and return it; else `None` (→ identity). Self-adapts (re-fits each run) so it
  tolerates new dimensions (volume) being activated.
- Flag `CONVICTION_CALIBRATOR_FLAG = "conviction_calibrator_oos_enabled"` (fail-closed
  OFF → byte-identical: both golden harnesses, fuser 179 + card 32, pass because the
  pure helpers are untouched and the gate is skipped). Unit-test the flag-ON fit/apply
  with synthetic `(p_up, y)`; fresh-verify; deploy dormant; enable + **sustained
  re-witness** once the runner is up.

**Why deferred, not shipped this turn**: it is the APEX hot path (the conviction the
trader sees), it is **un-witnessable** while the runner is down (violates the
"test the real execution" bar), and it deserves the project's "delicate slice → fresh
context" treatment. Shipping a new async fitter on the apex path deep in a long session,
for a feature that can't be enabled/witnessed, is the wrong trade (process > outcome).

### 3. "active le volume" → SEQUENCED after C-5 (activating now is wrong + moot)

- **Moot now**: runner down → no fresh cards → flag flip has no effect.
- **Wrong order**: volume is non-directional and only **raises** conviction
  (`uncertainty_credit` ≥ 0). The witness showed raw conviction is **over-confident**;
  activating volume BEFORE C-5 makes it MORE over-confident — the opposite of the goal.
  Correct sequence: enable C-5 → witness → then enable volume → re-witness on the new
  distribution. (The on-the-fly C-5 fitter self-adapts, so volume-then-recalibrate is
  safe once C-5 is live.)

### 4. "go rates" → DEFERRED with reasoning (the naive build would be a FAKE edge)

A directional rates DimensionVote on the **currently collected** data is **unsound**:

- The foreign 10Y series are **MONTHLY** (OECD MEI `IRLTLT01*M156N`, ~30-120d lag;
  `data_pool.py:184-191`). A "Δ5-day change" of a monthly series is ≈ 0 most days, so
  the "differential change" collapses to **US-10Y momentum alone, mislabelled as a rate
  differential** — a hallucinated signal. Violates "que du vrai, zéro approximation".
- Web doctrine (Fed / St. Louis Fed / CFA, primary): the FX-relevant signal is the
  **Δ(2Y)** front-end (policy expectations), NOT the 10Y (contaminated by term premium);
  `DGS2` + foreign 2Y daily are **not collected**. UIP/carry is empirically weak
  (R² ≈ 0.06-0.32), regime-dependent (risk-off flips JPY/CHF; a fiscal/term-premium
  yield rise can FLIP the sign). The subagent's proposed `USD_JPY = -1` polarity
  CONTRADICTS the primary sources (USD/JPY rises on US-yield strength — 2022 >150 case).
- **Correct path (a proper future slice)**: (a) collect daily `DGS2` + foreign 2Y
  (FRED), (b) signal = Δ(2Y differential) over a rolling window, decomposed real-yield
  vs breakeven, (c) regime gating (damp/abstain in risk-off + fiscal-stress), (d)
  per-pair signs EUR/GBP/AUD = −1 on USD strength, USD_JPY/USD_CAD = +1 (the
  carry-standard signs, with JPY/AUD/CAD risk-regime-gated). Until that data + gating
  exist, a rates vote would ship a poorly-founded directional tilt — refused.

## NEXT (fresh session, runner up)

1. Owner restarts the runner (above) → fresh cards generate.
2. Build C-5 per the design above → deploy dormant → enable flag → **sustained
   re-witness** (days) → confirm the displayed conviction is honest.
3. Enable volume → re-witness on the new distribution.
4. Rates: first a data-collection slice (daily `DGS2` + foreign 2Y + regime inputs),
   then the sound Δ(2Y) directional producer.

main = a63aede (unchanged this turn — analysis + dispositions only; no code shipped, by
design). ssh ichor-hetzner = root@prod; deploy = `gh workflow run deploy.yml --ref main
-f tags=api` (push-deploy full still broken on the observability docker pool — known).
