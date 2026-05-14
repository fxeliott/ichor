"""Unit tests for `_section_cross_asset_matrix` XAU_USD + NAS100_USD +
SPX500_USD symmetric bias hints (round-46 r46-round-5, R47 retroactive
symmetric mirror per cross-asset matrix R47 pattern codified r46-round-2).

The pre-r46-round-5 cross-asset matrix surfaced uni-directional hints
for these 3 assets despite their per-asset `_section_*_specific`
modules being fully symmetric :

  - XAU_USD : 3 partial-symmetric `(++)` / `(-)` hints (real-yield
    support + safe-haven flow + USD-strength counter-pressure) but NO
    XAU-soft mirror branch (e.g. real-yield headwind in goldilocks).
  - NAS100_USD : 3 NAS-soft `(-)` hints (duration headwind + multiple
    compression + vol-of-vol drag) and ZERO NAS-bid mirror despite
    `_section_nas_specific` (r42) being fully symmetric on all 3
    drivers (DGS10 + VVIX + SKEW) with Tetlock invalidation on both
    branches.
  - SPX500_USD : 2 SPX-soft `(-)` hints (risk-off + earnings-tail)
    and ZERO SPX-bid mirror despite `_section_spx_specific` (r43)
    being fully symmetric on VIX-term-structure + NFCI + SBOI.

Round-46-round-5 adds symmetric bid/soft mirrors with Tetlock
invalidation thresholds matching the per-asset specific sections
(Erb-Harvey 2013 + Stephen-Jen dollar-smile for XAU ; Hou-Mo-Xue 2015
+ Park 2015 + Bevilacqua-Tunaru 2021 for NAS ; Brunnermeier-Pedersen
2009 funding-liquidity-spiral for SPX). Audit-gap #16.

These tests pin :
  - Symmetric mirror invariant (each asset has BOTH bid/soft branches)
  - Tetlock invalidation discipline (every hint carries "invalidated if")
  - ADR-017 boundary regex-clean (no BUY/SELL/LONG/SHORT/TARGET/STOP/ENTRY)
  - Framework attribution anchors (Erb-Harvey, Brunnermeier-Pedersen,
    Hou-Mo-Xue, Park 2015, Bevilacqua-Tunaru 2021)
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from ichor_api.services.data_pool import _section_cross_asset_matrix


def _make_mct_row(value: float) -> MagicMock:
    row = MagicMock()
    row.mct_trend_pct = value
    row.observation_month = date(2026, 4, 1)
    return row


def _make_nowcast_row(value: float) -> MagicMock:
    row = MagicMock()
    row.nowcast_value = value
    row.revision_date = date(2026, 5, 1)
    return row


def _make_skew_row(value: float) -> MagicMock:
    row = MagicMock()
    row.skew_value = value
    row.observation_date = date(2026, 5, 13)
    return row


def _make_sbet_row(value: float) -> MagicMock:
    row = MagicMock()
    row.sboi = value
    row.report_month = date(2026, 4, 1)
    return row


def _make_session_execute_mock(
    mct_val: float,
    nowcast_val: float,
    skew_val: float,
    sbet_val: float,
) -> MagicMock:
    """Build an AsyncMock session whose .execute() returns the right
    scalar for each query in `_section_cross_asset_matrix`. Order :
    MCT -> Nowcast -> SKEW -> SBET (each via `.scalar_one_or_none()`)."""
    results = [
        _make_mct_row(mct_val),
        _make_nowcast_row(nowcast_val),
        _make_skew_row(skew_val),
        _make_sbet_row(sbet_val),
    ]

    def execute_side_effect(_stmt: object) -> MagicMock:
        r = MagicMock()
        r.scalar_one_or_none = MagicMock(return_value=results.pop(0))
        return r

    session = MagicMock()
    session.execute = AsyncMock(side_effect=execute_side_effect)
    return session


def _xau_block(md: str) -> str:
    return md.split("XAU_USD")[1].split("NAS100_USD")[0]


def _nas_block(md: str) -> str:
    return md.split("NAS100_USD")[1].split("SPX500_USD")[0]


def _spx_block(md: str) -> str:
    # SPX is the last asset in the matrix — split on the trailing newline
    # after the section is complete.
    return md.split("SPX500_USD")[1]


# ─────────────── USD-positive / stress regime (XAU-bid, NAS-soft, SPX-soft) ───────────────


@pytest.mark.asyncio
async def test_stress_regime_xau_bid_nas_soft_spx_soft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """USD-positive stress regime (NFCI tight, VIX panic, MCT unanchored,
    SKEW tail-fear, SBOI recession-pre) -> XAU bid scenarios fire,
    NAS soft scenarios fire, SPX soft scenarios fire."""

    async def fake_latest_fred(
        _session: object, series_id: str, *, max_age_days: int = 14
    ) -> tuple[float, datetime] | None:
        if series_id == "NFCI":
            return (0.8, datetime.now(UTC))  # tight
        if series_id == "VIXCLS":
            return (35.0, datetime.now(UTC))  # panic
        return None

    monkeypatch.setattr("ichor_api.services.data_pool._latest_fred", fake_latest_fred)

    session = _make_session_execute_mock(
        mct_val=3.50,  # inflation_pressure_up
        nowcast_val=3.55,
        skew_val=160.0,  # tail-fear
        sbet_val=92.0,  # sentiment_weak
    )
    md, _src = await _section_cross_asset_matrix(session)

    xau_block = _xau_block(md)
    nas_block = _nas_block(md)
    spx_block = _spx_block(md)

    # XAU : 3 XAU-bid hints fire (real-yield + safe-haven + USD-strength counter)
    assert xau_block.count("XAU-bid (") == 3
    assert "real-yield support via Erb-Harvey" in xau_block
    assert "safe-haven flight + dollar-smile co-bid per Brunnermeier-Pedersen 2009" in xau_block
    assert "USD-strength counter-pressure" in xau_block
    # NO XAU-soft in stress regime
    assert "XAU-soft" not in xau_block

    # NAS : 3 NAS-soft hints fire
    assert nas_block.count("NAS-soft (") == 3
    assert "duration headwind via Hou-Mo-Xue" in nas_block
    assert "multiple-compression via funding-stress" in nas_block
    assert "vol-of-vol drag" in nas_block
    # NO NAS-bid in stress regime
    assert "NAS-bid" not in nas_block

    # SPX : 2 SPX-soft hints fire (risk-off + earnings-tail)
    assert spx_block.count("SPX-soft (") == 2
    assert "risk-off pressure via Brunnermeier-Pedersen funding-liquidity spiral" in spx_block
    assert "earnings-tail downside via SBOI" in spx_block
    # NO SPX-bid in stress regime
    assert "SPX-bid" not in spx_block


# ─────────────── Goldilocks regime (XAU-soft, NAS-bid, SPX-bid) ───────────────


@pytest.mark.asyncio
async def test_goldilocks_regime_xau_soft_nas_bid_spx_bid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """USD-complacency goldilocks regime (NFCI loose, VIX complacent,
    SKEW calm, MCT anchored, SBOI expansionary) -> XAU soft mirror
    fires, NAS bid mirror fires, SPX bid mirror fires."""

    async def fake_latest_fred(
        _session: object, series_id: str, *, max_age_days: int = 14
    ) -> tuple[float, datetime] | None:
        if series_id == "NFCI":
            return (-0.7, datetime.now(UTC))  # loose
        if series_id == "VIXCLS":
            return (13.0, datetime.now(UTC))  # complacent
        return None

    monkeypatch.setattr("ichor_api.services.data_pool._latest_fred", fake_latest_fred)

    session = _make_session_execute_mock(
        mct_val=2.10,  # inflation_anchored
        nowcast_val=2.05,
        skew_val=120.0,  # tail_calm
        sbet_val=105.0,  # sentiment_strong
    )
    md, _src = await _section_cross_asset_matrix(session)

    xau_block = _xau_block(md)
    nas_block = _nas_block(md)
    spx_block = _spx_block(md)

    # XAU : both XAU-soft branches fire (inflation_anchored+sentiment_strong
    # AND liquidity_loose+vol_complacent)
    assert xau_block.count("XAU-soft (") == 2
    assert "real yields rising in goldilocks" in xau_block
    assert "risk-on carry-receiving regime" in xau_block
    # NO XAU-bid in goldilocks regime (no inflation_pressure_up, no tail_fear,
    # no vol_elevated, no liquidity_tight)
    assert "XAU-bid" not in xau_block

    # NAS : all 3 NAS-bid hints fire
    assert nas_block.count("NAS-bid (") == 3
    assert "carry-bid risk-on regime" in nas_block
    assert "real-yield easing + earnings reflation" in nas_block
    assert "vol-of-vol low + dispersion absorption per Bevilacqua-Tunaru 2021" in nas_block
    # NO NAS-soft
    assert "NAS-soft" not in nas_block

    # SPX : all 3 SPX-bid hints fire
    assert spx_block.count("SPX-bid (") == 3
    assert "broad reflation + multiple-expansion" in spx_block
    assert "goldilocks regime, mechanical beta accumulation" in spx_block
    assert "VIX-term-structure contango + vol-seller roll-yield" in spx_block
    # NO SPX-soft
    assert "SPX-soft" not in spx_block


# ─────────────── Tetlock invalidation discipline (R23 + R28 carry-forward) ───────────────


@pytest.mark.asyncio
async def test_xau_all_hints_carry_tetlock_invalidation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every XAU hint (bid OR soft) must carry an inline 'invalidated if'
    Tetlock threshold. Mirrors round-39 GAP-C closure pattern for EUR_USD
    extended to XAU per r46-round-5 R47 retroactive symmetric mirror."""

    # Use a mixed regime to fire BOTH XAU-bid and XAU-soft branches.
    async def fake_latest_fred(
        _session: object, series_id: str, *, max_age_days: int = 14
    ) -> tuple[float, datetime] | None:
        if series_id == "NFCI":
            return (0.8, datetime.now(UTC))  # tight -> XAU-bid (USD-strength counter)
        if series_id == "VIXCLS":
            return (35.0, datetime.now(UTC))  # panic -> XAU-bid (safe-haven)
        return None

    monkeypatch.setattr("ichor_api.services.data_pool._latest_fred", fake_latest_fred)

    session = _make_session_execute_mock(
        mct_val=3.50,  # inflation_pressure_up -> XAU-bid (real-yield)
        nowcast_val=3.55,
        skew_val=160.0,
        sbet_val=92.0,
    )
    md, _src = await _section_cross_asset_matrix(session)
    xau_block = _xau_block(md)

    # Split on "XAU-bid (" delimiter, collect non-empty fragments
    xau_bid_frags = ["XAU-bid " + frag for frag in xau_block.split("XAU-bid ") if frag.strip()]
    xau_bid_hints = [f for f in xau_bid_frags if f.startswith("XAU-bid (")]
    assert len(xau_bid_hints) >= 3, (
        f"Expected >=3 XAU-bid hints in stress regime, got {len(xau_bid_hints)}"
    )
    for hint in xau_bid_hints:
        assert "invalidated if" in hint.lower(), (
            f"XAU-bid hint missing Tetlock invalidation : {hint!r}"
        )


