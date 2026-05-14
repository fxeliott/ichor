"""Unit tests for `_section_jpy_specific` — Round-45 GAP-A continuation 4/5.

Verifies the USD/JPY US-JP rate-differential data-pool section :
  1. Asset gate : non-USD_JPY assets return ("", []) without DB I/O.
  2. Empty IRLTLT01JPM156N → silent skip (primary JPY anchor absent).
  3. JP10Y-only path (no DGS10) renders Japan anchor only.
  4. Full 2-driver path renders both blocks + differential + composite triangle.
  5. Composite triangle absent when DGS10 missing.
  6. US-JP differential computed correctly (DGS10 - IRLTLT01JPM156N).
  7. Source-stamp format pinned (FRED:IRLTLT01JPM156N@*, FRED:DGS10@*).
  8. ADR-017 boundary preserved on rendered text.
  9. Symmetric language doctrine (USD-bid + JPY-bid branches both present).
 10. Tetlock invalidation thresholds visible on the rate-differential reading.
 11. Frequency mismatch warning emitted inline (BTP r34 precedent).
 12. Ito-Yabu 2007 DOI referenced for ADR-095 intervention deferral.

Uses _latest_fred monkeypatch (for 2 FRED series in sequence). Zero DB I/O
on asset-gate fail path.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest
from ichor_api.services.adr017_filter import is_adr017_clean
from ichor_api.services.data_pool import _section_jpy_specific


def _make_fred_stub(jp10y=None, dgs10=None):
    """Build a _latest_fred replacement that returns canned values per
    series_id. None means "series not available" (returns None)."""

    async def _stub(session, series_id, max_age_days=None):
        if series_id == "IRLTLT01JPM156N":
            return jp10y
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
        "GBP_USD",
        "USD_CAD",
        "AUD_USD",
        "XAU_USD",
        "NAS100_USD",
        "SPX500_USD",
    ],
)
async def test_returns_empty_on_non_jpy_asset(asset: str) -> None:
    """Asset gate : only USD_JPY renders. Zero DB I/O on non-JPY assets."""
    session = AsyncMock()
    md, sources = await _section_jpy_specific(session, asset)
    assert md == ""
    assert sources == []
    assert session.execute.await_count == 0


# ──────────────────────────── Empty JP10Y path ─────────────────────────


@pytest.mark.asyncio
async def test_returns_empty_when_jp10y_missing(monkeypatch) -> None:
    """Empty IRLTLT01JPM156N → silent skip (Japan 10Y is the PRIMARY
    JPY-specific anchor ; without it section refuses to render even
    if DGS10 has data)."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(jp10y=None, dgs10=(4.45, date(2026, 5, 13))),
    )
    session = AsyncMock()
    md, sources = await _section_jpy_specific(session, "USD_JPY")
    assert md == ""
    assert sources == []


# ──────────────────────────── JP10Y-only path ──────────────────────────


@pytest.mark.asyncio
async def test_renders_jp10y_only_when_dgs10_missing(monkeypatch) -> None:
    """JP10Y populated but DGS10 absent → section renders Japan anchor
    only (graceful degradation, no differential block, no composite)."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(jp10y=(1.45, date(2026, 4, 1)), dgs10=None),
    )
    session = AsyncMock()
    md, sources = await _section_jpy_specific(session, "USD_JPY")
    assert "JP 10Y = 1.45%" in md
    assert "OECD MEI monthly" in md
    # No DGS10 block (differential absent)
    assert "DGS10" not in md or "FRED:DGS10" not in md
    # No composite triangle
    assert "rate-differential triangle" not in md
    assert sources == ["FRED:IRLTLT01JPM156N@2026-04-01"]


# ──────────────────────────── Full 2-driver path ───────────────────────


@pytest.mark.asyncio
async def test_renders_full_triangle_when_both_drivers_present(monkeypatch) -> None:
    """JP10Y + DGS10 both populated → renders both blocks + differential
    + composite triangle + 2 source-stamps."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            jp10y=(1.45, date(2026, 4, 1)),
            dgs10=(4.45, date(2026, 5, 13)),
        ),
    )
    session = AsyncMock()
    md, sources = await _section_jpy_specific(session, "USD_JPY")
    # JP block
    assert "JP 10Y = 1.45%" in md
    # DGS10 block
    assert "DGS10 = 4.45%" in md
    # Differential computed (4.45 - 1.45 = +3.00)
    assert "US-JP 10Y differential = +3.00 pp" in md
    # Frequency mismatch warning
    assert "Frequency mismatch" in md
    assert "MONTHLY" in md
    # Composite triangle
    assert "rate-differential triangle" in md
    assert "Engel-West" in md
    assert "Brunnermeier-Nagel-Pedersen" in md
    # 2 source-stamps
    assert "FRED:IRLTLT01JPM156N@2026-04-01" in sources
    assert "FRED:DGS10@2026-05-13" in sources
    assert len(sources) == 2


