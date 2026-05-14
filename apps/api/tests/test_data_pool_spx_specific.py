"""Unit tests for `_section_spx_specific` — Round-43 GAP-A continuation 3/5.

Verifies the SPX500 VIX-term-structure + funding + sentiment data-pool
section :
  1. Asset gate : non-SPX500_USD assets return ("", []) without DB I/O.
  2. Empty VIXCLS → silent skip (primary tail-regime driver absent).
  3. VIX-only path (no VXVCLS, no NFCI, no SBOI) renders single-driver.
  4. Full 3-driver path renders all blocks + composite triangle.
  5. Triangle ABSENT when any driver is partial.
  6. Term-structure ratio band classification (contango / backwardation).
  7. NFCI band classification (4 bands).
  8. SBOI band classification (4 bands).
  9. Source-stamp format pinned (FRED:VIXCLS@*, FRED:VXVCLS@*,
     FRED:NFCI@*, NFIB:SBOI@YYYY-MM).
 10. ADR-017 boundary preserved on rendered text.
 11. Symmetric language doctrine (SPX-bid + SPX-soft).
 12. Tetlock invalidation thresholds visible on all 3 drivers.
 13. SPY-proxy caveat (ADR-089) annotated inline.

Uses _latest_fred monkeypatch (for 3 FRED series in sequence) + a
1-call AsyncMock + MagicMock for the SBOI ORM lookup.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from ichor_api.services.adr017_filter import is_adr017_clean
from ichor_api.services.data_pool import _section_spx_specific


def _make_sboi_row(d: date, sboi: float, unc: float | None = None):
    """Lightweight stand-in for `NfibSbetObservation` rows."""
    obj = MagicMock()
    obj.report_month = d
    obj.sboi = sboi
    obj.uncertainty_index = unc
    return obj


def _mock_session_for_sboi(sboi_rows=None) -> AsyncMock:
    """AsyncMock session that returns SBOI rows on its single execute()
    call (the FRED reads are stubbed via _latest_fred monkeypatch)."""
    sboi_rows = sboi_rows or []
    sboi_scalars = MagicMock()
    sboi_scalars.all.return_value = sboi_rows
    sboi_result = MagicMock()
    sboi_result.scalars.return_value = sboi_scalars

    session = AsyncMock()
    session.execute = AsyncMock(return_value=sboi_result)
    return session


def _make_fred_stub(vix=None, vxv=None, nfci=None):
    """Build a _latest_fred replacement that returns canned values per
    series_id. None means "series not available" (returns None)."""

    async def _stub(session, series_id, max_age_days=None):
        if series_id == "VIXCLS":
            return vix
        if series_id == "VXVCLS":
            return vxv
        if series_id == "NFCI":
            return nfci
        return None

    return _stub


# ──────────────────────────── Asset gate ──────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "asset",
    [
        "EUR_USD",
        "GBP_USD",
        "USD_JPY",
        "AUD_USD",
        "USD_CAD",
        "XAU_USD",
        "NAS100_USD",
    ],
)
async def test_returns_empty_on_non_spx_asset(asset: str) -> None:
    """Asset gate : only SPX500_USD renders. Zero DB I/O on non-SPX."""
    session = AsyncMock()
    md, sources = await _section_spx_specific(session, asset)
    assert md == ""
    assert sources == []
    assert session.execute.await_count == 0


# ──────────────────────────── Empty VIXCLS path ────────────────────────


@pytest.mark.asyncio
async def test_returns_empty_when_vix_missing(monkeypatch) -> None:
    """Empty VIXCLS → silent skip (VIX is the PRIMARY tail-regime driver
    ; without it section refuses to render even if other drivers have
    data)."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(vix=None),
    )
    session = _mock_session_for_sboi(sboi_rows=[])
    md, sources = await _section_spx_specific(session, "SPX500_USD")
    assert md == ""
    assert sources == []


# ──────────────────────────── VIX-only path ────────────────────────────