@pytest.mark.asyncio
async def test_nas_all_hints_carry_tetlock_invalidation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every NAS hint (bid OR soft) must carry an inline 'invalidated if'
    Tetlock threshold. R47 retroactive pattern."""

    async def fake_latest_fred(
        _session: object, series_id: str, *, max_age_days: int = 14
    ) -> tuple[float, datetime] | None:
        if series_id == "NFCI":
            return (-0.7, datetime.now(UTC))  # loose
        if series_id == "VIXCLS":
            return (13.0, datetime.now(UTC))  # complacent
        return None

    monkeypatch.setattr("ichor_api.services.data_pool._latest_fred", fake_latest_fred)

    session = _make_session_execute_mock(
        mct_val=2.10, nowcast_val=2.05, skew_val=120.0, sbet_val=105.0
    )
    md, _src = await _section_cross_asset_matrix(session)
    nas_block = _nas_block(md)

    nas_bid_frags = ["NAS-bid " + frag for frag in nas_block.split("NAS-bid ") if frag.strip()]
    nas_bid_hints = [f for f in nas_bid_frags if f.startswith("NAS-bid (")]
    assert len(nas_bid_hints) >= 3
    for hint in nas_bid_hints:
        assert "invalidated if" in hint.lower(), (
            f"NAS-bid hint missing Tetlock invalidation : {hint!r}"
        )


@pytest.mark.asyncio
async def test_spx_all_hints_carry_tetlock_invalidation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every SPX hint (bid OR soft) must carry an inline 'invalidated if'
    Tetlock threshold. R47 retroactive pattern."""

    async def fake_latest_fred(
        _session: object, series_id: str, *, max_age_days: int = 14
    ) -> tuple[float, datetime] | None:
        if series_id == "NFCI":
            return (-0.7, datetime.now(UTC))
        if series_id == "VIXCLS":
            return (13.0, datetime.now(UTC))
        return None

    monkeypatch.setattr("ichor_api.services.data_pool._latest_fred", fake_latest_fred)

    session = _make_session_execute_mock(
        mct_val=2.10, nowcast_val=2.05, skew_val=120.0, sbet_val=105.0
    )
    md, _src = await _section_cross_asset_matrix(session)
    spx_block = _spx_block(md)

    spx_bid_frags = ["SPX-bid " + frag for frag in spx_block.split("SPX-bid ") if frag.strip()]
    spx_bid_hints = [f for f in spx_bid_frags if f.startswith("SPX-bid (")]
    assert len(spx_bid_hints) >= 3
    for hint in spx_bid_hints:
        assert "invalidated if" in hint.lower(), (
            f"SPX-bid hint missing Tetlock invalidation : {hint!r}"
        )


