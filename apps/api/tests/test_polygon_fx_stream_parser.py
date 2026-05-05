"""Tests for the Polygon Forex Quote message parser.

Wire format VERIFIED on 2026-05-05 against official Polygon docs +
github.com/polygon-io/client-python/examples/websocket/forex.py :

  Subscribe : `{"action":"subscribe","params":"C.EUR/USD,C.GBP/USD,..."}`
  Quote evt : `{"ev":"C","p":"USD/CNH","x":"44","a":6.83366,"b":6.83363,"t":1536036818784}`

The `x` (exchange ID) field is a string in Polygon's docs but our model
column is INTEGER. The parser must coerce or skip cleanly.

These tests cover the parser-only path (no WebSocket needed), so they
run instantly without hitting the network.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from ichor_api.collectors.polygon_fx_stream import (
    DEFAULT_PAIRS,
    FxTickEvent,
    _ticker_to_asset,
    parse_frame,
    parse_quote_message,
)


# ───────────────────── _ticker_to_asset ─────────────────────


def test_ticker_to_asset_strips_slash() -> None:
    assert _ticker_to_asset("EUR/USD") == "EURUSD"
    assert _ticker_to_asset("XAU/USD") == "XAUUSD"
    assert _ticker_to_asset("USD/JPY") == "USDJPY"


def test_default_pairs_are_six_majors_plus_xau() -> None:
    assert "EUR/USD" in DEFAULT_PAIRS
    assert "XAU/USD" in DEFAULT_PAIRS
    assert len(DEFAULT_PAIRS) == 6


# ─────────────────── parse_quote_message ──────────────────


def test_parse_quote_canonical_message() -> None:
    msg = {
        "ev": "C",
        "p": "USD/CNH",
        "x": 44,
        "a": 6.83366,
        "b": 6.83363,
        "t": 1536036818784,
    }
    ev = parse_quote_message(msg)
    assert isinstance(ev, FxTickEvent)
    assert ev.asset == "USDCNH"
    assert ev.ticker == "C:USD/CNH"
    assert ev.bid == 6.83363
    assert ev.ask == 6.83366
    assert ev.mid == (6.83363 + 6.83366) / 2.0
    assert ev.exchange_id == 44
    # Timestamp 1536036818784 ms = 2018-09-04T07:33:38.784Z
    assert ev.ts.year == 2018
    assert ev.ts.tzinfo is UTC


def test_parse_quote_message_returns_none_for_non_quote_event() -> None:
    """Polygon multiplexes status / aggregate frames on the same socket ;
    only ev='C' is a Forex Quote."""
    assert parse_quote_message({"ev": "status", "status": "auth_success"}) is None
    assert parse_quote_message({"ev": "CAS", "p": "EUR/USD"}) is None  # second-aggs
    assert parse_quote_message({"ev": "CA", "p": "EUR/USD"}) is None  # minute-aggs


def test_parse_quote_message_rejects_non_dict() -> None:
    assert parse_quote_message(None) is None
    assert parse_quote_message("a string") is None
    assert parse_quote_message([1, 2, 3]) is None
    assert parse_quote_message(42) is None


def test_parse_quote_message_drops_zero_or_negative_prices() -> None:
    bad_bid = {"ev": "C", "p": "EUR/USD", "b": 0, "a": 1.10, "t": 1700000000000}
    assert parse_quote_message(bad_bid) is None
    bad_ask = {"ev": "C", "p": "EUR/USD", "b": 1.10, "a": -0.5, "t": 1700000000000}
    assert parse_quote_message(bad_ask) is None


def test_parse_quote_message_drops_zero_timestamp() -> None:
    msg = {"ev": "C", "p": "EUR/USD", "b": 1.0995, "a": 1.0997, "t": 0}
    assert parse_quote_message(msg) is None


def test_parse_quote_message_drops_missing_pair() -> None:
    msg = {"ev": "C", "b": 1.0995, "a": 1.0997, "t": 1700000000000}
    assert parse_quote_message(msg) is None
    empty_pair = {"ev": "C", "p": "", "b": 1.0995, "a": 1.0997, "t": 1700000000000}
    assert parse_quote_message(empty_pair) is None


def test_parse_quote_message_drops_non_numeric_prices() -> None:
    msg = {"ev": "C", "p": "EUR/USD", "b": "1.0995", "a": 1.0997, "t": 1700000000000}
    # Per Polygon docs, b/a are floats — but if a future change ships
    # them as strings, defensively skip.
    assert parse_quote_message(msg) is None


def test_parse_quote_handles_optional_fields_absent() -> None:
    """Per Polygon Forex spec, bs/as (sizes) are CRYPTO-only — absent on
    Forex frames. The parser must not crash."""
    msg = {
        "ev": "C",
        "p": "EUR/USD",
        "b": 1.0995,
        "a": 1.0997,
        "t": 1700000000000,
    }
    ev = parse_quote_message(msg)
    assert ev is not None
    assert ev.bid_size is None
    assert ev.ask_size is None
    assert ev.exchange_id is None  # x absent here


def test_parse_quote_mid_price_arithmetic() -> None:
    msg = {"ev": "C", "p": "EUR/USD", "b": 1.0995, "a": 1.0997, "t": 1700000000000}
    ev = parse_quote_message(msg)
    assert ev is not None
    assert ev.mid == 1.0996


# ───────────────────── parse_frame ────────────────────────


def test_parse_frame_extracts_quotes_from_array() -> None:
    """Polygon batches messages into a JSON array per WebSocket frame."""
    frame = json.dumps(
        [
            {"ev": "C", "p": "EUR/USD", "b": 1.0995, "a": 1.0997, "t": 1700000000000},
            {"ev": "C", "p": "GBP/USD", "b": 1.2540, "a": 1.2542, "t": 1700000000100},
        ]
    )
    out = parse_frame(frame)
    assert len(out) == 2
    assert out[0].asset == "EURUSD"
    assert out[1].asset == "GBPUSD"


def test_parse_frame_handles_single_object() -> None:
    """Some frames (status messages) come as a single object, not array."""
    frame = json.dumps(
        {"ev": "C", "p": "EUR/USD", "b": 1.0995, "a": 1.0997, "t": 1700000000000}
    )
    out = parse_frame(frame)
    assert len(out) == 1
    assert out[0].asset == "EURUSD"


def test_parse_frame_skips_non_quote_events_in_mixed_array() -> None:
    """A frame may carry both status frames and Quote events ; keep
    only the quotes."""
    frame = json.dumps(
        [
            {"ev": "status", "status": "auth_success", "message": "authenticated"},
            {"ev": "C", "p": "EUR/USD", "b": 1.0995, "a": 1.0997, "t": 1700000000000},
            {"ev": "status", "status": "success", "message": "subscribed"},
        ]
    )
    out = parse_frame(frame)
    assert len(out) == 1
    assert out[0].asset == "EURUSD"


def test_parse_frame_returns_empty_for_invalid_json() -> None:
    assert parse_frame("not-json{") == []
    assert parse_frame("") == []


def test_parse_frame_returns_empty_for_unrelated_payload() -> None:
    assert parse_frame(json.dumps({"foo": "bar"})) == []


def test_parse_frame_preserves_order() -> None:
    """Tick ordering matters for VPIN — frames must surface quotes in
    the order received."""
    frame = json.dumps(
        [
            {"ev": "C", "p": "EUR/USD", "b": 1.0, "a": 1.001, "t": 1700000000000},
            {"ev": "C", "p": "EUR/USD", "b": 1.001, "a": 1.002, "t": 1700000000010},
            {"ev": "C", "p": "EUR/USD", "b": 1.002, "a": 1.003, "t": 1700000000020},
        ]
    )
    out = parse_frame(frame)
    assert len(out) == 3
    assert [e.bid for e in out] == [1.0, 1.001, 1.002]


def test_parse_frame_drops_silently_malformed_quotes_in_batch() -> None:
    """Defensive : one corrupt quote must not poison the whole frame."""
    frame = json.dumps(
        [
            {"ev": "C", "p": "EUR/USD", "b": 1.0995, "a": 1.0997, "t": 1700000000000},
            {"ev": "C", "p": "EUR/USD", "b": 0, "a": 1.0997, "t": 1700000000010},  # bad
            {"ev": "C", "p": "GBP/USD", "b": 1.2540, "a": 1.2542, "t": 1700000000020},
        ]
    )
    out = parse_frame(frame)
    assert len(out) == 2
    assert {e.asset for e in out} == {"EURUSD", "GBPUSD"}


def test_parse_quote_coerces_string_digit_exchange_id_to_int() -> None:
    """Polygon docs sample shows `x: "44"` (string). The parser coerces
    digit strings to int so the value lands in the INTEGER column."""
    msg = {
        "ev": "C",
        "p": "EUR/USD",
        "x": "44",
        "a": 1.10,
        "b": 1.0995,
        "t": 1700000000000,
    }
    ev = parse_quote_message(msg)
    assert ev is not None
    assert ev.exchange_id == 44


def test_parse_quote_drops_garbage_exchange_id_string() -> None:
    """Non-digit strings (e.g., 'NYSE') get dropped to None rather than
    raising or coercing wrongly."""
    msg = {
        "ev": "C",
        "p": "EUR/USD",
        "x": "NYSE",
        "a": 1.10,
        "b": 1.0995,
        "t": 1700000000000,
    }
    ev = parse_quote_message(msg)
    assert ev is not None
    assert ev.exchange_id is None