@pytest.mark.asyncio
async def test_renders_vix_only_when_other_drivers_empty(monkeypatch) -> None:
    """VIX populated but VXVCLS + NFCI + SBOI all empty → section
    renders VIX level only (graceful degradation, single-driver)."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(vix=(18.5, date(2026, 5, 13)), vxv=None, nfci=None),
    )
    session = _mock_session_for_sboi(sboi_rows=[])
    md, sources = await _section_spx_specific(session, "SPX500_USD")
    assert "VIXCLS = 18.50" in md
    assert "Polygon ticker = SPY proxy, ADR-089" in md
    # No VXVCLS block (ratio absent)
    assert "Term-structure ratio" not in md
    # No NFCI heading
    assert "### NFCI" not in md
    # No SBOI heading
    assert "### NFIB" not in md
    # No composite triangle
    assert "triangle composite" not in md
    assert sources == ["FRED:VIXCLS@2026-05-13"]


# ──────────────────────────── Full 3-driver path ───────────────────────


@pytest.mark.asyncio
async def test_renders_full_triangle_when_all_3_drivers_present(monkeypatch) -> None:
    """All 3 drivers populated → renders all blocks + composite triangle
    + 4 source-stamps (VIX + VXV + NFCI + SBOI)."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            vix=(18.5, date(2026, 5, 13)),
            vxv=(21.0, date(2026, 5, 13)),  # ratio = 21/18.5 = 1.135 (deep contango)
            nfci=(-0.4, date(2026, 5, 11)),  # modestly loose
        ),
    )
    sboi_rows = [
        _make_sboi_row(date(2026, 4, 1), 98.5, 92.0),
        _make_sboi_row(date(2026, 3, 1), 95.8, 95.0),
    ]
    session = _mock_session_for_sboi(sboi_rows=sboi_rows)
    md, sources = await _section_spx_specific(session, "SPX500_USD")
    # VIX block
    assert "VIXCLS = 18.50" in md
    assert "VXVCLS = 21.00" in md
    assert "Term-structure ratio = 1.135" in md
    assert "deep contango" in md
    # NFCI block (-0.4 = modestly loose -0.5 to 0)
    assert "NFCI = -0.400" in md
    assert "modestly loose" in md
    # SBOI block (98.5 = modestly contractionary 95-100)
    assert "SBOI = 98.5" in md
    assert "modestly contractionary" in md
    assert "Uncertainty Index" in md
    # 1-month delta = 98.5 - 95.8 = +2.7
    assert "+2.7" in md
    # Composite triangle
    assert "VIX-funding-sentiment triangle" in md
    assert "R24 SUBSET-not-SUPERSET" in md
    # 4 source-stamps
    assert "FRED:VIXCLS@2026-05-13" in sources
    assert "FRED:VXVCLS@2026-05-13" in sources
    assert "FRED:NFCI@2026-05-11" in sources
    assert "NFIB:SBOI@2026-04" in sources
    assert len(sources) == 4


# ──────────────────────────── Composite triangle gating ────────────────


@pytest.mark.asyncio
async def test_composite_triangle_absent_when_sboi_missing(monkeypatch) -> None:
    """VIX + VXV + NFCI present but SBOI missing → all 3 individual
    blocks render but NO composite triangle (needs all 3 fresh)."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            vix=(18.5, date(2026, 5, 13)),
            vxv=(21.0, date(2026, 5, 13)),
            nfci=(-0.4, date(2026, 5, 11)),
        ),
    )
    session = _mock_session_for_sboi(sboi_rows=[])
    md, sources = await _section_spx_specific(session, "SPX500_USD")
    assert "VIXCLS" in md
    assert "VXVCLS" in md
    assert "NFCI" in md
    assert "### NFIB" not in md  # SBOI heading absent
    assert "VIX-funding-sentiment triangle" not in md
    # 3 source-stamps (no SBOI)
    assert len(sources) == 3


# ──────────────────────────── Term-structure band ──────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("vix", "vxv", "expected_band"),
    [
        (18.0, 22.0, "deep contango"),  # ratio 1.222
        (18.0, 18.5, "modest contango"),  # ratio 1.028
        (20.0, 19.5, "near-flat"),  # ratio 0.975
        (22.0, 19.0, "backwardation"),  # ratio 0.864
    ],
)
async def test_term_structure_band_classification(
    monkeypatch, vix: float, vxv: float, expected_band: str
) -> None:
    """4 bands : deep contango (>=1.10) / modest (1.00-1.10) /
    near-flat (0.95-1.00) / backwardation (<0.95)."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(vix=(vix, date(2026, 5, 13)), vxv=(vxv, date(2026, 5, 13))),
    )
    session = _mock_session_for_sboi(sboi_rows=[])
    md, _ = await _section_spx_specific(session, "SPX500_USD")
    assert expected_band in md