# ──────────────────────────── Differential math ────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("dgs10_value", "jp10y_value", "expected_diff_str"),
    [
        (4.45, 1.45, "+3.00 pp"),  # canonical 2026 print
        (3.80, 1.50, "+2.30 pp"),  # narrowing scenario
        (5.20, 0.80, "+4.40 pp"),  # 2024-class wide
        (3.50, 3.40, "+0.10 pp"),  # near-parity tail
    ],
)
async def test_differential_computed_correctly(
    monkeypatch, dgs10_value: float, jp10y_value: float, expected_diff_str: str
) -> None:
    """4 scenarios : differential = DGS10 - JP 10Y, signed format `+X.XX pp`."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            jp10y=(jp10y_value, date(2026, 4, 1)),
            dgs10=(dgs10_value, date(2026, 5, 13)),
        ),
    )
    session = AsyncMock()
    md, _ = await _section_jpy_specific(session, "USD_JPY")
    assert expected_diff_str in md


# ──────────────────────────── ADR-017 boundary ─────────────────────────


@pytest.mark.asyncio
async def test_rendered_text_passes_adr017_filter(monkeypatch) -> None:
    """Full-render text MUST pass the r32 hardened ADR-017 filter."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            jp10y=(1.45, date(2026, 4, 1)),
            dgs10=(4.45, date(2026, 5, 13)),
        ),
    )
    session = AsyncMock()
    md, _ = await _section_jpy_specific(session, "USD_JPY")
    assert is_adr017_clean(md), "ADR-017 violation in r45 _section_jpy_specific output."


# ──────────────────────────── Symmetric language doctrine ──────────────


@pytest.mark.asyncio
async def test_symmetric_USD_bid_and_JPY_bid_branches_emitted(monkeypatch) -> None:
    """ichor-trader r32/r41/r42/r43 carry-forward : the differential
    interpretive section emits BOTH USD-bid (carry-bid regime) AND
    JPY-bid (carry-unwind regime) branches."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            jp10y=(1.45, date(2026, 4, 1)),
            dgs10=(4.45, date(2026, 5, 13)),
        ),
    )
    session = AsyncMock()
    md, _ = await _section_jpy_specific(session, "USD_JPY")
    assert "USD-bid" in md or "USD/JPY upside" in md
    assert "JPY-bid" in md
    # Regime references
    md_lower = md.lower()
    assert "carry-bid" in md_lower
    assert "carry-unwind" in md_lower
    assert "risk-off" in md_lower or "vol_elevated" in md_lower


# ──────────────────────────── Tetlock invalidation ─────────────────────


@pytest.mark.asyncio
async def test_tetlock_invalidation_thresholds_visible(monkeypatch) -> None:
    """r42 R28 + r43 carry-forward : differential interpretation section
    MUST emit explicit Tetlock invalidation lines with VIX cross-confirmation
    thresholds."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            jp10y=(1.45, date(2026, 4, 1)),
            dgs10=(4.45, date(2026, 5, 13)),
        ),
    )
    session = AsyncMock()
    md, _ = await _section_jpy_specific(session, "USD_JPY")
    assert "Tetlock invalidation" in md
    # Specific thresholds
    assert "VIX > 25" in md
    assert "narrows by " in md
    assert "VIX falls below 18" in md
    assert "Brunnermeier-Nagel-Pedersen 2009" in md


# ──────────────────────────── Frequency mismatch warning ───────────────


@pytest.mark.asyncio
async def test_frequency_mismatch_warning_emitted(monkeypatch) -> None:
    """BTP r34 cadence-mismatch precedent : the section MUST surface
    the daily/monthly cadence mismatch inline so the LLM treats the
    differential as a REGIME indicator, not an intraday signal."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            jp10y=(1.45, date(2026, 4, 1)),
            dgs10=(4.45, date(2026, 5, 13)),
        ),
    )
    session = AsyncMock()
    md, _ = await _section_jpy_specific(session, "USD_JPY")
    assert "Frequency mismatch" in md
    assert "DGS10 is DAILY" in md
    assert "JP 10Y is MONTHLY" in md
    assert "REGIME indicator" in md
    assert "BTP r34 precedent" in md


# ──────────────────────────── Ito-Yabu deferral citation ────────────────


@pytest.mark.asyncio
async def test_ito_yabu_doi_referenced_for_intervention_deferral(monkeypatch) -> None:
    """ADR-092 §T2.JPY-Intervention deferral : the section MUST reference
    Ito-Yabu 2007 reaction function with corrected DOI 10.1016/j.jimonfin.
    2006.12.001 (not the .11.002 adjacent paper). Confirms BoJ intervention
    tail-risk is acknowledged but deferred to ADR-095."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            jp10y=(1.45, date(2026, 4, 1)),
            dgs10=(4.45, date(2026, 5, 13)),
        ),
    )
    session = AsyncMock()
    md, _ = await _section_jpy_specific(session, "USD_JPY")
    assert "Ito-Yabu 2007" in md
    assert "10.1016/j.jimonfin.2006.12.001" in md
    assert "ADR-095" in md


# ──────────────────────────── R24 SUBSET-not-SUPERSET ──────────────────


@pytest.mark.asyncio
async def test_r24_subset_not_superset_documented_inline(monkeypatch) -> None:
    """R24 discipline (r40 codified) : the composite triangle MUST
    document the cadence-mismatch reasoning inline, citing BTP r34 as
    the precedent."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            jp10y=(1.45, date(2026, 4, 1)),
            dgs10=(4.45, date(2026, 5, 13)),
        ),
    )
    session = AsyncMock()
    md, _ = await _section_jpy_specific(session, "USD_JPY")
    assert "R24 SUBSET-not-SUPERSET" in md
    assert "cadence-mismatch" in md
    assert "BTP r34 precedent" in md
