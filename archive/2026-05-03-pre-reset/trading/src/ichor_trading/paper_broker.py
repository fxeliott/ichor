"""Paper broker — in-memory order matching with fee/slippage model.

Every order submitted MUST pass `RiskEngine.evaluate` first ; the broker
itself is dumb and just executes. Risk is enforced upstream.

PAPER ONLY. No network, no live broker SDK. To go live, ADR-016 requires
a separate package + explicit Eliot ack.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import structlog

from .types import Order, OrderSide, Position, Trade

log = structlog.get_logger(__name__)


class PaperBrokerError(RuntimeError):
    """Raised when the broker cannot execute (e.g. unknown asset price)."""


# Caller supplies a price oracle that returns the current reference price
# for any asset. Allows paper backtests + paper live to share the same broker.
PriceOracle = Callable[[str], float]


@dataclass
class PaperBroker:
    """In-memory paper trading broker.

    State :
      - `positions` : asset → Position
      - `trades` : audit log of every fill
      - `cash` : free cash balance
    """

    initial_cash: float = 10_000.0
    fee_bps_per_side: float = 1.0
    """Fee + slippage combined, per side, in basis points."""

    cash: float = field(init=False)
    positions: dict[str, Position] = field(default_factory=dict)
    trades: list[Trade] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.cash = self.initial_cash

    def submit(self, order: Order, price_oracle: PriceOracle) -> Trade:
        """Submit an order. Returns a Trade record on fill."""
        assert order.paper is True, "ADR-016: only paper orders allowed"

        try:
            ref_price = price_oracle(order.asset)
        except Exception as e:
            raise PaperBrokerError(f"price_oracle failed for {order.asset}: {e}") from e

        if ref_price <= 0:
            raise PaperBrokerError(f"non-positive ref price for {order.asset}: {ref_price}")

        # Limit-order semantics : only fill if marketable.
        if order.order_type == "limit":
            assert order.limit_price is not None
            marketable = (
                (order.side == "buy" and ref_price <= order.limit_price)
                or (order.side == "sell" and ref_price >= order.limit_price)
            )
            if not marketable:
                raise PaperBrokerError(
                    f"limit not marketable: side={order.side} ref={ref_price} "
                    f"limit={order.limit_price}"
                )

        fill_price = self._apply_fee_slippage(order.side, ref_price)
        notional = order.quantity * fill_price
        fee_paid = abs(notional) * (self.fee_bps_per_side / 10_000.0)

        # Update position
        pos = self.positions.setdefault(order.asset, Position(asset=order.asset))
        realized = pos.update_on_fill(order.quantity, fill_price, order.side)

        # Cash impact : buy reduces, sell increases ; fee always reduces.
        if order.side == "buy":
            self.cash -= notional
        else:
            self.cash += notional
        self.cash -= fee_paid

        trade = Trade(
            order_id=order.id,
            asset=order.asset,
            side=order.side,
            quantity=order.quantity,
            fill_price=fill_price,
            fee_paid=fee_paid,
            realized_pnl_at_fill=realized,
        )
        self.trades.append(trade)
        log.info(
            "paper_broker.fill",
            order_id=order.id,
            asset=order.asset,
            side=order.side,
            qty=order.quantity,
            fill=fill_price,
            fee=round(fee_paid, 6),
            realized=round(realized, 4),
            cash_after=round(self.cash, 2),
            position_after=round(pos.quantity, 6),
        )
        return trade

    def _apply_fee_slippage(self, side: OrderSide, ref: float) -> float:
        """Buy fills above ref, sell below — by `fee_bps_per_side`."""
        sign = 1.0 if side == "buy" else -1.0
        return ref * (1.0 + sign * self.fee_bps_per_side / 10_000.0)

    # ---------------- helpers ----------------

    def get_position(self, asset: str) -> Position:
        return self.positions.setdefault(asset, Position(asset=asset))

    def equity(self, price_oracle: PriceOracle) -> float:
        """Total equity = cash + sum(position * mark)."""
        total = self.cash
        for asset, pos in self.positions.items():
            if pos.is_flat():
                continue
            try:
                mark = price_oracle(asset)
            except Exception:
                continue
            total += pos.quantity * mark
        return total
