"""Pure tests for the asian_session render + supported pairs."""

from __future__ import annotations

from ichor_api.services.asian_session import (
    AsianSessionReading,
    render_asian_session_block,
    supported_pairs,
)


def test_supported_pairs_includes_jpy_aud_nzd_crosses() -> None:
    pairs = supported_pairs()
    assert "USD_JPY" in pairs
    assert "AUD_USD" in pairs
    assert "NZD_USD" in pairs
    assert "EUR_JPY" in pairs


def test_render_none_yields_empty() -> None:
    md, sources = render_asian_session_block(None)
    assert md == ""
    assert sources == []


def test_render_no_bars_emits_note() -> None:
    r = AsianSessionReading(
        asset="USD_JPY",
        session_date_utc="2026-05-04",
        n_bars=0,
        open_price=None,
        fix_price=None,
        close_price=None,
        high=None,
        low=None,
        range_pips=None,
        open_to_fix_pips=None,
        fix_to_close_pips=None,
        open_to_close_pips=None,
        direction="asian_range",
        volume_total=0.0,
        note="no bars in Asian session window",
    )
    md, sources = render_asian_session_block(r)
    assert "no bars" in md
    assert sources == []


def test_render_full_payload_lines() -> None:
    r = AsianSessionReading(
        asset="USD_JPY",
        session_date_utc="2026-05-04",
        n_bars=120,
        open_price=152.10,
        fix_price=152.15,
        close_price=152.30,
        high=152.40,
        low=152.05,
        range_pips=35.0,
        open_to_fix_pips=5.0,
        fix_to_close_pips=15.0,
        open_to_close_pips=20.0,
        direction="asian_bid",
        volume_total=15_000.0,
    )
    md, sources = render_asian_session_block(r)
    assert "USD_JPY" in md
    assert "152" in md
    assert "asian_bid" in md
    assert "+20.0p" in md or "+20.0" in md
    assert "polygon_intraday:USD_JPY" in sources[0]


def test_render_asian_offered_direction_token() -> None:
    r = AsianSessionReading(
        asset="USD_JPY",
        session_date_utc="2026-05-04",
        n_bars=120,
        open_price=152.50,
        fix_price=152.30,
        close_price=152.10,
        high=152.55,
        low=152.05,
        range_pips=50.0,
        open_to_fix_pips=-20.0,
        fix_to_close_pips=-20.0,
        open_to_close_pips=-40.0,
        direction="asian_offered",
        volume_total=15_000.0,
    )
    md, _ = render_asian_session_block(r)
    assert "asian_offered" in md
