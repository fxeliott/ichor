"""End-to-end tests for the paper trading layer.

Includes : type invariants (paper=True everywhere), Position math
(open / add / reduce / close / flip), PaperBroker submit + fill,
fee/slippage application, P&L helpers.
"""

from __future__ import annotations

import pytest

from ichor_trading import (
    Order,
    PaperBroker,
    PaperBrokerError,
    Position,
    Trade,
    compute_unrealized_pnl,
    equity_curve_from_trades,
)


# ───────────────────────── invariants ─────────────────────────


def test_order_paper_invariant() -> None:
    """ADR-016: Order.paper must be True ; constructor refuses False."""
    o = Order(asset="EUR_USD", side="buy", quantity=100)
    assert o.paper is True
    # Frozen dataclass — paper field cannot be reassigned.
    with pytest.raises((AttributeError, Exception)):
        o.paper = False  # type: ignore[misc]


def test_order_constructor_refuses_paper_false() -> None:
    with pytest.raises(AssertionError):
        Order(asset="EUR_USD", side="buy", quantity=100, paper=False)


def test_order_zero_quantity_refused() -> None:
    with pytest.raises(AssertionError):
        Order(asset="EUR_USD", side="buy", quantity=0)


def test_order_negative_quantity_refused() -> None:
    with pytest.raises(AssertionError):
        Order(asset="EUR_USD", side="sell", quantity=-100)


def test_limit_order_requires_limit_price() -> None:
    with pytest.raises(AssertionError):
        Order(asset="EUR_USD", side="buy", quantity=100, order_type="limit")


def test_trade_paper_invariant() -> None:
    t = Trade(
        order_id="abc",
        asset="EUR_USD",
        side="buy",
        quantity=100,
        fill_price=1.10,
        fee_paid=0.011,
        realized_pnl_at_fill=0.0,
    )
    assert t.paper is True


# ───────────────────────── Position math ─────────────────────────


def test_position_open_long() -> None:
    p = Position(asset="EUR_USD")
    realized = p.update_on_fill(100, 1.10, "buy")
    assert p.quantity == 100
    assert p.avg_entry == 1.10
    assert realized == 0


def test_position_add_to_long_vwap() -> None:
    p = Position(asset="EUR_USD", quantity=100, avg_entry=1.10)
    p.update_on_fill(100, 1.20, "buy")
    assert p.quantity == 200
    # VWAP = (100 * 1.10 + 100 * 1.20) / 200 = 1.15
    assert abs(p.avg_entry - 1.15) < 1e-9


def test_position_reduce_long_realizes_pnl() -> None:
    p = Position(asset="EUR_USD", quantity=100, avg_entry=1.10)
    realized = p.update_on_fill(40, 1.20, "sell")
    assert p.quantity == 60
    assert p.avg_entry == 1.10  # unchanged on reduction
    # 40 sold at 1.20 vs entry 1.10 → +0.04
    assert abs(realized - 4.0) < 1e-9
    assert abs(p.realized_pnl - 4.0) < 1e-9


def test_position_close_long() -> None:
    p = Position(asset="EUR_USD", quantity=100, avg_entry=1.10)
    realized = p.update_on_fill(100, 1.20, "sell")
    assert p.is_flat()
    assert p.avg_entry == 0.0
    assert abs(realized - 10.0) < 1e-9


def test_position_flip_long_to_short_realizes_only_closed_part() -> None:
    p = Position(asset="EUR_USD", quantity=100, avg_entry=1.10)
    # Sell 150 at 1.20 → close 100 long + open 50 short
    realized = p.update_on_fill(150, 1.20, "sell")
    assert abs(realized - 10.0) < 1e-9  # only the 100 closed
    assert p.quantity == -50
    assert p.avg_entry == 1.20


def test_position_short_works_symmetrically() -> None:
    p = Position(asset="EUR_USD")
    p.update_on_fill(100, 1.20, "sell")
    assert p.quantity == -100
    assert p.avg_entry == 1.20
    # Cover at 1.10 → +0.10 per unit on 100 units
    realized = p.update_on_fill(100, 1.10, "buy")
    assert abs(realized - 10.0) < 1e-9
    assert p.is_flat()


# ───────────────────────── PaperBroker ─────────────────────────


def _oracle(prices: dict[str, float]):
    def f(asset: str) -> float:
        return prices[asset]
    return f


def test_paper_broker_buy_fill_updates_position_and_cash() -> None:
    b = PaperBroker(initial_cash=10_000, fee_bps_per_side=1.0)
    o = Order(asset="EUR_USD", side="buy", quantity=100)
    t = b.submit(o, _oracle({"EUR_USD": 1.10}))
    pos = b.get_position("EUR_USD")
    # fill price = 1.10 * (1 + 1bps) = 1.10011
    assert abs(t.fill_price - 1.10011) < 1e-6
    # notional ~= 110.011 ; fee ~= 0.0110011
    assert pos.quantity == 100
    expected_cash = 10_000 - 100 * 1.10011 - 100 * 1.10011 * 0.0001
    assert abs(b.cash - expected_cash) < 1e-4


