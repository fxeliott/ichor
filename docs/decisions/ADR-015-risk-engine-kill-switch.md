# ADR-015 — Risk engine + kill switch design

- **Date** : 2026-05-03
- **Status** : Accepted
- **Decider** : autonomous BLOC C2 (Eliot validated v2 plan)

## Context

Phase 1 brings paper trading. Before any signal can produce a paper
order — let alone a real one in the eventual escalation — every trade
intent must pass through a single, audited gate that enforces :

1. **Position sizing** bounded by a hard cap (no full Kelly, no
   "I felt like 50%").
2. **Per-trade stop** to bound a single position's loss.
3. **Daily drawdown stop** to halt the system if the day goes south.
4. **Trade-frequency cap** to prevent runaway loops.
5. **Kill switch** — single-touch emergency halt visible to operators
   and tooling.

These rules exist to prevent the system from doing something stupid in
both paper (cosmetic damage) and live (real damage) modes.

## Decision

A new package `packages/risk/` with three concerns separated :

| File | Concern |
|---|---|
| `config.py` | `RiskConfig` frozen dataclass — knobs with conservative defaults |
| `kill_switch.py` | `KillSwitch` — file-flag + env-var trip detection, in-process trip-lock |
| `engine.py` | `RiskEngine.evaluate(intent, snapshot) → RiskDecision` |

### `RiskConfig` defaults

| Parameter | Default | Rationale |
|---|---|---|
| `kelly_fraction_cap` | 0.10 | Never risk more than 10 % equity per trade |
| `full_kelly_multiplier` | 0.25 | Quarter-Kelly — the industry standard ; full Kelly is famously too aggressive |
| `per_trade_stop_pct` | 0.02 | 2 % per-position stop ; conservative |
| `daily_drawdown_stop_pct` | 0.05 | Halt new orders at 5 % daily DD ; if the day is bad, sit on hands |
| `max_trades_per_day` | 50 | Sanity cap above what daily-bar models can plausibly need |
| `require_kill_switch_check` | True | Engine refuses to run without a KillSwitch attached |

### Order of checks (short-circuit on first refusal)

1. Kill switch (instant halt)
2. Asset sanity (intent.asset must match snapshot.asset)
3. Daily DD stop
4. Trade frequency cap
5. Sizing (Kelly cap + min size)

### Kill switch trip mechanisms (OR'd)

1. **File flag** : `/etc/ichor/KILL_SWITCH` (path overridable). Operator
   `touch`es the file from any shell to halt without code deploy.
2. **Env var** : `ICHOR_KILL_SWITCH=1`. Useful for systemd units.

### Trip is one-way per process

Once the switch trips in a process, `is_tripped()` keeps returning
True even if the file is removed and the env unset. **Operator must
restart the process.** This is deliberate — we don't want a trip to
silently un-trip itself between two evaluate() calls because the
file got recreated by mistake or because of caching.

## Alternatives considered

- **Inline risk checks in the runner** (one big function in
  `runner.py`) : kills auditability + makes it impossible to attach
  the same gate to a future live broker. Rejected.
- **Cancellable kill switch** (un-trip via API call) : too easy to
  un-trip by mistake or by an attacker. Rejected.
- **No env-var fallback, file only** : env var is needed inside
  systemd units that may run in containers without writable
  filesystems. Kept both.
- **Pluggable sizing strategy** (volatility-targeting, fixed-fractional,
  Kelly) : real benefit but premature for Phase 1 ; Kelly with cap is
  fine until live trading discussions re-open the choice.
- **Position-aware stops** (ATR-based, trailing) : same answer ; bring
  in when needed.

## Consequences

Positive :

- Single audit point. Every order goes through `RiskEngine.evaluate`,
  so adding a check (e.g. correlation cap across assets) is one place
  to change.
- Stateless engine. Caller owns the snapshot, so unit tests are trivial
  and the same engine plugs into live + paper + backtest.
- Kill switch is BOTH operator-friendly (touch a file) and
  CI/automation-friendly (env var).
- Hard caps mean a buggy upstream model can't size a single trade past
  10 % of equity even if it has 100 % conviction.

Negative :

- Stateless = caller must remember to compute `equity_high_today` +
  reset trades_today at midnight. Mitigated by helper functions in
  `packages/trading/` (BLOC C3).
- In-process trip lock means a paper script that handles its own
  errors might keep limping ; intentional.
- Kelly cap of 10 % may be too aggressive for real money — ADR-016
  forces tighter when escalating.

## Verification

28 unit tests in `packages/risk/tests/test_risk.py` :
- 4 kill-switch state tests (clear, file trip, env trip, in-process lock)
- 5 truthy + 5 falsy env-value parametrized tests
- 3 Kelly math tests (no edge, with edge, zero payoff)
- 11 risk engine tests covering each refusal path + the happy path
- Mid-session trip-during-evaluate scenario

All 28/28 green.

## RUNBOOK

[RUNBOOK-012](../runbooks/RUNBOOK-012-kill-switch-trip.md) covers :
- How to manually trip
- Diagnosis steps when an automated trip fires
- Recovery procedure (investigate → clear flag → restart)

## Trading rules respected

- Hard cap on position size (10 % default, 25 % quarter-Kelly).
- Daily drawdown stop wired in.
- Kill switch tested end-to-end (file + env, mid-session, trip-lock).
- ADR-016 (paper-only contract) requires `kill_switch.assert_clear()`
  before any order generation in the trading layer.
