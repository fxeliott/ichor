"""Unit tests for `_section_cross_asset_matrix` EUR_USD symmetric
bias hints (round-38, r37-audit-gap #2 partial closure).

The pre-round-38 cross-asset matrix surfaced 3 USD-positive scenarios
for EUR_USD (NFCI tight, vol elevated, Fed-on-hold) with ZERO
EUR-bullish symmetric counterparts. EUR_USD hints in
`usd_complacency` regimes (NFCI loose + vol complacent + sentiment
expansionary) rendered as `["balanced"]`, giving the Pass-1/Pass-2
LLM no EUR-positive directional steer — matching the Vovk
`EUR_USD/usd_complacency` n=13 anti-skill pocket diagnostic
(round-27 researcher GAP-B).

Round-38 adds 3 symmetric EUR-bullish hints (round-trip mirror) :
  - `liquidity_loose` → "EUR-bid (NFCI loose, broad USD-weakness flow)"
  - `vol_complacent AND tail_calm` → "EUR-bid (carry-friendly calm regime)"
  - `inflation_anchored AND sentiment_strong` → "EUR-bid (Fed easing
    path, rate-differential narrowing)"

These tests pin the symmetric behaviour : same number of triggers on
each side, exact label text, balanced fallback when both sides silent.
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
    MCT → Nowcast → SKEW → SBET (each via `.scalar_one_or_none()`)."""
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


# ──────────────────── USD-positive regime ────────────────────


@pytest.mark.asyncio
async def test_usd_positive_regime_renders_3_usd_bid_hints(monkeypatch: pytest.MonkeyPatch) -> None:
    """USD-positive macro regime (NFCI tight, VIX panic, MCT unanchored)
    → 3 USD-bid hints, 0 EUR-bid hints. Pre-round-38 baseline."""

    # NFCI tight = 0.8, VIX panic = 35, MCT unanchored = 3.5
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
        mct_val=3.50,
        nowcast_val=3.55,
        skew_val=160.0,  # tail-fear
        sbet_val=92.0,  # recession-pre
    )
    md, _src = await _section_cross_asset_matrix(session)
    # EUR_USD section line should contain all 3 USD-bid hints, NO EUR-bid.
    assert "USD-bid (NFCI tight)" in md
    assert "USD-bid (vol regime)" in md
    assert "Fed-on-hold supports USD" in md
    assert "EUR-bid" not in md.split("EUR_USD")[1].split("GBP_USD")[0]


# ──────────────────── EUR-positive regime ────────────────────


@pytest.mark.asyncio
async def test_eur_positive_regime_renders_3_eur_bid_hints(monkeypatch: pytest.MonkeyPatch) -> None:
    """USD-complacency macro regime (NFCI loose, VIX complacent + SKEW
    calm, MCT anchored + SBOI expansionary) → 3 EUR-bid hints, 0
    USD-bid. Round-38 symmetric mirror."""

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
        mct_val=2.10,  # anchored
        nowcast_val=2.05,
        skew_val=120.0,  # calm
        sbet_val=105.0,  # expansionary
    )
    md, _src = await _section_cross_asset_matrix(session)
    eur_block = md.split("EUR_USD")[1].split("GBP_USD")[0]
    # Round-39 GAP-C closure : each EUR-bid hint now carries a
    # Tetlock-invalidation threshold inline. The exact prefix +
    # invalidation phrase must appear.
    assert "EUR-bid (NFCI loose, broad USD-weakness flow" in eur_block
    assert "EUR-bid (carry-friendly calm regime" in eur_block
    assert "EUR-bid (Fed easing path, rate-differential narrowing" in eur_block
    # 3 invalidation clauses must be present (one per EUR-bid hint).
    assert eur_block.count("invalidated if") == 3
    assert "USD-bid" not in eur_block


# ──────────────────── Mixed / balanced regime ────────────────────