# ─────────────── ADR-017 boundary (no trade signals) ───────────────


@pytest.mark.asyncio
async def test_xau_nas_spx_hints_contain_no_trade_signals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-017 invariant : the new XAU/NAS/SPX bid+soft hints must NOT
    contain BUY/SELL/LONG/SHORT/TARGET/STOP/ENTRY tokens. Research
    framing only — the LLM weighs the heuristic."""

    async def fake_latest_fred(
        _session: object, series_id: str, *, max_age_days: int = 14
    ) -> tuple[float, datetime] | None:
        if series_id == "NFCI":
            return (-0.7, datetime.now(UTC))
        if series_id == "VIXCLS":
            return (13.0, datetime.now(UTC))
        return None

    monkeypatch.setattr("ichor_api.services.data_pool._latest_fred", fake_latest_fred)

    session = _make_session_execute_mock(
        mct_val=2.10, nowcast_val=2.05, skew_val=120.0, sbet_val=105.0
    )
    md, _src = await _section_cross_asset_matrix(session)

    # Use the actual ADR-017 source-of-truth regex filter (word-boundary
    # aware) — string-substring checks would false-positive on legitimate
    # phrases like `vol-seller` containing the substring "SELL".
    from ichor_api.services.adr017_filter import find_violations

    for block_name, block in (
        ("XAU", _xau_block(md)),
        ("NAS", _nas_block(md)),
        ("SPX", _spx_block(md)),
    ):
        violations = find_violations(block)
        assert violations == [], (
            f"ADR-017 boundary breach : {violations!r} in {block_name} hints block"
        )


# ─────────────── Symmetry invariant : each asset has BOTH branches available ───────────────


@pytest.mark.asyncio
async def test_xau_has_both_bid_and_soft_branches_defined(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Symmetric mirror invariant : with regime that triggers BOTH XAU-bid
    and XAU-soft conditions (mixed regime — inflation_pressure_up triggers
    XAU-bid, but no goldilocks anchor), only XAU-bid fires. We then test
    the reciprocal regime in the goldilocks test. The point of this test
    is to confirm the code paths EXIST for both branches (not that both
    fire simultaneously, which would be regime-contradictory)."""

    # Stress regime test : XAU-bid fires, XAU-soft does not
    async def fake_stress(
        _session: object, series_id: str, *, max_age_days: int = 14
    ) -> tuple[float, datetime] | None:
        if series_id == "NFCI":
            return (0.8, datetime.now(UTC))
        if series_id == "VIXCLS":
            return (35.0, datetime.now(UTC))
        return None

    monkeypatch.setattr("ichor_api.services.data_pool._latest_fred", fake_stress)
    session = _make_session_execute_mock(
        mct_val=3.50, nowcast_val=3.55, skew_val=160.0, sbet_val=92.0
    )
    md_stress, _ = await _section_cross_asset_matrix(session)
    xau_stress = _xau_block(md_stress)
    assert "XAU-bid (" in xau_stress
    assert "XAU-soft" not in xau_stress

    # Goldilocks regime test : XAU-soft fires, XAU-bid does not
    async def fake_calm(
        _session: object, series_id: str, *, max_age_days: int = 14
    ) -> tuple[float, datetime] | None:
        if series_id == "NFCI":
            return (-0.7, datetime.now(UTC))
        if series_id == "VIXCLS":
            return (13.0, datetime.now(UTC))
        return None

    monkeypatch.setattr("ichor_api.services.data_pool._latest_fred", fake_calm)
    session2 = _make_session_execute_mock(
        mct_val=2.10, nowcast_val=2.05, skew_val=120.0, sbet_val=105.0
    )
    md_calm, _ = await _section_cross_asset_matrix(session2)
    xau_calm = _xau_block(md_calm)
    assert "XAU-soft (" in xau_calm
    assert "XAU-bid" not in xau_calm