# ──────────────────────────── NFCI band classification ─────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("nfci_value", "expected_band"),
    [
        (-0.8, "very loose"),
        (-0.3, "modestly loose"),
        (0.2, "modestly tight"),
        (0.7, "tight"),
    ],
)
async def test_nfci_band_classification(monkeypatch, nfci_value: float, expected_band: str) -> None:
    """4 bands : very loose (<-0.5) / modestly loose (-0.5 to 0) /
    modestly tight (0 to +0.5) / tight (>=+0.5)."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            vix=(18.0, date(2026, 5, 13)),
            nfci=(nfci_value, date(2026, 5, 11)),
        ),
    )
    session = _mock_session_for_sboi(sboi_rows=[])
    md, _ = await _section_spx_specific(session, "SPX500_USD")
    assert expected_band in md


# ──────────────────────────── SBOI band classification ─────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("sboi_value", "expected_band"),
    [
        (102.5, "expansionary"),
        (97.0, "modestly contractionary"),
        (92.0, "contractionary"),
        (85.0, "deeply contractionary"),
    ],
)
async def test_sboi_band_classification(monkeypatch, sboi_value: float, expected_band: str) -> None:
    """4 bands : expansionary (>=100) / modestly contractionary (95-100) /
    contractionary (90-95) / deeply contractionary (<90)."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(vix=(18.0, date(2026, 5, 13))),
    )
    sboi_rows = [_make_sboi_row(date(2026, 4, 1), sboi_value, 90.0)]
    session = _mock_session_for_sboi(sboi_rows=sboi_rows)
    md, _ = await _section_spx_specific(session, "SPX500_USD")
    assert expected_band in md


# ──────────────────────────── ADR-017 boundary ─────────────────────────


@pytest.mark.asyncio
async def test_rendered_text_passes_adr017_filter(monkeypatch) -> None:
    """Full-render text MUST pass the r32 hardened ADR-017 filter."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            vix=(18.5, date(2026, 5, 13)),
            vxv=(21.0, date(2026, 5, 13)),
            nfci=(-0.4, date(2026, 5, 11)),
        ),
    )
    sboi_rows = [
        _make_sboi_row(date(2026, 4, 1), 98.5, 92.0),
        _make_sboi_row(date(2026, 3, 1), 95.8, 95.0),
    ]
    session = _mock_session_for_sboi(sboi_rows=sboi_rows)
    md, _ = await _section_spx_specific(session, "SPX500_USD")
    assert is_adr017_clean(md), "ADR-017 violation in r43 _section_spx_specific output."


# ──────────────────────────── Symmetric language doctrine ──────────────


@pytest.mark.asyncio
async def test_all_drivers_emit_symmetric_branches(monkeypatch) -> None:
    """ichor-trader r32/r41/r42 carry-forward : every interpretive
    section emits BOTH SPX-bid AND SPX-soft branches."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            vix=(18.5, date(2026, 5, 13)),
            vxv=(21.0, date(2026, 5, 13)),
            nfci=(-0.4, date(2026, 5, 11)),
        ),
    )
    sboi_rows = [
        _make_sboi_row(date(2026, 4, 1), 98.5, 92.0),
    ]
    session = _mock_session_for_sboi(sboi_rows=sboi_rows)
    md, _ = await _section_spx_specific(session, "SPX500_USD")
    # All 3 sections symmetric
    assert "SPX-bid" in md
    assert "SPX-soft" in md
    # Regime references on each section
    md_lower = md.lower()
    assert "goldilocks" in md_lower or "risk-on" in md_lower
    assert "risk-off" in md_lower or "vol_elevated" in md_lower
    # Broken-smile reference (Stephen Jen)
    assert "broken-smile" in md_lower


# ──────────────────────────── Tetlock invalidation ─────────────────────


@pytest.mark.asyncio
async def test_tetlock_invalidation_on_all_3_drivers(monkeypatch) -> None:
    """r42 R28 carry-forward : every interpretive section MUST emit a
    Tetlock invalidation line. Full triangle path = 3 Tetlock keywords."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            vix=(18.5, date(2026, 5, 13)),
            vxv=(21.0, date(2026, 5, 13)),
            nfci=(-0.4, date(2026, 5, 11)),
        ),
    )
    sboi_rows = [
        _make_sboi_row(date(2026, 4, 1), 98.5, 92.0),
    ]
    session = _mock_session_for_sboi(sboi_rows=sboi_rows)
    md, _ = await _section_spx_specific(session, "SPX500_USD")
    assert md.count("Tetlock invalidation") >= 3
    # Specific thresholds visible
    assert "ratio drops below 1.00" in md  # VIX-term-structure invalidation
    assert "VIX > 22" in md
    assert "NFCI" in md  # NFCI invalidation


# ──────────────────────────── ADR-089 SPY proxy caveat ─────────────────


@pytest.mark.asyncio
async def test_spy_proxy_caveat_annotated(monkeypatch) -> None:
    """ADR-089 SPY proxy caveat MUST be annotated inline (Polygon SPX
    blocked $49/mo subscription, SPY ETF used as proxy)."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(vix=(18.0, date(2026, 5, 13))),
    )
    session = _mock_session_for_sboi(sboi_rows=[])
    md, _ = await _section_spx_specific(session, "SPX500_USD")
    assert "Polygon ticker = SPY proxy" in md
    assert "ADR-089" in md
