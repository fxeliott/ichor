"""Unit tests for `_section_gbp_specific` — Round-90 (ADR-101, ADR-099 Tier 2).

Verifies the GBP/USD UK-US rate-differential + sterling-risk-premium
data-pool section (mirror of the JPY r45 2-driver template) :
  1. Asset gate : non-GBP_USD assets return ("", []) without DB I/O.
  2. Empty IRLTLT01GBM156N → silent skip (primary UK anchor absent).
  3. UK10Y-only path (no DGS10) renders UK anchor only.
  4. Full 2-driver path renders both blocks + differential + composite.
  5. US-UK differential computed correctly (DGS10 - IRLTLT01GBM156N),
     incl. the NEGATIVE-differential sterling-rate-advantage regime.
  6. ADR-017 boundary preserved on rendered text.
  7. Symmetric language doctrine (GBP-soft + GBP-bid branches both present).
  8. Tetlock invalidation thresholds visible on the differential reading.
  9. Frequency mismatch warning emitted inline (BTP r34 precedent).
 10. R44 sign-convention : GBP/USD polarity (USD is the quote currency,
     INVERSE to USD/JPY) stated explicitly — the r40 GBP-bug class guard.
 11. Driver-3 deferral + safe-haven caveat surfaced with correct DOIs.
 12. R24 SUBSET-not-SUPERSET documented inline (cadence-mismatch BTP r34).

Uses _latest_fred monkeypatch (2 FRED series in sequence). Zero DB I/O
on the asset-gate fail path.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest
from ichor_api.services.adr017_filter import is_adr017_clean
from ichor_api.services.data_pool import _section_gbp_specific


def _make_fred_stub(uk10y=None, dgs10=None):
    """Build a _latest_fred replacement returning canned values per
    series_id. None means "series not available" (returns None)."""

    async def _stub(session, series_id, max_age_days=None):
        if series_id == "IRLTLT01GBM156N":
            return uk10y
        if series_id == "DGS10":
            return dgs10
        return None

    return _stub


# ──────────────────────────── Asset gate ──────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "asset",
    [
        "EUR_USD",
        "USD_JPY",
        "USD_CAD",
        "AUD_USD",
        "XAU_USD",
        "NAS100_USD",
        "SPX500_USD",
    ],
)
async def test_returns_empty_on_non_gbp_asset(asset: str) -> None:
    """Asset gate : only GBP_USD renders. Zero DB I/O on non-GBP assets."""
    session = AsyncMock()
    md, sources = await _section_gbp_specific(session, asset)
    assert md == ""
    assert sources == []
    assert session.execute.await_count == 0


# ──────────────────────────── Empty UK10Y path ─────────────────────────


@pytest.mark.asyncio
async def test_returns_empty_when_uk10y_missing(monkeypatch) -> None:
    """Empty IRLTLT01GBM156N → silent skip (UK 10Y is the PRIMARY
    GBP-specific anchor ; without it the section refuses to render even
    if DGS10 has data)."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(uk10y=None, dgs10=(4.45, date(2026, 5, 13))),
    )
    session = AsyncMock()
    md, sources = await _section_gbp_specific(session, "GBP_USD")
    assert md == ""
    assert sources == []


# ──────────────────────────── UK10Y-only path ──────────────────────────


@pytest.mark.asyncio
async def test_renders_uk10y_only_when_dgs10_missing(monkeypatch) -> None:
    """UK10Y populated but DGS10 absent → section renders the UK anchor
    only (graceful degradation, no differential block, no composite)."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(uk10y=(4.20, date(2026, 4, 1)), dgs10=None),
    )
    session = AsyncMock()
    md, sources = await _section_gbp_specific(session, "GBP_USD")
    assert "UK 10Y = 4.20%" in md
    assert "OECD MEI monthly" in md
    assert "DGS10 = " not in md  # no differential block
    assert "rate-differential triangle" not in md  # no composite
    assert sources == ["FRED:IRLTLT01GBM156N@2026-04-01"]


# ──────────────────────────── Full 2-driver path ───────────────────────


@pytest.mark.asyncio
async def test_renders_full_triangle_when_both_drivers_present(monkeypatch) -> None:
    """UK10Y + DGS10 both populated → renders both blocks + differential
    + composite triangle + 2 source-stamps."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            uk10y=(4.20, date(2026, 4, 1)),
            dgs10=(4.45, date(2026, 5, 13)),
        ),
    )
    session = AsyncMock()
    md, sources = await _section_gbp_specific(session, "GBP_USD")
    assert "UK 10Y = 4.20%" in md
    assert "DGS10 = 4.45%" in md
    # Differential computed (4.45 - 4.20 = +0.25)
    assert "US-UK 10Y differential = +0.25 pp" in md
    assert "Frequency mismatch" in md
    assert "MONTHLY" in md
    assert "rate-differential triangle" in md
    assert "Engel-West" in md
    assert "Della Corte" in md
    assert "FRED:IRLTLT01GBM156N@2026-04-01" in sources
    assert "FRED:DGS10@2026-05-13" in sources
    assert len(sources) == 2


