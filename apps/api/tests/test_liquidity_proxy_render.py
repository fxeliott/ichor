"""S04 — « manipulations & zones de liquidité » dimension render (macro facet).

Pins `render_liquidity_proxy_block`: the data_pool-section contract
(`tuple[markdown, sources]`), the documented LIQUIDITY_TIGHTENING threshold
band, honest-absence, source-stamping, and the ADR-017 boundary (descriptive
liquidity condition, never a trade instruction).
"""

from __future__ import annotations

import re

from ichor_api.services.liquidity_proxy import (
    LIQ_TIGHTENING_THRESHOLD_BN,
    LiquidityProxyReading,
    render_liquidity_proxy_block,
)

# Mirror of session_verdict._FORBIDDEN_VERDICT_TOKENS_RE / scenarios forbidden set.
_FORBIDDEN = re.compile(r"\b(BUY|SELL|TP|SL|long entry|short entry|stop loss|take profit)\b", re.I)


def _reading(*, proxy=5000.0, delta=None, note="") -> LiquidityProxyReading:
    return LiquidityProxyReading(
        rrp_bn=400.0 if proxy is not None else None,
        tga_bn=(proxy - 400.0) if proxy is not None else None,
        proxy_bn=proxy,
        proxy_bn_lag=None if delta is None else (proxy - delta),
        delta_bn=delta,
        note=note,
    )


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