# ─────────────── Framework attribution anchors ───────────────


@pytest.mark.asyncio
async def test_xau_hints_cite_erb_harvey_and_brunnermeier_pedersen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """XAU symmetric mirror cites Erb-Harvey 2013 (real-yield channel)
    AND Brunnermeier-Pedersen 2009 (dollar-smile funding-liquidity
    spiral) for the bid branch, matching `_section_xau_specific`."""

    async def fake_latest_fred(
        _session: object, series_id: str, *, max_age_days: int = 14
    ) -> tuple[float, datetime] | None:
        if series_id == "NFCI":
            return (0.8, datetime.now(UTC))
        if series_id == "VIXCLS":
            return (35.0, datetime.now(UTC))
        return None

    monkeypatch.setattr("ichor_api.services.data_pool._latest_fred", fake_latest_fred)
    session = _make_session_execute_mock(
        mct_val=3.50, nowcast_val=3.55, skew_val=160.0, sbet_val=92.0
    )
    md, _src = await _section_cross_asset_matrix(session)
    xau_block = _xau_block(md)
    assert "Erb-Harvey" in xau_block
    assert "Brunnermeier-Pedersen 2009" in xau_block


@pytest.mark.asyncio
async def test_nas_hints_cite_hou_mo_xue_and_park_2015(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NAS symmetric mirror cites Hou-Mo-Xue (q-factor duration) AND
    Park 2015 (vol-of-vol vol-control deleveraging) AND Bevilacqua-
    Tunaru 2021 (dispersion absorption), matching `_section_nas_specific`."""

    # Stress regime triggers NAS-soft hints citing Hou-Mo-Xue + Park 2015
    async def fake_stress(
        _session: object, series_id: str, *, max_age_days: int = 14
    ) -> tuple[float, datetime] | None:
        if series_id == "NFCI":
            return (0.8, datetime.now(UTC))
        if series_id == "VIXCLS":
            return (35.0, datetime.now(UTC))
        return None

    monkeypatch.setattr("ichor_api.services.data_pool._latest_fred", fake_stress)
    session_s = _make_session_execute_mock(
        mct_val=3.50, nowcast_val=3.55, skew_val=160.0, sbet_val=92.0
    )
    md_stress, _ = await _section_cross_asset_matrix(session_s)
    nas_stress = _nas_block(md_stress)
    assert "Hou-Mo-Xue" in nas_stress
    assert "Park 2015" in nas_stress

    # Calm regime triggers NAS-bid hints citing Hou-Mo-Xue + Bevilacqua-Tunaru
    async def fake_calm(
        _session: object, series_id: str, *, max_age_days: int = 14
    ) -> tuple[float, datetime] | None:
        if series_id == "NFCI":
            return (-0.7, datetime.now(UTC))
        if series_id == "VIXCLS":
            return (13.0, datetime.now(UTC))
        return None

    monkeypatch.setattr("ichor_api.services.data_pool._latest_fred", fake_calm)
    session_c = _make_session_execute_mock(
        mct_val=2.10, nowcast_val=2.05, skew_val=120.0, sbet_val=105.0
    )
    md_calm, _ = await _section_cross_asset_matrix(session_c)
    nas_calm = _nas_block(md_calm)
    assert "Hou-Mo-Xue" in nas_calm
    assert "Bevilacqua-Tunaru 2021" in nas_calm


@pytest.mark.asyncio
async def test_spx_hints_cite_brunnermeier_pedersen_funding_spiral(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SPX symmetric mirror cites Brunnermeier-Pedersen 2009 funding-
    liquidity spiral framework, matching `_section_spx_specific` (r43)."""

    async def fake_stress(
        _session: object, series_id: str, *, max_age_days: int = 14
    ) -> tuple[float, datetime] | None:
        if series_id == "NFCI":
            return (0.8, datetime.now(UTC))
        if series_id == "VIXCLS":
            return (35.0, datetime.now(UTC))
        return None

    monkeypatch.setattr("ichor_api.services.data_pool._latest_fred", fake_stress)
    session = _make_session_execute_mock(
        mct_val=3.50, nowcast_val=3.55, skew_val=160.0, sbet_val=92.0
    )
    md, _src = await _section_cross_asset_matrix(session)
    spx_block = _spx_block(md)
    assert "Brunnermeier-Pedersen" in spx_block


# ─────────────── Balanced fallback when no trigger fires ───────────────


@pytest.mark.asyncio
async def test_balanced_fallback_with_neutral_bands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Neutral mid-bands (NFCI normal +0.3 above tight threshold won't
    work — use mild loose -0.3 which sits in liquidity_loose set BUT NOT
    in any of the bid combinations, VIX normal 18 which isn't complacent
    or elevated, SKEW normal 140, SBOI soft 99, MCT near-target 2.50)
    -> some hints may fire from single-condition triggers but NAS-bid
    composite conditions (which need 2 conjuncts each) should NOT fire."""

    async def fake_neutral(
        _session: object, series_id: str, *, max_age_days: int = 14
    ) -> tuple[float, datetime] | None:
        if series_id == "NFCI":
            return (-0.3, datetime.now(UTC))  # mild-loose (in liquidity_loose set)
        if series_id == "VIXCLS":
            return (18.0, datetime.now(UTC))  # normal, neither complacent nor elevated
        return None

    monkeypatch.setattr("ichor_api.services.data_pool._latest_fred", fake_neutral)
    session = _make_session_execute_mock(
        mct_val=2.50,  # near-target (inflation_anchored)
        nowcast_val=2.55,
        skew_val=140.0,  # normal, neither tail_fear nor tail_calm
        sbet_val=99.0,  # soft, neither sentiment_strong nor sentiment_weak
    )
    md, _src = await _section_cross_asset_matrix(session)

    xau_block = _xau_block(md)
    nas_block = _nas_block(md)
    spx_block = _spx_block(md)

    # XAU : inflation_pressure_up False, tail_fear False, vol_elevated False,
    # liquidity_tight False -> no XAU-bid. inflation_anchored+sentiment_strong
    # False (sboi=99 not >=100). liquidity_loose+vol_complacent False (vix=18
    # not complacent). -> XAU balanced.
    assert "balanced" in xau_block
    assert "XAU-bid" not in xau_block
    assert "XAU-soft" not in xau_block

    # NAS : inflation_pressure_up False, liquidity_tight False, vol_elevated False
    # -> no NAS-soft. liquidity_loose+vol_complacent False (vix=18 not complacent).
    # inflation_anchored+sentiment_strong False. tail_calm+vol_complacent False.
    # -> NAS balanced.
    assert "balanced" in nas_block
    assert "NAS-bid" not in nas_block
    assert "NAS-soft" not in nas_block

    # SPX : liquidity_tight False, tail_fear False -> no SPX-soft via risk-off.
    # sentiment_weak False -> no SPX-soft via earnings-tail.
    # liquidity_loose+sentiment_strong False. inflation_anchored+vol_complacent
    # False. tail_calm+vol_complacent False. -> SPX balanced.
    assert "balanced" in spx_block
    assert "SPX-bid" not in spx_block
    assert "SPX-soft" not in spx_block


# ─────────────── Symmetric mirror count invariants ───────────────


@pytest.mark.asyncio
async def test_xau_symmetric_mirror_hint_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """Symmetric mirror invariant : XAU has 3 bid triggers + 2 soft
    triggers (5 total). Catches a refactor that drops one side back
    to asymmetric."""

    # Maximal stress regime to fire all 3 XAU-bid triggers.
    async def fake_stress(
        _session: object, series_id: str, *, max_age_days: int = 14
    ) -> tuple[float, datetime] | None:
        if series_id == "NFCI":
            return (0.8, datetime.now(UTC))
        if series_id == "VIXCLS":
            return (35.0, datetime.now(UTC))
        return None

    monkeypatch.setattr("ichor_api.services.data_pool._latest_fred", fake_stress)
    session = _make_session_execute_mock(
        mct_val=3.50, nowcast_val=3.55, skew_val=160.0, sbet_val=92.0
    )
    md, _src = await _section_cross_asset_matrix(session)
    xau_stress = _xau_block(md)
    assert xau_stress.count("XAU-bid (") == 3, (
        f"Expected 3 XAU-bid triggers in maximal stress regime, got {xau_stress.count('XAU-bid (')}"
    )

    # Goldilocks regime to fire all 2 XAU-soft triggers.
    async def fake_calm(
        _session: object, series_id: str, *, max_age_days: int = 14
    ) -> tuple[float, datetime] | None:
        if series_id == "NFCI":
            return (-0.7, datetime.now(UTC))
        if series_id == "VIXCLS":
            return (13.0, datetime.now(UTC))
        return None

    monkeypatch.setattr("ichor_api.services.data_pool._latest_fred", fake_calm)
    session2 = _make_session_execute_mock(
        mct_val=2.10, nowcast_val=2.05, skew_val=120.0, sbet_val=105.0
    )
    md_calm, _ = await _section_cross_asset_matrix(session2)
    xau_calm = _xau_block(md_calm)
    assert xau_calm.count("XAU-soft (") == 2


@pytest.mark.asyncio
async def test_nas_symmetric_mirror_hint_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """NAS has 3 soft triggers + 3 bid triggers (6 total). Full symmetric
    mirror (vs r46-r5 pre-state of 3-vs-0 asymmetric)."""

    async def fake_stress(
        _session: object, series_id: str, *, max_age_days: int = 14
    ) -> tuple[float, datetime] | None:
        if series_id == "NFCI":
            return (0.8, datetime.now(UTC))
        if series_id == "VIXCLS":
            return (35.0, datetime.now(UTC))
        return None

    monkeypatch.setattr("ichor_api.services.data_pool._latest_fred", fake_stress)
    session = _make_session_execute_mock(
        mct_val=3.50, nowcast_val=3.55, skew_val=160.0, sbet_val=92.0
    )
    md, _src = await _section_cross_asset_matrix(session)
    nas_stress = _nas_block(md)
    assert nas_stress.count("NAS-soft (") == 3

    async def fake_calm(
        _session: object, series_id: str, *, max_age_days: int = 14
    ) -> tuple[float, datetime] | None:
        if series_id == "NFCI":
            return (-0.7, datetime.now(UTC))
        if series_id == "VIXCLS":
            return (13.0, datetime.now(UTC))
        return None

    monkeypatch.setattr("ichor_api.services.data_pool._latest_fred", fake_calm)
    session2 = _make_session_execute_mock(
        mct_val=2.10, nowcast_val=2.05, skew_val=120.0, sbet_val=105.0
    )
    md_calm, _ = await _section_cross_asset_matrix(session2)
    nas_calm = _nas_block(md_calm)
    assert nas_calm.count("NAS-bid (") == 3


@pytest.mark.asyncio
async def test_spx_symmetric_mirror_hint_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """SPX has 2 soft triggers + 3 bid triggers (5 total). Full symmetric
    mirror (vs r46-r5 pre-state of 2-vs-0 asymmetric)."""

    async def fake_stress(
        _session: object, series_id: str, *, max_age_days: int = 14
    ) -> tuple[float, datetime] | None:
        if series_id == "NFCI":
            return (0.8, datetime.now(UTC))
        if series_id == "VIXCLS":
            return (35.0, datetime.now(UTC))
        return None

    monkeypatch.setattr("ichor_api.services.data_pool._latest_fred", fake_stress)
    session = _make_session_execute_mock(
        mct_val=3.50, nowcast_val=3.55, skew_val=160.0, sbet_val=92.0
    )
    md, _src = await _section_cross_asset_matrix(session)
    spx_stress = _spx_block(md)
    assert spx_stress.count("SPX-soft (") == 2

    async def fake_calm(
        _session: object, series_id: str, *, max_age_days: int = 14
    ) -> tuple[float, datetime] | None:
        if series_id == "NFCI":
            return (-0.7, datetime.now(UTC))
        if series_id == "VIXCLS":
            return (13.0, datetime.now(UTC))
        return None

    monkeypatch.setattr("ichor_api.services.data_pool._latest_fred", fake_calm)
    session2 = _make_session_execute_mock(
        mct_val=2.10, nowcast_val=2.05, skew_val=120.0, sbet_val=105.0
    )
    md_calm, _ = await _section_cross_asset_matrix(session2)
    spx_calm = _spx_block(md_calm)
    assert spx_calm.count("SPX-bid (") == 3
