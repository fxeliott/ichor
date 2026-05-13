"""Smoke tests for the data_pool service.

Goal : confirm the module imports cleanly, the configuration dicts are
coherent across the Phase-1 universe, and the dataclass shapes are
stable. Full integration tests (with a real Postgres + fixtures) live
in the api integration suite which Phase 1 doesn't ship yet.
"""

from __future__ import annotations

from ichor_api.services.data_pool import (
    _ASSET_TO_POLYGON,
    _COT_MARKET_BY_ASSET,
    _DOLLAR_SMILE_SERIES,
    _MACRO_TRINITY_SERIES,
    _RATE_DIFF_PAIRS,
    _TFF_MARKET_BY_ASSET,
    DataPool,
)

PHASE1_ASSETS = {
    "EUR_USD",
    "GBP_USD",
    "USD_JPY",
    "AUD_USD",
    "USD_CAD",
    "XAU_USD",
    "NAS100_USD",
    "SPX500_USD",
}


def test_polygon_ticker_map_covers_phase1_universe() -> None:
    assert set(_ASSET_TO_POLYGON.keys()) == PHASE1_ASSETS


def test_polygon_xau_uses_currencies_namespace() -> None:
    """Regression guard for the XAU bug fixed 2026-05-03 (was X:XAUUSD)."""
    assert _ASSET_TO_POLYGON["XAU_USD"] == "C:XAUUSD"


def test_polygon_indices_use_i_namespace() -> None:
    assert _ASSET_TO_POLYGON["NAS100_USD"] == "I:NDX"
    # Round-27 ADR-089 (PROPOSED) : SPY proxy until Polygon Indices
    # Starter is budgeted. Allow either to support eventual upgrade.
    assert _ASSET_TO_POLYGON["SPX500_USD"] in {"SPY", "I:SPX"}


def test_cot_markets_cover_phase1_universe() -> None:
    """Every Phase-1 asset that has a CFTC futures contract must be in
    `_COT_MARKET_BY_ASSET`. SPX500_USD intentionally absent (its E-Mini
    code is pending — see data_pool.py inline comment)."""
    cot_keys = set(_COT_MARKET_BY_ASSET.keys())
    assert cot_keys <= PHASE1_ASSETS, f"unknown asset in COT map: {cot_keys - PHASE1_ASSETS}"
    # 7 of 8 Phase-1 assets currently mapped (SPX500 deferred).
    assert len(cot_keys) >= 7


def test_cot_market_codes_are_known_disaggregated_codes() -> None:
    """Codes are 6-digit CFTC commodity codes (cf data_pool.py)."""
    expected = {
        "EUR_USD": "099741",
        "GBP_USD": "096742",
        "USD_JPY": "097741",
        "AUD_USD": "232741",
        "USD_CAD": "090741",
        "XAU_USD": "088691",
        "NAS100_USD": "209742",
    }
    # Equality on the keys actually mapped (SPX500_USD pending — cf above).
    assert _COT_MARKET_BY_ASSET == expected


def test_rate_diff_pairs_cover_all_fx_majors() -> None:
    """All FX pairs (5 majors) must have a foreign 10Y series for the
    rate differential computation. XAU + indices are excluded by design."""
    assert set(_RATE_DIFF_PAIRS.keys()) == {"EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD"}


def test_tff_markets_cover_phase1_universe_including_spx() -> None:
    """TFF tracks all 8 Phase-1 assets (incl. SPX500 E-Mini code 13874A)."""
    tff_keys = set(_TFF_MARKET_BY_ASSET.keys())
    assert tff_keys <= PHASE1_ASSETS, f"unknown asset in TFF map: {tff_keys - PHASE1_ASSETS}"
    # TFF covers SPX500 unlike COT — verify the strict superset.
    assert "SPX500_USD" in tff_keys
    assert len(tff_keys) == 8


def test_tff_market_codes_match_collector_constants() -> None:
    """data_pool._TFF_MARKET_BY_ASSET must agree with collectors.cftc_tff
    MARKET_TO_ASSET — drift between the two is the cause of the
    'unknown target' bug class (cf ADR-024 / 030)."""
    from ichor_api.collectors.cftc_tff import MARKET_TO_ASSET as TFF_COLLECTOR_MAP

    for asset, code in _TFF_MARKET_BY_ASSET.items():
        assert TFF_COLLECTOR_MAP.get(code) == asset, (
            f"TFF map drift: data_pool says {asset}={code}, "
            f"collector says {code}={TFF_COLLECTOR_MAP.get(code)!r}"
        )


def test_macro_trinity_includes_dxy_us10y_vix() -> None:
    """The macro trinity must surface DXY broad, US10Y nominal, VIX."""
    assert "DTWEXBGS" in _MACRO_TRINITY_SERIES
    assert "DGS10" in _MACRO_TRINITY_SERIES
    assert "VIXCLS" in _MACRO_TRINITY_SERIES


def test_dollar_smile_includes_real_yields_and_oas() -> None:
    """Dollar-smile inputs must include TIPS real yields + HY OAS +
    IG OAS (the 3 pillars of the dollar-smile framework)."""
    assert "DFII10" in _DOLLAR_SMILE_SERIES
    assert "BAMLH0A0HYM2" in _DOLLAR_SMILE_SERIES
    assert "BAMLC0A0CM" in _DOLLAR_SMILE_SERIES


def test_data_pool_dataclass_is_frozen() -> None:
    """Mutability would let downstream code corrupt the audit trail."""
    pool = DataPool(
        asset="EUR_USD",
        generated_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        markdown="",
        sources=[],
        sections_emitted=[],
    )
    import dataclasses

    assert dataclasses.is_dataclass(pool)
    # frozen=True attempt to mutate raises
    try:
        pool.asset = "GBP_USD"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:
        raise AssertionError("DataPool should be frozen")


def test_format_specs_are_valid_python_format_strings() -> None:
    """All format strings in the series dicts must accept a float."""
    for series_id, (_label, fmt) in {
        **_MACRO_TRINITY_SERIES,
        **_DOLLAR_SMILE_SERIES,
    }.items():
        # Should not raise for a representative float
        formatted = fmt.format(123.456)
        assert isinstance(formatted, str)
        assert len(formatted) > 0, f"{series_id} format {fmt!r} produced empty string"
