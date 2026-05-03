"""Ichor paper trading layer.

PAPER-ONLY by ADR-016. Every public surface is stamped `paper=True` and
the package contains no broker SDK. To escalate to live trading, ADR-016
requires a NEW package `ichor_trading_live` with explicit Eliot ack +
audit trail.
"""

from .types import (
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    Trade,
)
from .paper_broker import PaperBroker, PaperBrokerError
from .pnl import compute_unrealized_pnl, equity_curve_from_trades

__all__ = [
    "Order",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "Position",
    "Trade",
    "PaperBroker",
    "PaperBrokerError",
    "compute_unrealized_pnl",
    "equity_curve_from_trades",
]
