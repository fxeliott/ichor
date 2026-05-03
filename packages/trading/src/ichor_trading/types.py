"""Order, Position, Trade dataclasses.

PAPER ONLY. Every Order carries `paper=True` ; the field is set by the
constructor and there is no setter. Tests assert the invariant.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

OrderSide = Literal["buy", "sell"]
OrderType = Literal["market", "limit"]
OrderStatus = Literal["pending", "filled", "rejected", "cancelled"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Order:
    """An order intent. Frozen — once created, immutable."""

    asset: str
    side: OrderSide
    quantity: float
    order_type: OrderType = "market"
    limit_price: float | None = None
    """Required when order_type='limit'."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=_now)
    status: OrderStatus = "pending"

    paper: bool = True
    """ALWAYS True. ADR-016 contract."""

    notes: str = ""

    def __post_init__(self) -> None:
        assert self.quantity > 0, "Order.quantity must be > 0 (use side for direction)"
        if self.order_type == "limit":
            assert self.limit_price is not None, "limit order requires limit_price"
        # Defensive : never accept paper=False at construction
        assert self.paper is True, (
            "ADR-016: Order.paper must be True. Live trading requires a "
            "separate ichor_trading_live package not yet authorized."
        )


@dataclass
class Position:
    """Mutable per-asset state.

    Quantity is signed: positive long, negative short. `avg_entry` is
    the volume-weighted average entry price.
    """

    asset: str
    quantity: float = 0.0
    avg_entry: float = 0.0
    realized_pnl: float = 0.0
    paper: bool = True

    def is_flat(self) -> bool:
        return abs(self.quantity) < 1e-12

    def update_on_fill(
        self, fill_qty: float, fill_price: float, side: OrderSide
    ) -> float:
        """Update position state on a fill. Returns realized PnL (0 unless
        the fill closes / reduces the position)."""
        signed_qty = fill_qty if side == "buy" else -fill_qty
        new_qty = self.quantity + signed_qty
        realized = 0.0

        # If we cross or reduce the existing position, realize PnL on the
        # closed portion.
        if self.quantity != 0 and (
            (self.quantity > 0 and signed_qty < 0)
            or (self.quantity < 0 and signed_qty > 0)
        ):
            close_qty = min(abs(self.quantity), abs(signed_qty))
            # PnL on the closed portion
            if self.quantity > 0:
                # Long → close = sell at fill_price, vs avg_entry
                realized = close_qty * (fill_price - self.avg_entry)
            else:
                realized = close_qty * (self.avg_entry - fill_price)
            self.realized_pnl += realized

        # New average entry only relevant when we're growing the position
        # (or flipping side).
        if new_qty == 0:
            self.avg_entry = 0.0
        elif self.quantity == 0 or (self.quantity > 0) != (new_qty > 0):
            # Was flat or just flipped sides → new entry = fill_price
            self.avg_entry = fill_price
        elif (self.quantity > 0 and signed_qty > 0) or (
            self.quantity < 0 and signed_qty < 0
        ):
            # Adding to existing same-side position → VWAP
            self.avg_entry = (
                self.avg_entry * abs(self.quantity)
                + fill_price * abs(signed_qty)
            ) / abs(new_qty)
        # else: reduced same-side without flipping → avg_entry unchanged.

        self.quantity = new_qty
        return realized


@dataclass(frozen=True)
class Trade:
    """A filled order. Frozen audit record."""

    order_id: str
    asset: str
    side: OrderSide
    quantity: float
    fill_price: float
    fee_paid: float
    realized_pnl_at_fill: float
    """PnL realized on this specific fill (0 unless it closes/reduces)."""
    filled_at: datetime = field(default_factory=_now)
    paper: bool = True

    def __post_init__(self) -> None:
        assert self.paper is True, "ADR-016: Trade.paper must be True"
