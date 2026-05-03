"""RiskEngine — the gate every order goes through before any broker.

`RiskEngine.evaluate(intent)` returns a `RiskDecision`:

  - `allowed=True, sized_qty=X` → caller may submit X units
  - `allowed=False, sized_qty=0, reason='...'` → refuse

Stateless across processes ; takes a `RiskSnapshot` as input so the
caller manages historical state (paper P&L, trade count today, equity).

Order of checks (short-circuit on first refusal) :
  1. Kill switch — instant halt
  2. Daily DD stop
  3. Trade-frequency cap
  4. Sizing (Kelly cap + min size)
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from .config import RiskConfig
from .kill_switch import KillSwitch, KillSwitchTripped

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class RiskSnapshot:
    """Caller-supplied state used by RiskEngine to compute decisions.

    Realized DD is computed from `equity` + `equity_high_today`.
    """

    equity: float
    """Current account equity (paper)."""

    equity_high_today: float
    """High-water mark since UTC midnight of today."""

    trades_today: int
    """Count of trades since UTC midnight."""

    asset: str
    """Target asset for the proposed trade."""

    reference_price: float
    """Mark price used to compute notional from sized_qty."""


@dataclass(frozen=True)
class TradeIntent:
    """Upstream proposal."""

    asset: str
    direction: str  # "long" | "short"
    probability: float
    """Calibrated probability the directional bet wins (in [0, 1])."""

    avg_win_pct: float = 0.005
    """Expected win as fraction of entry (e.g. 0.005 = 50 bps).
    Used in Kelly. Default = 50 bps for daily-bar FX moves."""

    avg_loss_pct: float = 0.005
    """Expected loss as fraction of entry, positive number."""


@dataclass(frozen=True)
class RiskDecision:
    """Result of `RiskEngine.evaluate`."""

    allowed: bool
    sized_qty: float
    """Signed quantity. Positive = long, negative = short. 0 if refused."""

    reason: str
    """Human-readable explanation. Always populated."""

    sizing_fraction: float = 0.0
    """The fraction of equity this position represents at entry. For audit."""


def _full_kelly(p: float, win: float, loss: float) -> float:
    """Standard Kelly criterion for binary outcome.

    f* = (p * b - (1-p)) / b   where b = win/loss ratio.
    Returns 0 if b ≤ 0 or p ≤ 0.5 (no edge).
    """
    if win <= 0 or loss <= 0:
        return 0.0
    b = win / loss
    edge = p * b - (1 - p)
    if edge <= 0:
        return 0.0
    return edge / b


@dataclass
class RiskEngine:
    """The single gate. Stateless — caller passes a RiskSnapshot per call."""

    config: RiskConfig
    kill_switch: KillSwitch | None = None

    def evaluate(self, intent: TradeIntent, snapshot: RiskSnapshot) -> RiskDecision:
        # -------- 1. kill switch --------
        if self.config.require_kill_switch_check and self.kill_switch is None:
            return RiskDecision(
                allowed=False, sized_qty=0.0,
                reason="kill_switch_not_configured",
            )
        if self.kill_switch is not None:
            try:
                self.kill_switch.assert_clear()
            except KillSwitchTripped as e:
                return RiskDecision(allowed=False, sized_qty=0.0, reason=str(e))

        # -------- 2. asset sanity --------
        if intent.asset != snapshot.asset:
            return RiskDecision(
                allowed=False, sized_qty=0.0,
                reason=f"asset_mismatch intent={intent.asset} snapshot={snapshot.asset}",
            )

        # -------- 3. daily DD stop --------
        if snapshot.equity_high_today > 0:
            dd = (snapshot.equity_high_today - snapshot.equity) / snapshot.equity_high_today
            if dd >= self.config.daily_drawdown_stop_pct:
                log.warning(
                    "risk.daily_dd_stop",
                    asset=intent.asset,
                    dd=round(dd, 4),
                    threshold=self.config.daily_drawdown_stop_pct,
                )
                return RiskDecision(
                    allowed=False, sized_qty=0.0,
                    reason=f"daily_dd_stop dd={dd:.2%} cap={self.config.daily_drawdown_stop_pct:.2%}",
                )

        # -------- 4. trade frequency --------
        if snapshot.trades_today >= self.config.max_trades_per_day:
            return RiskDecision(
                allowed=False, sized_qty=0.0,
                reason=f"max_trades_per_day reached ({snapshot.trades_today})",
            )

        # -------- 5. sizing --------
        full_k = _full_kelly(
            intent.probability, intent.avg_win_pct, intent.avg_loss_pct,
        )
        scaled_k = full_k * self.config.full_kelly_multiplier
        capped_k = min(scaled_k, self.config.kelly_fraction_cap)

        if capped_k <= 0:
            return RiskDecision(
                allowed=False, sized_qty=0.0,
                reason=f"no_edge full_kelly={full_k:.4f}",
            )

        notional = capped_k * snapshot.equity
        qty = notional / snapshot.reference_price
        if intent.direction == "short":
            qty = -qty

        if abs(qty) < self.config.min_position_size:
            return RiskDecision(
                allowed=False, sized_qty=0.0,
                reason=f"below_min_position_size qty={qty:.6f}",
            )

        return RiskDecision(
            allowed=True,
            sized_qty=qty,
            reason="ok",
            sizing_fraction=capped_k,
        )
