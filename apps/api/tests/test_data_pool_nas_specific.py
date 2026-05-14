"""Unit tests for `_section_nas_specific` — Round-42 GAP-A continuation 2/5.

Verifies the NAS100 duration-vol-tail triangle data-pool section
(Hou-Mo-Xue q-factor duration channel + Whaley VVIX vol-of-vol regime
+ CBOE SKEW tail-bid premium) :
  1. Asset gate : non-NAS100_USD assets return ("", []) without DB I/O.
  2. Empty DGS10 → silent skip (primary driver absent).
  3. DGS10-only path (VVIX + SKEW empty) renders single-driver block.
  4. Full 3-driver path renders all blocks + composite triangle.
  5. Triangle ABSENT when only 1 or 2 drivers have 6+ rows.
  6. VVIX band classification correctness (4 bands).
  7. SKEW band classification correctness (4 bands).
  8. Source-stamp format pinned (`FRED:DGS10@*`, `CBOE:VVIX@*`, `CBOE:SKEW@*`).
  9. ADR-017 boundary preserved on rendered text.
 10. Symmetric language doctrine (NAS-bid + NAS-soft on each driver).
 11. Tetlock invalidation thresholds visible inline (r39+ doctrine).
 12. R24 SUBSET-not-SUPERSET clause surfaced in composite block.

Uses 3-call `AsyncMock + MagicMock + side_effect` for the multi-query
session (DGS10 + VVIX + SKEW), mirrors XAU r41 + EUR r34 template.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from ichor_api.services.adr017_filter import is_adr017_clean
from ichor_api.services.data_pool import _section_nas_specific


def _make_vvix_row(d: date, v: float):
    """Lightweight stand-in for `CboeVvixObservation` rows."""
    obj = MagicMock()
    obj.observation_date = d
    obj.vvix_value = v
    return obj


def _make_skew_row(d: date, v: float):
    """Lightweight stand-in for `CboeSkewObservation` rows."""
    obj = MagicMock()
    obj.observation_date = d
    obj.skew_value = v
    return obj


def _mock_session_multi(*, dgs_rows=None, vvix_rows=None, skew_rows=None) -> AsyncMock:
    """Build an AsyncMock session returning DIFFERENT rows for successive
    `await session.execute(stmt)` calls.

    Call 1 → DGS10 rows (FredObservation tuples).
    Call 2 → VVIX scalars (CboeVvixObservation-like objects).
    Call 3 → SKEW scalars (CboeSkewObservation-like objects).
    """
    dgs_rows = dgs_rows or []
    vvix_rows = vvix_rows or []
    skew_rows = skew_rows or []

    dgs_result = MagicMock()
    dgs_result.all.return_value = dgs_rows

    vvix_scalars = MagicMock()
    vvix_scalars.all.return_value = vvix_rows
    vvix_result = MagicMock()
    vvix_result.scalars.return_value = vvix_scalars

    skew_scalars = MagicMock()
    skew_scalars.all.return_value = skew_rows
    skew_result = MagicMock()
    skew_result.scalars.return_value = skew_scalars

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[dgs_result, vvix_result, skew_result])
    return session


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
        "SPX500_USD",
    ],
)
async def test_returns_empty_on_non_nas_asset(asset: str) -> None:
    """Asset gate : only NAS100_USD renders. Zero DB I/O on non-NAS asset."""
    session = AsyncMock()
    md, sources = await _section_nas_specific(session, asset)
    assert md == ""
    assert sources == []
    assert session.execute.await_count == 0


# ──────────────────────────── Empty DGS10 path ─────────────────────────


@pytest.mark.asyncio
async def test_returns_empty_when_dgs10_table_empty() -> None:
    """Empty DGS10 → silent skip (DGS10 is the PRIMARY duration driver
    per Hou-Mo-Xue ; without it the section refuses to render even if
    VVIX/SKEW would have data)."""
    session = _mock_session_multi(dgs_rows=[], vvix_rows=[], skew_rows=[])
    md, sources = await _section_nas_specific(session, "NAS100_USD")
    assert md == ""
    assert sources == []


# ──────────────────────────── DGS10-only path ──────────────────────────


@pytest.mark.asyncio
async def test_renders_dgs10_only_when_vol_tables_empty() -> None:
    """DGS10 populated but VVIX + SKEW empty → section renders DGS10
    block only (graceful degradation, single-driver)."""
    dgs_rows = [
        (date(2026, 5, 13), Decimal("4.35")),
        (date(2026, 5, 12), Decimal("4.33")),
        (date(2026, 5, 9), Decimal("4.30")),
        (date(2026, 5, 8), Decimal("4.28")),
        (date(2026, 5, 7), Decimal("4.25")),
        (date(2026, 5, 6), Decimal("4.20")),
    ]
    session = _mock_session_multi(dgs_rows=dgs_rows, vvix_rows=[], skew_rows=[])
    md, sources = await _section_nas_specific(session, "NAS100_USD")
    assert "DGS10 = 4.35%" in md
    # delta = 4.35 - 4.20 = +0.15% = +15.0 bp
    assert "+15.0 bp" in md
    # VVIX SECTION heading absent (note : DGS10 Tetlock line legitimately
    # cross-references "VVIX > 100" as a threshold guard — that's a
    # framework reference, not a rendered block)
    assert "### VVIX" not in md
    # SKEW SECTION heading absent (similar : SKEW threshold may appear
    # in cross-references but no rendered SKEW block)
    assert "### SKEW" not in md
    # Composite triangle absent (needs all 3 drivers with 6+ rows)
    assert "duration-vol-tail triangle" not in md
    assert sources == ["FRED:DGS10@2026-05-13"]


# ──────────────────────────── Full 3-driver path ───────────────────────


@pytest.mark.asyncio
async def test_renders_full_triangle_when_all_3_have_6_plus_rows() -> None:
    """All 3 drivers populated with 6+ rows each → renders all blocks +
    composite triangle + 3 source-stamps."""
    dgs_rows = [
        (date(2026, 5, 13), Decimal("4.35")),
        (date(2026, 5, 12), Decimal("4.33")),
        (date(2026, 5, 9), Decimal("4.30")),
        (date(2026, 5, 8), Decimal("4.28")),
        (date(2026, 5, 7), Decimal("4.25")),
        (date(2026, 5, 6), Decimal("4.20")),
    ]
    vvix_rows = [
        _make_vvix_row(date(2026, 5, 13), 92.50),
        _make_vvix_row(date(2026, 5, 12), 91.00),
        _make_vvix_row(date(2026, 5, 9), 90.50),
        _make_vvix_row(date(2026, 5, 8), 89.00),
        _make_vvix_row(date(2026, 5, 7), 88.50),
        _make_vvix_row(date(2026, 5, 6), 88.00),
    ]
    skew_rows = [
        _make_skew_row(date(2026, 5, 13), 125.00),
        _make_skew_row(date(2026, 5, 12), 124.00),
        _make_skew_row(date(2026, 5, 9), 123.50),
        _make_skew_row(date(2026, 5, 8), 122.00),
        _make_skew_row(date(2026, 5, 7), 121.00),
        _make_skew_row(date(2026, 5, 6), 120.00),
    ]
    session = _mock_session_multi(dgs_rows=dgs_rows, vvix_rows=vvix_rows, skew_rows=skew_rows)
    md, sources = await _section_nas_specific(session, "NAS100_USD")
    # DGS10 block
    assert "DGS10 = 4.35%" in md
    assert "+15.0 bp" in md
    # VVIX block (92.50 = modest bid band 85-100)
    assert "VVIX = 92.50" in md
    assert "modest bid (85-100)" in md
    # SKEW block (125.00 = modest tail bid 115-130)
    assert "SKEW = 125.00" in md
    assert "modest tail bid (115-130)" in md
    # Composite triangle present
    assert "duration-vol-tail triangle" in md
    assert "R24 SUBSET-not-SUPERSET" in md
    # 3 source-stamps
    assert "FRED:DGS10@2026-05-13" in sources
    assert "CBOE:VVIX@2026-05-13" in sources
    assert "CBOE:SKEW@2026-05-13" in sources
    assert len(sources) == 3


# ──────────────────────────── Composite triangle gating ────────────────


@pytest.mark.asyncio
async def test_composite_triangle_absent_when_skew_empty() -> None:
    """DGS10 + VVIX have 6+ rows but SKEW empty → DGS10 + VVIX render
    but NO composite triangle (needs all 3 fresh)."""
    dgs_rows = [
        (date(2026, 5, 13), Decimal("4.35")),
        (date(2026, 5, 12), Decimal("4.33")),
        (date(2026, 5, 9), Decimal("4.30")),
        (date(2026, 5, 8), Decimal("4.28")),
        (date(2026, 5, 7), Decimal("4.25")),
        (date(2026, 5, 6), Decimal("4.20")),
    ]
    vvix_rows = [
        _make_vvix_row(date(2026, 5, 13), 92.50),
        _make_vvix_row(date(2026, 5, 12), 91.00),
        _make_vvix_row(date(2026, 5, 9), 90.50),
        _make_vvix_row(date(2026, 5, 8), 89.00),
        _make_vvix_row(date(2026, 5, 7), 88.50),
        _make_vvix_row(date(2026, 5, 6), 88.00),
    ]
    session = _mock_session_multi(dgs_rows=dgs_rows, vvix_rows=vvix_rows, skew_rows=[])
    md, sources = await _section_nas_specific(session, "NAS100_USD")
    assert "DGS10" in md
    assert "VVIX = 92.50" in md
    # SKEW section heading absent (cross-references in VVIX Tetlock line OK)
    assert "### SKEW" not in md
    assert "duration-vol-tail triangle" not in md
    # 2 source-stamps
    assert "FRED:DGS10@2026-05-13" in sources
    assert "CBOE:VVIX@2026-05-13" in sources
    assert len(sources) == 2


# ──────────────────────────── VVIX band classification ─────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("vvix_value", "expected_band"),
    [
        (75.0, "calm tail-pricing (<85)"),
        (92.5, "modest bid (85-100)"),
        (120.0, "elevated turbulence (100-140)"),
        (155.0, "vol-surface blowup territory (>140)"),
    ],
)
async def test_vvix_band_classification(vvix_value: float, expected_band: str) -> None:
    """VVIX bands : <85 calm / 85-100 modest / 100-140 elevated / >140 blowup."""
    dgs_rows = [(date(2026, 5, 13), Decimal("4.35"))]
    vvix_rows = [_make_vvix_row(date(2026, 5, 13), vvix_value)]
    session = _mock_session_multi(dgs_rows=dgs_rows, vvix_rows=vvix_rows, skew_rows=[])
    md, _ = await _section_nas_specific(session, "NAS100_USD")
    assert expected_band in md


# ──────────────────────────── SKEW band classification ─────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("skew_value", "expected_band"),
    [
        (110.0, "neutral / complacent (<115)"),
        (125.0, "modest tail bid (115-130)"),
        (140.0, "elevated stress (130-150)"),
        (155.0, "panic priced in (>150)"),
    ],
)
async def test_skew_band_classification(skew_value: float, expected_band: str) -> None:
    """SKEW bands : <115 complacent / 115-130 modest / 130-150 elevated / >150 panic."""
    dgs_rows = [(date(2026, 5, 13), Decimal("4.35"))]
    skew_rows = [_make_skew_row(date(2026, 5, 13), skew_value)]
    session = _mock_session_multi(dgs_rows=dgs_rows, vvix_rows=[], skew_rows=skew_rows)
    md, _ = await _section_nas_specific(session, "NAS100_USD")
    assert expected_band in md


# ──────────────────────────── Source-stamp format pinned ───────────────


@pytest.mark.asyncio
async def test_source_stamp_format_pinned_dgs10_only() -> None:
    """DGS10 source-stamp format `FRED:DGS10@YYYY-MM-DD`."""
    dgs_rows = [(date(2026, 4, 1), Decimal("4.18"))]
    session = _mock_session_multi(dgs_rows=dgs_rows, vvix_rows=[], skew_rows=[])
    _, sources = await _section_nas_specific(session, "NAS100_USD")
    assert sources == ["FRED:DGS10@2026-04-01"]


@pytest.mark.asyncio
async def test_source_stamps_full_triangle_format_pinned() -> None:
    """All 3 stamps in fixed order : DGS10 → VVIX → SKEW."""
    dgs_rows = [(date(2026, 5, 13), Decimal("4.35"))]
    vvix_rows = [_make_vvix_row(date(2026, 5, 12), 92.50)]
    skew_rows = [_make_skew_row(date(2026, 5, 11), 125.00)]
    session = _mock_session_multi(dgs_rows=dgs_rows, vvix_rows=vvix_rows, skew_rows=skew_rows)
    _, sources = await _section_nas_specific(session, "NAS100_USD")
    assert sources == [
        "FRED:DGS10@2026-05-13",
        "CBOE:VVIX@2026-05-12",
        "CBOE:SKEW@2026-05-11",
    ]


# ──────────────────────────── ADR-017 boundary ─────────────────────────


@pytest.mark.asyncio
async def test_rendered_text_passes_adr017_filter() -> None:
    """Full-render text MUST pass the r32 hardened ADR-017 filter — no
    BUY/SELL/TARGET/ENTRY tokens, no Unicode-confusable bypass, no
    FR/ES/DE imperatives."""
    dgs_rows = [
        (date(2026, 5, 13), Decimal("4.35")),
        (date(2026, 5, 12), Decimal("4.33")),
        (date(2026, 5, 9), Decimal("4.30")),
        (date(2026, 5, 8), Decimal("4.28")),
        (date(2026, 5, 7), Decimal("4.25")),
        (date(2026, 5, 6), Decimal("4.20")),
    ]
    vvix_rows = [_make_vvix_row(date(2026, 5, 13 - i), 90.0 + i * 0.5) for i in range(6)]
    skew_rows = [_make_skew_row(date(2026, 5, 13 - i), 125.0 - i * 0.5) for i in range(6)]
    session = _mock_session_multi(dgs_rows=dgs_rows, vvix_rows=vvix_rows, skew_rows=skew_rows)
    md, _ = await _section_nas_specific(session, "NAS100_USD")
    assert is_adr017_clean(md), "ADR-017 violation in r42 _section_nas_specific output."


# ──────────────────────────── Symmetric language doctrine ──────────────


@pytest.mark.asyncio
async def test_all_drivers_emit_symmetric_branches() -> None:
    """ichor-trader r32 + r33 + r41 carry-forward : every interpretive
    section MUST emit BOTH NAS-bid AND NAS-soft branches so the
    Pass-2 LLM picks consistent with Pass-1 regime."""
    dgs_rows = [
        (date(2026, 5, 13), Decimal("4.35")),
        (date(2026, 5, 12), Decimal("4.33")),
        (date(2026, 5, 9), Decimal("4.30")),
        (date(2026, 5, 8), Decimal("4.28")),
        (date(2026, 5, 7), Decimal("4.25")),
        (date(2026, 5, 6), Decimal("4.20")),
    ]
    vvix_rows = [_make_vvix_row(date(2026, 5, 13 - i), 90.0 + i * 0.5) for i in range(6)]
    skew_rows = [_make_skew_row(date(2026, 5, 13 - i), 125.0 - i * 0.5) for i in range(6)]
    session = _mock_session_multi(dgs_rows=dgs_rows, vvix_rows=vvix_rows, skew_rows=skew_rows)
    md, _ = await _section_nas_specific(session, "NAS100_USD")
    # DGS10 block symmetric
    assert "NAS-soft" in md
    assert "NAS-bid" in md
    # All 3 drivers reference both regime sides
    md_lower = md.lower()
    assert "risk-off" in md_lower or "vol_elevated" in md_lower
    assert "goldilocks" in md_lower or "risk-on" in md_lower
    # Composite triangle clarifies 3-corner-bear vs growth-not-inflation
    assert "growth-not-inflation" in md
    assert "3-corner-bear" in md or "duration-stress-tail-stress" in md


# ──────────────────────────── Tetlock invalidation discipline ──────────


@pytest.mark.asyncio
async def test_tetlock_invalidation_thresholds_inline() -> None:
    """r39+ codified, r40 R23 ichor-trader default-round-opener
    confirmation : threshold-flip conditions MUST be emitted inline so
    a falsified hypothesis is visible immediately."""
    dgs_rows = [
        (date(2026, 5, 13), Decimal("4.35")),
        (date(2026, 5, 12), Decimal("4.33")),
        (date(2026, 5, 9), Decimal("4.30")),
        (date(2026, 5, 8), Decimal("4.28")),
        (date(2026, 5, 7), Decimal("4.25")),
        (date(2026, 5, 6), Decimal("4.20")),
    ]
    vvix_rows = [_make_vvix_row(date(2026, 5, 13 - i), 90.0 + i * 0.5) for i in range(6)]
    session = _mock_session_multi(dgs_rows=dgs_rows, vvix_rows=vvix_rows, skew_rows=[])
    md, _ = await _section_nas_specific(session, "NAS100_USD")
    # Tetlock keyword present at least twice in DGS10-only + VVIX path
    # (SKEW not rendered here, but with full triangle 3+ occurrences pinned
    # by test_full_triangle below)
    assert md.count("Tetlock invalidation") >= 2
    # Specific thresholds visible
    assert "+15 bp" in md  # DGS10 duration-headwind invalidation
    assert "VVIX > 100" in md or "VVIX exceeds 100" in md
    assert "SKEW" in md  # SKEW 130 threshold referenced in VVIX block


@pytest.mark.asyncio
async def test_tetlock_invalidation_present_on_all_3_drivers() -> None:
    """r42 ichor-trader YELLOW fix : SKEW block MUST also emit a
    Tetlock invalidation line (was missing pre-YELLOW). Full triangle
    path should show 3 separate `Tetlock invalidation` keywords (one
    per interpretive section : DGS10 + VVIX + SKEW)."""
    dgs_rows = [
        (date(2026, 5, 13), Decimal("4.35")),
        (date(2026, 5, 12), Decimal("4.33")),
        (date(2026, 5, 9), Decimal("4.30")),
        (date(2026, 5, 8), Decimal("4.28")),
        (date(2026, 5, 7), Decimal("4.25")),
        (date(2026, 5, 6), Decimal("4.20")),
    ]
    vvix_rows = [_make_vvix_row(date(2026, 5, 13 - i), 90.0 + i * 0.5) for i in range(6)]
    skew_rows = [_make_skew_row(date(2026, 5, 13 - i), 125.0 - i * 0.5) for i in range(6)]
    session = _mock_session_multi(dgs_rows=dgs_rows, vvix_rows=vvix_rows, skew_rows=skew_rows)
    md, _ = await _section_nas_specific(session, "NAS100_USD")
    assert md.count("Tetlock invalidation") >= 3
    # SKEW Tetlock-specific threshold visible
    assert "SKEW falls below 115" in md
    assert "SKEW rises above 130" in md