def test_paper_broker_sell_fill_below_reference() -> None:
    b = PaperBroker(initial_cash=10_000, fee_bps_per_side=2.0)
    t = b.submit(
        Order(asset="EUR_USD", side="sell", quantity=100),
        _oracle({"EUR_USD": 1.10}),
    )
    # sell fills below reference
    assert t.fill_price < 1.10


def test_paper_broker_round_trip_realizes_pnl() -> None:
    b = PaperBroker(initial_cash=10_000, fee_bps_per_side=1.0)
    b.submit(Order(asset="EUR_USD", side="buy", quantity=100),
             _oracle({"EUR_USD": 1.10}))
    t2 = b.submit(Order(asset="EUR_USD", side="sell", quantity=100),
                  _oracle({"EUR_USD": 1.20}))
    assert b.get_position("EUR_USD").is_flat()
    # Per-fill realized comes from Position.update_on_fill, not raw price diff
    assert t2.realized_pnl_at_fill > 0  # bought low, sold high


def test_paper_broker_limit_order_rejects_non_marketable() -> None:
    b = PaperBroker(initial_cash=10_000)
    o = Order(
        asset="EUR_USD", side="buy", quantity=100,
        order_type="limit", limit_price=1.05,  # below ref 1.10
    )
    with pytest.raises(PaperBrokerError):
        b.submit(o, _oracle({"EUR_USD": 1.10}))


def test_paper_broker_limit_order_fills_when_marketable() -> None:
    b = PaperBroker(initial_cash=10_000)
    # Buy limit 1.20, ref 1.10 → marketable
    o = Order(
        asset="EUR_USD", side="buy", quantity=100,
        order_type="limit", limit_price=1.20,
    )
    t = b.submit(o, _oracle({"EUR_USD": 1.10}))
    assert t.fill_price > 0
    assert b.get_position("EUR_USD").quantity == 100


def test_paper_broker_oracle_failure_raises() -> None:
    b = PaperBroker()
    def bad_oracle(asset: str) -> float:
        raise RuntimeError("oracle down")
    with pytest.raises(PaperBrokerError):
        b.submit(Order(asset="EUR_USD", side="buy", quantity=100), bad_oracle)


def test_paper_broker_negative_price_rejected() -> None:
    b = PaperBroker()
    with pytest.raises(PaperBrokerError):
        b.submit(
            Order(asset="EUR_USD", side="buy", quantity=100),
            _oracle({"EUR_USD": -1.0}),
        )


def test_paper_broker_equity_marks_to_market() -> None:
    b = PaperBroker(initial_cash=10_000, fee_bps_per_side=0)
    b.submit(
        Order(asset="EUR_USD", side="buy", quantity=100),
        _oracle({"EUR_USD": 1.10}),
    )
    # Now mark moved up to 1.20
    eq = b.equity(_oracle({"EUR_USD": 1.20}))
    # Cash = 10_000 - 110 = 9890 ; mark = 100 * 1.20 = 120 ; total = 10010
    assert abs(eq - 10_010) < 0.5


# ───────────────────────── pnl helpers ─────────────────────────


def test_equity_curve_from_trades_sequential_cash() -> None:
    b = PaperBroker(initial_cash=10_000, fee_bps_per_side=0)
    b.submit(
        Order(asset="EUR_USD", side="buy", quantity=100),
        _oracle({"EUR_USD": 1.10}),
    )
    b.submit(
        Order(asset="EUR_USD", side="sell", quantity=100),
        _oracle({"EUR_USD": 1.20}),
    )
    curve = equity_curve_from_trades(b.trades, initial_cash=10_000)
    assert len(curve) == 2
    # After buy: 10_000 - 110 = 9890
    assert abs(curve[0].cash - 9890) < 1e-6
    # After sell: 9890 + 120 = 10_010
    assert abs(curve[1].cash - 10_010) < 1e-6
    assert curve[1].realized_cumulative > 0


def test_unrealized_pnl_open_long_positive_when_mark_above_entry() -> None:
    pos = {"EUR_USD": Position(asset="EUR_USD", quantity=100, avg_entry=1.10)}
    pnl = compute_unrealized_pnl(pos, {"EUR_USD": 1.15})
    assert abs(pnl - 5.0) < 1e-9


def test_unrealized_pnl_short_positive_when_mark_below_entry() -> None:
    pos = {"EUR_USD": Position(asset="EUR_USD", quantity=-100, avg_entry=1.10)}
    pnl = compute_unrealized_pnl(pos, {"EUR_USD": 1.05})
    assert abs(pnl - 5.0) < 1e-9


def test_unrealized_pnl_skip_missing_marks() -> None:
    pos = {
        "EUR_USD": Position(asset="EUR_USD", quantity=100, avg_entry=1.10),
        "XAU_USD": Position(asset="XAU_USD", quantity=10, avg_entry=2900),
    }
    pnl = compute_unrealized_pnl(pos, {"EUR_USD": 1.15})  # XAU mark missing
    # Only EUR_USD counted
    assert abs(pnl - 5.0) < 1e-9


def test_unrealized_pnl_zero_when_flat() -> None:
    pos = {"EUR_USD": Position(asset="EUR_USD")}
    assert compute_unrealized_pnl(pos, {"EUR_USD": 1.10}) == 0.0
