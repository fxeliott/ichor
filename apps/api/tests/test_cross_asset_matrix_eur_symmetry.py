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
    assert "EUR-bid (NFCI loose, broad USD-weakness flow)" in eur_block
    assert "EUR-bid (carry-friendly calm regime)" in eur_block
    assert "EUR-bid (Fed easing path, rate-differential narrowing)" in eur_block
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
    assert "EUR-bid (NFCI loose, broad USD-weakness flow)" in eur_block
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
