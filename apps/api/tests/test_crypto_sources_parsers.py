"""Pure-parsing tests for the 3 crypto-source collectors.

No network, no DB. Validates response shape handling so a
schema drift on alternative.me / Binance / DeFiLlama is caught
before the cron silently dumps zero rows.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from ichor_api.collectors.binance_funding import (
    annualize_rate,
    parse_funding_response,
    supported_symbols,
)
from ichor_api.collectors.crypto_fear_greed import (
    is_extreme,
    parse_fng_response,
)
from ichor_api.collectors.defillama import (
    parse_chain_tvl_response,
    parse_stablecoins_response,
)


# ── DeFiLlama ────────────────────────────────────────────────────────


def test_parse_chain_tvl_canonical_response() -> None:
    body = [
        {"date": 1700000000, "tvl": 50_000_000_000.0},
        {"date": 1700086400, "tvl": 51_500_000_000.0},
    ]
    out = parse_chain_tvl_response("Ethereum", body)
    assert len(out) == 2
    assert out[0].chain == "Ethereum"
    assert out[0].tvl_usd == 50e9


def test_parse_chain_tvl_skips_malformed_rows() -> None:
    body = [
        {"date": 1700000000, "tvl": 1.0},
        {"date": None, "tvl": 2.0},  # bad date
        {"date": 1700086400, "tvl": None},  # bad tvl
        "garbage",  # not a dict
        {"date": 1700172800, "tvl": "n/a"},  # non-numeric tvl
    ]
    out = parse_chain_tvl_response("Solana", body)
    assert len(out) == 1


def test_parse_chain_tvl_returns_empty_on_non_list() -> None:
    assert parse_chain_tvl_response("X", {"data": []}) == []
    assert parse_chain_tvl_response("X", "garbage") == []


def test_parse_stablecoins_handles_pegged_usd_dict() -> None:
    """The 2026 schema wraps totalCirculatingUSD in {peggedUSD: N}."""
    body = [
        {"date": 1700000000, "totalCirculatingUSD": {"peggedUSD": 150_000_000_000}},
        {"date": 1700086400, "totalCirculatingUSD": {"peggedUSD": 151_000_000_000}},
    ]
    out = parse_stablecoins_response(body)
    assert len(out) == 2
    assert out[0].total_circulating_usd == 150e9


def test_parse_stablecoins_handles_flat_dict_aggregation() -> None:
    """If peggedUSD is missing, sum numeric values in the dict."""
    body = [
        {
            "date": 1700000000,
            "totalCirculatingUSD": {"peggedSGD": 1.0, "peggedJPY": 2.0},  # no peggedUSD
        },
    ]
    out = parse_stablecoins_response(body)
    assert len(out) == 1
    assert out[0].total_circulating_usd == 3.0


# ── Binance funding ─────────────────────────────────────────────────


def test_parse_funding_canonical_response() -> None:
    body = [
        {"symbol": "BTCUSDT", "fundingTime": 1700000000000, "fundingRate": "0.0001"},
        {"symbol": "BTCUSDT", "fundingTime": 1700028800000, "fundingRate": "0.00015"},
    ]
    out = parse_funding_response("BTCUSDT", body)
    assert len(out) == 2
    assert out[0].funding_rate == 0.0001


def test_parse_funding_skips_malformed_rows() -> None:
    body = [
        {"symbol": "BTCUSDT", "fundingTime": 1700000000000, "fundingRate": "0.0001"},
        {"fundingTime": None},  # bad
        {"fundingTime": 1700028800000, "fundingRate": "garbage"},  # bad rate
        "not-a-dict",
    ]
    out = parse_funding_response("BTCUSDT", body)
    assert len(out) == 1


def test_annualize_rate_reasonable_magnitude() -> None:
    # 0.01% per 8h → 0.01% × 3 × 365 ≈ 10.95% annualized
    annual = annualize_rate(0.0001)
    assert 0.10 < annual < 0.12


def test_supported_symbols_minimum_set() -> None:
    syms = supported_symbols()
    assert "BTCUSDT" in syms
    assert "ETHUSDT" in syms


# ── Crypto Fear & Greed ─────────────────────────────────────────────


def test_parse_fng_canonical_response() -> None:
    body = {
        "data": [
            {
                "value": "75",
                "value_classification": "Greed",
                "timestamp": "1700000000",
                "time_until_update": "12345",
            },
            {
                "value": "30",
                "value_classification": "Fear",
                "timestamp": "1700086400",
            },
        ]
    }
    out = parse_fng_response(body)
    assert len(out) == 2
    assert out[0].value == 75
    assert out[0].classification == "Greed"


def test_parse_fng_rejects_out_of_range_values() -> None:
    body = {
        "data": [
            {"value": "150", "timestamp": "1700000000"},  # > 100
            {"value": "-5", "timestamp": "1700086400"},  # < 0
            {"value": "50", "timestamp": "1700172800"},  # ok
        ]
    }
    out = parse_fng_response(body)
    assert len(out) == 1
    assert out[0].value == 50


def test_is_extreme_detects_thresholds() -> None:
    from ichor_api.collectors.crypto_fear_greed import FearGreedReading

    fixed_dt = datetime(2026, 5, 5, tzinfo=UTC)
    extreme_low = FearGreedReading(
        observation_date=date(2026, 5, 1),
        value=15,
        classification="Extreme Fear",
        fetched_at=fixed_dt,
    )
    extreme_high = FearGreedReading(
        observation_date=date(2026, 5, 1),
        value=85,
        classification="Extreme Greed",
        fetched_at=fixed_dt,
    )
    middle = FearGreedReading(
        observation_date=date(2026, 5, 1),
        value=50,
        classification="Neutral",
        fetched_at=fixed_dt,
    )
    assert is_extreme(extreme_low)
    assert is_extreme(extreme_high)
    assert not is_extreme(middle)


def test_parse_fng_empty_data_returns_empty() -> None:
    assert parse_fng_response({"data": []}) == []
    assert parse_fng_response({}) == []


def test_parse_fng_garbage_returns_empty() -> None:
    assert parse_fng_response("string") == []
    assert parse_fng_response(None) == []