# ──────────────────────────── Differential math ────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("dgs10_value", "uk10y_value", "expected_diff_str"),
    [
        (4.45, 4.20, "+0.25 pp"),  # US slightly above UK
        (4.47, 4.82, "-0.35 pp"),  # real 2026-05 print : sterling rate ADVANTAGE
        (5.20, 3.80, "+1.40 pp"),  # wide US-bid scenario
        (4.10, 4.05, "+0.05 pp"),  # near-parity tail
    ],
)
async def test_differential_computed_correctly(
    monkeypatch, dgs10_value: float, uk10y_value: float, expected_diff_str: str
) -> None:
    """4 scenarios : differential = DGS10 - UK 10Y, signed `+/-X.XX pp`.
    Includes the NEGATIVE-differential (sterling rate-advantage) regime."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            uk10y=(uk10y_value, date(2026, 4, 1)),
            dgs10=(dgs10_value, date(2026, 5, 13)),
        ),
    )
    session = AsyncMock()
    md, _ = await _section_gbp_specific(session, "GBP_USD")
    assert expected_diff_str in md


# ──────────────────────────── ADR-017 boundary ─────────────────────────


@pytest.mark.asyncio
async def test_rendered_text_passes_adr017_filter(monkeypatch) -> None:
    """Full-render text MUST pass the r32 hardened ADR-017 filter."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            uk10y=(4.20, date(2026, 4, 1)),
            dgs10=(4.45, date(2026, 5, 13)),
        ),
    )
    session = AsyncMock()
    md, _ = await _section_gbp_specific(session, "GBP_USD")
    assert is_adr017_clean(md), "ADR-017 violation in r90 _section_gbp_specific output."


# ──────────────────────────── Symmetric language doctrine ──────────────


@pytest.mark.asyncio
async def test_symmetric_GBP_soft_and_GBP_bid_branches_emitted(monkeypatch) -> None:
    """ichor-trader r32/r41/r42/r43 carry-forward : the differential
    interpretive section emits BOTH GBP-soft (USD-bid carry regime) AND
    GBP-bid (sterling rate-advantage regime) branches."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            uk10y=(4.20, date(2026, 4, 1)),
            dgs10=(4.45, date(2026, 5, 13)),
        ),
    )
    session = AsyncMock()
    md, _ = await _section_gbp_specific(session, "GBP_USD")
    assert "GBP-soft" in md
    assert "GBP-bid" in md
    md_lower = md.lower()
    assert "carry-bid" in md_lower  # calm-regime branch
    # stress-regime branch (post-r90 ichor-trader YELLOW-1 honest reframe:
    # "UK funding stress" / "2022 LDI/gilt-crisis", no longer "gilt-stress")
    assert "funding stress" in md_lower or "gilt-crisis" in md_lower
    assert "risk-off" in md_lower


# ──────────────────────────── Tetlock invalidation ─────────────────────


@pytest.mark.asyncio
async def test_tetlock_invalidation_thresholds_visible(monkeypatch) -> None:
    """r42 R28 + r43 carry-forward : the differential interpretation
    MUST emit explicit Tetlock invalidation lines with VIX cross-
    confirmation thresholds."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            uk10y=(4.20, date(2026, 4, 1)),
            dgs10=(4.45, date(2026, 5, 13)),
        ),
    )
    session = AsyncMock()
    md, _ = await _section_gbp_specific(session, "GBP_USD")
    assert "Tetlock invalidation" in md
    assert "VIX > 25" in md
    assert "narrows by " in md
    assert "VIX falls below 18" in md


# ──────────────────────────── Frequency mismatch warning ───────────────


