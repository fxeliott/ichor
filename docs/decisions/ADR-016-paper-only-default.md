# ADR-016 — Paper-only by default ; live trading requires explicit escalation

- **Date** : 2026-05-03
- **Status** : Accepted (CONTRACTUAL — see "How to escalate" before any change)
- **Decider** : autonomous BLOC C3 (Eliot validated v2 plan)

## Context

Phase 1 introduces a trading layer (`packages/trading/`). Even in
paper mode, the surface looks operationally identical to live trading:
Order objects, fills, positions, P&L, equity. The risk of "we
accidentally went live" exists from day 1 :

- A future contributor (or future-Eliot) plugs in OANDA / Alpaca / IBKR
  because "the broker interface looks compatible".
- An LLM agent in the loop helpfully implements live order routing
  because the ADR didn't forbid it.
- A quick test in dev accidentally points at a real account.

The user's stated rule is explicit : **paper-only by default, capital 0,
kill switch tested end-to-end before any live livrable**. This ADR
makes that rule structural, not aspirational.

## Decision

### Contract — Phase 0 + Phase 1 + Phase 2 (until amended)

1. **Every** Order, Position, Trade, and BacktestResult dataclass MUST
   carry `paper: bool = True`. The constructor MUST refuse `paper=False`
   via assertion. Frozen dataclasses (`@dataclass(frozen=True)`)
   prevent post-construction mutation.

2. **Every** broker class in `packages/trading/` MUST be paper. There
   is no live broker in this package and no abstract `Broker` interface
   that a live impl could satisfy.

3. **Every** order submission code path MUST call
   `RiskEngine.evaluate(...)` (which calls `KillSwitch.assert_clear()`)
   before reaching the broker. Tests for ADR-015 cover this.

4. **No package** in the monorepo may import `oandapyV20`, `alpaca-py`,
   `ib_insync`, `ccxt`, `polygon-api-client`, or any other live-broker
   SDK. Dependency audit
   ([`docs/audits/dependencies-2026-05-03.md`](../audits/dependencies-2026-05-03.md))
   verifies this. CI guard is open for Phase 1.

5. **Paper-only stamping** is part of the audit trail. Every Trade row
   eventually persisted to a future `paper_trades` table will carry
   the same `paper=True` field, mirroring the dataclass.

### How to escalate to live trading

The path is explicit and slow on purpose :

1. **Eliot writes a new ADR** (`ADR-NNN-go-live-<scope>.md`) that
   defines :
   - Which assets, which capital, which broker, which max DD per day,
     which max position size as fraction of equity.
   - The rollback plan : how to halt live trading in <60 s.
   - Independent verification that backtests + paper sim of the SAME
     strategy over ≥ 6 months show acceptable risk-adjusted returns.
2. **Eliot creates a new package** `packages/trading_live/` :
   - Imports nothing from `packages/trading/` (clean separation).
   - Implements its own `Order` / `Trade` types with `live=True`
     stamping (mirror of the paper invariant).
   - Wires its own `LiveBroker` against the chosen vendor SDK.
3. **The risk engine refuses to evaluate** a live intent unless a
   second human-acked env-var (`ICHOR_LIVE_ACK_<DATE>=1`) is present.
   This is a tripwire against silent re-deploy.
4. **A separate kill switch file** at `/etc/ichor/KILL_SWITCH_LIVE`
   defaults to PRESENT at install — operator must `rm` it once,
   intentionally, after reading the ADR.
5. **A separate observability dashboard** for live with end-of-day
   reconciliation against the broker statement.
6. **Mandatory weekly post-mortem** for the first month live.

This ADR cannot be amended to allow live trading without writing the
escalation ADR above.

## Alternatives considered

- **Just be careful** : "we'll never connect a live broker by accident".
  History of trading systems disagrees ; this is exactly how money
  gets lost.
- **Use a shared `Broker` interface that both paper and live impls
  satisfy** : convenience invites mistakes. Hard separation = no
  confusion.
- **Mark live with a dataclass field but allow it** : the field
  becomes a config flag people flip. Rejected — must be a separate
  type tree.
- **Use a feature flag instead of separate package** : flags get
  toggled. Packages don't get accidentally imported.

## Consequences

Positive :

- Live-trading mistakes require deliberate, multi-step action.
- Dataclass invariants + tests catch any code change that even
  attempts to set `paper=False`.
- Risk engine + kill switch (ADR-015) is the single audit point for
  every order regardless of which package generated it.
- Future Eliot reading this ADR has a clear escalation path with
  brakes built in.

Negative :

- Two packages to maintain when we eventually go live (paper +
  trading_live). Acceptable cost — the separation is the safety.
- Slightly more boilerplate at construction time (assertions). Cheap.
- If a contributor "forgets" the `paper=True` invariant in a new type,
  they lose the safety. Mitigated by tests + linting.

## Verification

- 25 unit tests in
  [`packages/trading/tests/test_trading.py`](../../packages/trading/tests/test_trading.py)
  including :
  - `test_order_paper_invariant` — frozen + always True
  - `test_order_constructor_refuses_paper_false`
  - `test_trade_paper_invariant`
  - All Position math + PaperBroker + P&L helpers
- `RiskEngine` requires `KillSwitch` by default
  ([ADR-015](ADR-015-risk-engine-kill-switch.md)) — every order goes
  through it.

## How to test the contract is alive

```python
import pytest
from ichor_trading import Order, Trade

# Construction with paper=False must raise
with pytest.raises(AssertionError):
    Order(asset="EUR_USD", side="buy", quantity=100, paper=False)

# Construction with paper=True (default) succeeds
o = Order(asset="EUR_USD", side="buy", quantity=100)
assert o.paper is True
```

## References

- [`packages/trading/`](../../packages/trading/) — paper layer
- [`packages/risk/`](../../packages/risk/) — gate every order goes through
- [`packages/backtest/`](../../packages/backtest/) — also stamped paper-only
- [ADR-015](ADR-015-risk-engine-kill-switch.md) — risk engine + kill switch
- [RUNBOOK-012](../runbooks/RUNBOOK-012-kill-switch-trip.md) — kill-switch
  trip recovery