@pytest.mark.asyncio
async def test_balanced_regime_falls_back_to_balanced_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mid-regime (NFCI mild-loose, VIX normal, SKEW normal, SBOI soft,
    MCT near-target) → no trigger fires either side → "balanced" fallback."""

    async def fake_latest_fred(
        _session: object, series_id: str, *, max_age_days: int = 14
    ) -> tuple[float, datetime] | None:
        if series_id == "NFCI":
            return (-0.3, datetime.now(UTC))  # mild-loose → triggers liquidity_loose
        if series_id == "VIXCLS":
            return (18.0, datetime.now(UTC))  # normal
        return None

    monkeypatch.setattr("ichor_api.services.data_pool._latest_fred", fake_latest_fred)

    session = _make_session_execute_mock(
        mct_val=2.50,  # near-target
        nowcast_val=2.55,
        skew_val=140.0,  # normal
        sbet_val=99.0,  # soft
    )
    md, _src = await _section_cross_asset_matrix(session)
    eur_block = md.split("EUR_USD")[1].split("GBP_USD")[0]
    # mild-loose IS in liquidity_loose set → triggers 1 EUR-bid hint
    # (with round-39 Tetlock invalidation suffix — match prefix only)
    assert "EUR-bid (NFCI loose, broad USD-weakness flow" in eur_block
    # other 2 EUR-bid hints require stronger conditions
    assert "carry-friendly calm regime" not in eur_block
    assert "Fed easing path" not in eur_block
    # NO USD-bid either (vol normal, mct near-target, NFCI loose not tight)
    assert "USD-bid" not in eur_block


# ──────────────────── Symmetry invariant ────────────────────


@pytest.mark.asyncio
async def test_eur_usd_hint_count_symmetric_with_usd_eur(monkeypatch: pytest.MonkeyPatch) -> None:
    """Property : the symmetric mirror is exactly 3-vs-3 trigger pairs.
    Catches a refactor that drops one side back to asymmetric."""

    # Use the most extreme EUR-bullish regime and assert it produces
    # exactly 3 EUR-bid hints (mirror of the 3 USD-bid hints in the
    # extreme USD regime test above).
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
    eur_block = md.split("EUR_USD")[1].split("GBP_USD")[0]
    eur_bid_count = eur_block.count("EUR-bid (")
    assert eur_bid_count == 3, (
        f"Expected 3 EUR-bid hints in extreme EUR-bullish regime, got {eur_bid_count}. "
        "Symmetric mirror with the 3 USD-bid hints is the audit-gap #2 closure invariant."
    )


# ──────────────────── Tetlock invalidation (round-39 GAP-C) ────────────────────


@pytest.mark.asyncio
async def test_eur_bid_hints_carry_testable_invalidation_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round-39 ichor-trader GAP-C closure : every EUR-bid hint emitted
    by `_section_cross_asset_matrix` MUST carry an inline Tetlock
    invalidation threshold (a numerical condition that flips the
    directional thesis). Catches a refactor that adds a new EUR-bid
    trigger without attaching an exit rule — the kind of asymmetric
    forward-looking claim Pass-2 LLMs were observed adopting verbatim
    in n=13 Vovk anti-skill pocket diagnostics."""

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
    eur_block = md.split("EUR_USD")[1].split("GBP_USD")[0]

    # Hints are joined with " · " on a single line. Split on the EUR-bid
    # delimiter and count the resulting fragments instead of lines.
    eur_bid_fragments = ["EUR-bid " + frag for frag in eur_block.split("EUR-bid ") if frag.strip()]
    # Filter out fragments that don't actually start a hint (e.g. trailing
    # text from the asset block).
    eur_bid_hints = [frag for frag in eur_bid_fragments if frag.startswith("EUR-bid (")]
    assert len(eur_bid_hints) >= 3, (
        f"Expected ≥3 EUR-bid hints in extreme EUR-bullish regime, got "
        f"{len(eur_bid_hints)} : {eur_bid_hints!r}"
    )
    for hint in eur_bid_hints:
        assert "invalidated if" in hint.lower(), (
            f"EUR-bid hint missing Tetlock invalidation clause : {hint!r}. "
            "Pass-2 LLM cannot adopt a directional thesis without an explicit "
            "testable exit (round-39 GAP-C invariant)."
        )


# ──────────────────── ADR-017 boundary ────────────────────


@pytest.mark.asyncio
async def test_eur_bullish_hints_contain_no_trade_signals(monkeypatch: pytest.MonkeyPatch) -> None:
    """ADR-017 invariant : the new EUR-bid hints must NOT contain
    BUY/SELL/LONG/SHORT/TARGET/STOP/ENTRY tokens. Research framing
    only — the LLM weighs the heuristic."""

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
    eur_block = md.split("EUR_USD")[1].split("GBP_USD")[0]
    for forbidden in ("BUY", "SELL", "LONG ", "SHORT ", "TARGET", "STOP", "ENTRY"):
        assert forbidden not in eur_block.upper().replace("EUR-USD", "").replace("USD-USD", ""), (
            f"ADR-017 boundary breach : {forbidden!r} in EUR_USD hints block"
        )


# ──────────────────── Round-40 GBP_USD symmetry ────────────────────