@pytest.mark.asyncio
async def test_frequency_mismatch_warning_emitted(monkeypatch) -> None:
    """BTP r34 cadence-mismatch precedent : the section MUST surface the
    daily/monthly cadence mismatch inline so the LLM treats the
    differential as a REGIME indicator, not an intraday signal."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            uk10y=(4.20, date(2026, 4, 1)),
            dgs10=(4.45, date(2026, 5, 13)),
        ),
    )
    session = AsyncMock()
    md, _ = await _section_gbp_specific(session, "GBP_USD")
    assert "Frequency mismatch" in md
    assert "DGS10 is DAILY" in md
    assert "UK 10Y is MONTHLY" in md
    assert "REGIME indicator" in md
    assert "BTP r34 precedent" in md


# ──────────────────────────── R44 sign-convention polarity ─────────────


@pytest.mark.asyncio
async def test_polarity_sign_convention_stated(monkeypatch) -> None:
    """R44 sign-convention discipline (the r40 GBP-bug class) : GBP/USD
    quotes USD per GBP, so a WIDER US-UK differential is GBP-soft — the
    INVERSE polarity to USD/JPY. The section MUST state this explicitly
    so the Pass-2 LLM cannot mis-apply the JPY-class reading to GBP."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            uk10y=(4.20, date(2026, 4, 1)),
            dgs10=(4.45, date(2026, 5, 13)),
        ),
    )
    session = AsyncMock()
    md, _ = await _section_gbp_specific(session, "GBP_USD")
    assert "QUOTE currency" in md
    assert "OPPOSITE to USD/JPY" in md
    assert "GBP/USD DOWNSIDE (GBP-soft)" in md
    assert "ADR-101" in md


@pytest.mark.asyncio
async def test_polarity_binds_both_sign_directions(monkeypatch) -> None:
    """r40-bug-class regression guard (ichor-trader r90 recommended) : the
    polarity statement MUST bind BOTH sign directions verbatim — a WIDER/
    positive US-UK differential → GBP-soft AND a NARROWER/NEGATIVE
    differential → GBP-bid. `test_differential_computed_correctly` only
    checks the `+/-X.XX pp` string ; this pins the sign→direction mapping
    itself (the exact gap the r40 GBP bug slipped through). Feeds the real
    2026-05 print (DGS10 4.47 / UK10Y 4.82 = -0.35 pp = UK rate advantage)."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            uk10y=(4.82, date(2026, 4, 1)),
            dgs10=(4.47, date(2026, 5, 13)),
        ),
    )
    session = AsyncMock()
    md, _ = await _section_gbp_specific(session, "GBP_USD")
    # Wider/positive differential → GBP-soft (USD-bid ; USD is the quote ccy)
    assert (
        "A WIDER (more positive) US-UK differential is USD-bid → GBP/USD DOWNSIDE (GBP-soft)" in md
    )
    # Narrower/NEGATIVE differential (the real current regime) → GBP-bid
    assert (
        "a NARROWER or NEGATIVE differential (UK yield ≥ US) is a sterling rate advantage → GBP-bid"
        in md
    )
    # The real 2026-05 print computes a negative differential
    assert "US-UK 10Y differential = -0.35 pp" in md


# ──────────────────────────── Deferred Driver-3 + safe-haven caveat ────


@pytest.mark.asyncio
async def test_deferred_driver3_and_safe_haven_caveat(monkeypatch) -> None:
    """Honest scope discipline (r88 anti-over-claim) : the BoE-vs-Fed
    Driver 3 (Clarida-Gali-Gertler 1998) is surfaced as DEFERRED (needs
    the unpolled IR3TIB01GBM156N) and sterling's NON-safe-haven status
    is a one-line caveat (Ranaldo-Soderlind 2010), each with correct DOIs."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            uk10y=(4.20, date(2026, 4, 1)),
            dgs10=(4.45, date(2026, 5, 13)),
        ),
    )
    session = AsyncMock()
    md, _ = await _section_gbp_specific(session, "GBP_USD")
    # Safe-haven caveat (NOT a driver)
    assert "Ranaldo-Soderlind 2010" in md
    assert "10.1093/rof/rfq007" in md
    assert "NOT a USD safe-haven" in md
    # Deferred Driver 3
    assert "Clarida-Gali-Gertler 1998" in md
    assert "10.1016/S0014-2921(98)00016-6" in md
    assert "IR3TIB01GBM156N" in md
    assert "DEFERRED" in md
    # Shipped framework DOIs
    assert "10.1086/429137" in md  # Engel-West
    assert "10.1162/REST_a_00157" in md  # Della Corte-Sarno-Sestieri


# ──────────────────────────── R24 SUBSET-not-SUPERSET ──────────────────


@pytest.mark.asyncio
async def test_r24_subset_not_superset_documented_inline(monkeypatch) -> None:
    """R24 discipline (r40 codified) : the composite triangle MUST
    document the cadence-mismatch reasoning inline, citing BTP r34 as
    the precedent."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            uk10y=(4.20, date(2026, 4, 1)),
            dgs10=(4.45, date(2026, 5, 13)),
        ),
    )
    session = AsyncMock()
    md, _ = await _section_gbp_specific(session, "GBP_USD")
    assert "R24 SUBSET-not-SUPERSET" in md
    assert "cadence-mismatch" in md
    assert "BTP r34 precedent" in md
