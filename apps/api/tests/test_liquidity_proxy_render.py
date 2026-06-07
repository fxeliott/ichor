"""S04 — « manipulations & zones de liquidité » dimension render (macro facet).

Pins `render_liquidity_proxy_block`: the data_pool-section contract
(`tuple[markdown, sources]`), the documented LIQUIDITY_TIGHTENING threshold
band, honest-absence, source-stamping, and the ADR-017 boundary (descriptive
liquidity condition, never a trade instruction).
"""

from __future__ import annotations

import re
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from ichor_api.services.liquidity_proxy import (
    LIQ_TIGHTENING_THRESHOLD_BN,
    LiquidityProxyReading,
    assess_liquidity_proxy,
    render_liquidity_proxy_block,
)

# Mirror of session_verdict._FORBIDDEN_VERDICT_TOKENS_RE / scenarios forbidden set.
_FORBIDDEN = re.compile(r"\b(BUY|SELL|TP|SL|long entry|short entry|stop loss|take profit)\b", re.I)


def _reading(*, proxy=5000.0, delta=None, note="", tga_series=None) -> LiquidityProxyReading:
    return LiquidityProxyReading(
        rrp_bn=400.0 if proxy is not None else None,
        tga_bn=(proxy - 400.0) if proxy is not None else None,
        proxy_bn=proxy,
        proxy_bn_lag=None if delta is None else (proxy - delta),
        delta_bn=delta,
        note=note,
        tga_series=tga_series,
    )


def test_render_source_stamp_reflects_actual_tga_series() -> None:
    """Provenance integrity: when the value came from WTREGEN, the source stamp
    must say WTREGEN — never falsely claim DTS_TGA_CLOSE (Critic-verifiable)."""
    md, sources = render_liquidity_proxy_block(_reading(delta=-10.0, tga_series="WTREGEN"))
    assert "FRED:WTREGEN" in sources
    assert "FRED:WTREGEN" in md
    assert "FRED:DTS_TGA_CLOSE" not in sources


def test_render_returns_markdown_and_sources_contract() -> None:
    md, sources = render_liquidity_proxy_block(_reading(delta=-10.0))
    assert md.startswith("## Manipulation & liquidity zones")
    assert "FRED:RRPONTSYD" in sources and "FRED:DTS_TGA_CLOSE" in sources


def test_render_unavailable_when_proxy_none() -> None:
    md, sources = render_liquidity_proxy_block(
        _reading(proxy=None, note="missing series: RRPONTSYD")
    )
    assert "unavailable" in md
    assert "missing series" in md
    assert sources == []  # honest absence: no source stamp on a non-reading


def test_render_hard_drain_flags_elevated_manipulation() -> None:
    md, _ = render_liquidity_proxy_block(_reading(delta=LIQ_TIGHTENING_THRESHOLD_BN - 50))
    assert "DRAINING hard" in md
    assert "ELEVATED" in md
    assert "LIQUIDITY_TIGHTENING" in md


def test_render_mild_drain_is_thinning_not_elevated() -> None:
    md, _ = render_liquidity_proxy_block(_reading(delta=-80.0))
    assert "draining" in md
    assert "thinning" in md
    assert "DRAINING hard" not in md


def test_render_positive_delta_is_easing() -> None:
    md, _ = render_liquidity_proxy_block(_reading(delta=120.0))
    assert "easing" in md


def test_render_delta_none_is_honest_na() -> None:
    md, _ = render_liquidity_proxy_block(_reading(delta=None, note="insufficient history"))
    assert "n/a" in md
    assert "insufficient history" in md


def test_render_states_session05_boundary() -> None:
    md, _ = render_liquidity_proxy_block(_reading(delta=-10.0))
    assert "Session 05" in md  # ICT price-action zones are explicitly deferred


def test_render_is_adr017_clean_across_all_bands() -> None:
    for delta in (None, -300.0, -80.0, 0.0, 120.0):
        md, _ = render_liquidity_proxy_block(_reading(delta=delta))
        assert not _FORBIDDEN.search(md), f"ADR-017 token leaked at delta={delta}: {md!r}"
    # also the unavailable path
    md, _ = render_liquidity_proxy_block(_reading(proxy=None, note="missing"))
    assert not _FORBIDDEN.search(md)


# ── assess_liquidity_proxy TGA-source fallback (DTS_TGA_CLOSE → WTREGEN) ─────


def _exec_row(d, v) -> MagicMock:
    r = MagicMock()
    r.first.return_value = (d, v)
    return r


def _exec_none() -> MagicMock:
    r = MagicMock()
    r.first.return_value = None
    return r


@pytest.mark.asyncio
async def test_assess_falls_back_to_wtregen_when_dts_empty() -> None:
    """The latent bug this dimension exposed: DTS_TGA_CLOSE is empty in prod
    but WTREGEN (FRED weekly TGA) is fresh. The proxy must fall back so the
    dimension carries data instead of going permanently 'unavailable'."""
    session = MagicMock()
    # Call order in assess_liquidity_proxy:
    #   RRP now → DTS now (empty) → WTREGEN now → RRP lag → DTS lag (empty) → WTREGEN lag
    session.execute = AsyncMock(
        side_effect=[
            _exec_row(date(2026, 6, 5), 0.76),  # RRPONTSYD now ($bn)
            _exec_none(),  # DTS_TGA_CLOSE now → empty
            _exec_row(date(2026, 6, 3), 875713.0),  # WTREGEN now ($mn) → fallback
            _exec_row(date(2026, 5, 29), 0.80),  # RRPONTSYD lag
            _exec_none(),  # DTS_TGA_CLOSE lag → empty
            _exec_row(date(2026, 5, 27), 830296.0),  # WTREGEN lag → fallback
        ]
    )
    reading = await assess_liquidity_proxy(session)
    assert reading.proxy_bn is not None, "proxy must compute via the WTREGEN fallback"
    assert reading.tga_bn is not None and reading.tga_bn > 800.0  # 875713/1000 ≈ 876 $bn
    assert reading.delta_bn is not None
    assert "via WTREGEN" in reading.note  # fallback source is provenance-stamped


@pytest.mark.asyncio
async def test_assess_unavailable_when_no_tga_series_at_all() -> None:
    """Both DTS_TGA_CLOSE and WTREGEN empty → honest 'unavailable', never crash."""
    session = MagicMock()
    session.execute = AsyncMock(
        side_effect=[
            _exec_row(date(2026, 6, 5), 0.76),  # RRP now
            _exec_none(),  # DTS now empty
            _exec_none(),  # WTREGEN now empty → no TGA
        ]
    )
    reading = await assess_liquidity_proxy(session)
    assert reading.proxy_bn is None
    assert "missing series" in reading.note and "WTREGEN" in reading.note