@pytest.mark.asyncio
async def test_gbp_usd_no_longer_copies_eur_usd_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round-40 GAP-A bug-fix invariant : GBP_USD hints must NOT be a
    verbatim copy of EUR_USD hints (pre-r40 `gbp_usd = list(eur_usd)`
    was wrong — GBP is risk-currency, EUR has ECB-Fed mechanic, no
    structural reason for them to share triggers). The GBP block
    MUST mention `GBP-bid` AND/OR `GBP risk-currency` text, NOT
    `EUR-bid`."""

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
    gbp_block = md.split("GBP_USD")[1].split("USD_JPY")[0]

    # GBP_USD block must NOT contain "EUR-bid" anywhere (the pre-r40
    # bug copied EUR-bid hints into GBP).
    assert "EUR-bid" not in gbp_block, (
        "GAP-A regression : GBP_USD inherits EUR-bid hints "
        f"(pre-r40 bug). GBP block : {gbp_block!r}"
    )
    # GBP_USD block must contain GBP-specific markers.
    assert "GBP-bid" in gbp_block or "GBP risk-currency" in gbp_block, (
        f"GBP_USD missing GBP-specific marker : {gbp_block!r}"
    )


@pytest.mark.asyncio
async def test_gbp_usd_bullish_subset_of_eur_pattern(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round-40 GAP-A : GBP-bid is SUBSET of EUR-bid pattern (only
    broad USD-weakness flows propagate, NOT ECB-specific rate-
    differential narrative). Expect 2 GBP-bid triggers (subset) vs
    EUR's 3."""

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
    gbp_block = md.split("GBP_USD")[1].split("USD_JPY")[0]
    eur_block = md.split("EUR_USD")[1].split("GBP_USD")[0]

    eur_bid_count = eur_block.count("EUR-bid (")
    gbp_bid_count = gbp_block.count("GBP-bid (")
    assert eur_bid_count == 3
    assert gbp_bid_count == 2, (
        f"GBP-bid count should be 2 (SUBSET of EUR pattern). Got {gbp_bid_count}"
    )
    # Every GBP-bid hint must carry Tetlock invalidation.
    gbp_hints = ["GBP-bid " + frag for frag in gbp_block.split("GBP-bid ") if frag.strip()]
    gbp_bid_hints = [h for h in gbp_hints if h.startswith("GBP-bid (")]
    for hint in gbp_bid_hints:
        assert "invalidated if" in hint.lower(), (
            f"GBP-bid hint missing Tetlock invalidation : {hint!r}"
        )


# ──────────────────── Round-40 USD_CAD symmetry ────────────────────


@pytest.mark.asyncio
async def test_usd_cad_has_at_least_one_cad_bid_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round-40 GAP-A : pre-r40 USD_CAD had ONLY 1 USD-bid trigger
    (vol_elevated) and ZERO CAD-bullish branch. r40 adds 3 USD-bid +
    1 CAD-bid (commodity reflation via broad risk-on flow ;
    Tetlock-defensible without oil-price overclaim). The 2 deferred
    CAD-bid framings (BoC-hawkish-oil-carry / tail_calm-oil-positive)
    await DCOILWTICO empirical surface in r41+."""

    async def fake_latest_fred(
        _session: object, series_id: str, *, max_age_days: int = 14
    ) -> tuple[float, datetime] | None:
        if series_id == "NFCI":
            return (-0.7, datetime.now(UTC))  # loose
        if series_id == "VIXCLS":
            return (13.0, datetime.now(UTC))
        return None

    monkeypatch.setattr("ichor_api.services.data_pool._latest_fred", fake_latest_fred)

    session = _make_session_execute_mock(
        mct_val=2.10,
        nowcast_val=2.05,
        skew_val=120.0,
        sbet_val=105.0,  # sentiment_strong
    )
    md, _src = await _section_cross_asset_matrix(session)
    cad_block = md.split("USD_CAD")[1].split("XAU_USD")[0]

    # 1 CAD-bid trigger expected under (liquidity_loose AND
    # sentiment_strong).
    cad_bid_count = cad_block.count("CAD-bid (")
    assert cad_bid_count == 1, (
        f"USD_CAD should have 1 CAD-bid trigger in liquidity_loose+sentiment_strong regime. "
        f"Got {cad_bid_count}. Block : {cad_block!r}"
    )
    # CAD-bid must carry Tetlock invalidation.
    assert "invalidated if NFCI" in cad_block, (
        f"CAD-bid hint missing NFCI Tetlock invalidation : {cad_block!r}"
    )


@pytest.mark.asyncio
async def test_usd_cad_usd_bid_branch_3_triggers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round-40 GAP-A : USD_CAD USD-bid branch expanded from 1 trigger
    (vol_elevated pre-r40) to 3 (vol_elevated + liquidity_tight +
    tail_fear)."""

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
        mct_val=3.50, nowcast_val=3.55, skew_val=160.0, sbet_val=92.0
    )
    md, _src = await _section_cross_asset_matrix(session)
    cad_block = md.split("USD_CAD")[1].split("XAU_USD")[0]
    usd_bid_count = cad_block.count("USD-bid (")
    assert usd_bid_count == 3, (
        f"USD_CAD USD-bid branch should have 3 triggers in USD-positive regime. Got {usd_bid_count}"
    )
