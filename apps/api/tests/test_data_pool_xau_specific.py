"""Unit tests for `_section_xau_specific` — Round-41 GAP-A continuation.

Verifies the gold-USD specific data-pool section (Erb/Harvey real-yield
triangle + dollar-smile counter-driver) :
  1. Asset gate : non-XAU_USD assets return ("", []) without DB I/O.
  2. Empty DFII10 → silent skip (primary driver absent).
  3. DFII10-only path (DTWEXBGS empty) renders single-driver block.
  4. DFII10 + DTWEXBGS path renders both blocks + composite triangle.
  5. 5-day delta arithmetic correctness for DFII10 (bp) and DTWEXBGS (%).
  6. Source-stamp format pinned (`FRED:DFII10@YYYY-MM-DD`, `FRED:DTWEXBGS@YYYY-MM-DD`).
  7. ADR-017 boundary : rendered text passes the r32 hardened filter.
  8. Symmetric language preserved (both interpretive branches per signal).
  9. Tetlock invalidation thresholds visible inline (r39+ doctrine).
 10. R24 SUBSET-not-SUPERSET clause surfaced when both drivers present.
 11. Single-row case (no 5-day delta) renders LEVEL only.
 12. Composite triangle ABSENT when only one driver has 6+ rows.

Uses `AsyncMock + MagicMock + side_effect` for the multi-query session
mirror of `test_data_pool_eur_specific.py` r34 template.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from ichor_api.services.adr017_filter import is_adr017_clean
from ichor_api.services.data_pool import _section_xau_specific


def _mock_session_multi(*, dfii_rows=None, dxy_rows=None) -> AsyncMock:
    """Build an AsyncMock session returning DIFFERENT rows for successive
    `await session.execute(stmt)` calls.

    Call 1 → DFII10 rows (or [] if not provided).
    Call 2 → DTWEXBGS rows (or [] if not provided).
    """
    dfii_rows = dfii_rows or []
    dxy_rows = dxy_rows or []

    dfii_result = MagicMock()
    dfii_result.all.return_value = dfii_rows
    dxy_result = MagicMock()
    dxy_result.all.return_value = dxy_rows

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[dfii_result, dxy_result])
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
        "NAS100_USD",
        "SPX500_USD",
    ],
)
async def test_returns_empty_on_non_xau_asset(asset: str) -> None:
    """Asset gate : only XAU_USD renders. Zero DB I/O on non-XAU asset."""
    session = AsyncMock()
    md, sources = await _section_xau_specific(session, asset)
    assert md == ""
    assert sources == []
    assert session.execute.await_count == 0


# ──────────────────────────── Empty DFII10 path ────────────────────────


@pytest.mark.asyncio
async def test_returns_empty_when_dfii10_table_empty() -> None:
    """Empty DFII10 → silent skip (DFII10 is the PRIMARY gold driver per
    Erb/Harvey ; without it the section refuses to render even if
    DTWEXBGS would have data)."""
    session = _mock_session_multi(dfii_rows=[], dxy_rows=[])
    md, sources = await _section_xau_specific(session, "XAU_USD")
    assert md == ""
    assert sources == []


# ──────────────────────────── DFII10-only path ─────────────────────────


@pytest.mark.asyncio
async def test_renders_dfii10_only_when_dxy_empty() -> None:
    """DFII10 populated but DTWEXBGS empty → section renders DFII10
    block only (graceful degradation, single-driver)."""
    dfii_rows = [
        (date(2026, 5, 13), Decimal("2.10")),
        (date(2026, 5, 12), Decimal("2.08")),
        (date(2026, 5, 9), Decimal("2.05")),
        (date(2026, 5, 8), Decimal("2.04")),
        (date(2026, 5, 7), Decimal("2.00")),
        (date(2026, 5, 6), Decimal("1.95")),
    ]
    session = _mock_session_multi(dfii_rows=dfii_rows, dxy_rows=[])
    md, sources = await _section_xau_specific(session, "XAU_USD")
    assert "DFII10 = 2.10%" in md
    # delta = 2.10 - 1.95 = +0.15% = +15.0 bp
    assert "+15.0 bp" in md
    # DTWEXBGS block absent (empty rows)
    assert "DTWEXBGS" not in md
    # Composite triangle absent (single driver)
    assert "Gold-Real-Yield triangle" not in md
    assert sources == ["FRED:DFII10@2026-05-13"]


# ──────────────────────────── DFII10 + DXY full path ───────────────────


@pytest.mark.asyncio
async def test_renders_dfii10_plus_dxy_full_triangle() -> None:
    """Both DFII10 + DTWEXBGS populated with 6+ rows each → renders
    BOTH blocks + composite triangle + both source-stamps."""
    dfii_rows = [
        (date(2026, 5, 13), Decimal("2.10")),
        (date(2026, 5, 12), Decimal("2.08")),
        (date(2026, 5, 9), Decimal("2.05")),
        (date(2026, 5, 8), Decimal("2.04")),
        (date(2026, 5, 7), Decimal("2.00")),
        (date(2026, 5, 6), Decimal("1.95")),
    ]
    dxy_rows = [
        (date(2026, 5, 13), Decimal("105.30")),
        (date(2026, 5, 12), Decimal("105.10")),
        (date(2026, 5, 9), Decimal("104.80")),
        (date(2026, 5, 8), Decimal("104.50")),
        (date(2026, 5, 7), Decimal("104.20")),
        (date(2026, 5, 6), Decimal("104.00")),
    ]
    session = _mock_session_multi(dfii_rows=dfii_rows, dxy_rows=dxy_rows)
    md, sources = await _section_xau_specific(session, "XAU_USD")
    # DFII10 block
    assert "DFII10 = 2.10%" in md
    assert "+15.0 bp" in md
    # DTWEXBGS block — % change = (105.30 - 104.00) / 104.00 * 100 = +1.25%
    assert "DTWEXBGS = 105.30" in md
    assert "+1.25%" in md
    # Composite triangle present
    assert "Gold-Real-Yield triangle" in md
    assert "R24 SUBSET-not-SUPERSET" in md
    # Both source-stamps
    assert "FRED:DFII10@2026-05-13" in sources
    assert "FRED:DTWEXBGS@2026-05-13" in sources
    assert len(sources) == 2


# ──────────────────────────── Composite triangle gating ───────────────


@pytest.mark.asyncio
async def test_composite_triangle_absent_when_dxy_single_row() -> None:
    """DFII10 has 6+ rows, DTWEXBGS has only 1 row → DXY level renders
    but NO composite triangle block (needs 6+ on BOTH for the framework
    to disambiguate stagflation vs normal regimes)."""
    dfii_rows = [
        (date(2026, 5, 13), Decimal("2.10")),
        (date(2026, 5, 12), Decimal("2.08")),
        (date(2026, 5, 9), Decimal("2.05")),
        (date(2026, 5, 8), Decimal("2.04")),
        (date(2026, 5, 7), Decimal("2.00")),
        (date(2026, 5, 6), Decimal("1.95")),
    ]
    dxy_rows = [(date(2026, 5, 13), Decimal("105.30"))]
    session = _mock_session_multi(dfii_rows=dfii_rows, dxy_rows=dxy_rows)
    md, sources = await _section_xau_specific(session, "XAU_USD")
    assert "DFII10" in md
    assert "DTWEXBGS = 105.30" in md
    # DXY change line absent (no 5-day delta on single row)
    assert "5-trading-day change" in md  # Present from DFII10 block
    # but NOT a SECOND time for DXY (single occurrence guard)
    assert md.count("5-trading-day change") == 1
    # No composite triangle
    assert "Gold-Real-Yield triangle" not in md
    assert sources == ["FRED:DFII10@2026-05-13", "FRED:DTWEXBGS@2026-05-13"]


# ──────────────────────────── DFII10 single-row case ──────────────────


@pytest.mark.asyncio
async def test_dfii10_single_row_renders_level_only() -> None:
    """DFII10 has only 1 row → no 5-day delta, no interpretation, but
    level + source-stamp still render."""
    dfii_rows = [(date(2026, 5, 13), Decimal("2.10"))]
    session = _mock_session_multi(dfii_rows=dfii_rows, dxy_rows=[])
    md, sources = await _section_xau_specific(session, "XAU_USD")
    assert "DFII10 = 2.10%" in md
    # No delta line, no interpretation, no Tetlock
    assert "5-trading-day change" not in md
    assert "Tetlock" not in md
    assert sources == ["FRED:DFII10@2026-05-13"]


# ──────────────────────────── ADR-017 boundary ─────────────────────────


@pytest.mark.asyncio
async def test_rendered_text_passes_adr017_filter() -> None:
    """The fully-rendered text (DFII10 + DTWEXBGS + composite triangle)
    MUST pass the r32 hardened ADR-017 filter — no BUY/SELL/TARGET
    tokens, no Unicode-confusable bypass, no FR/ES/DE imperatives."""
    dfii_rows = [
        (date(2026, 5, 13), Decimal("2.10")),
        (date(2026, 5, 12), Decimal("2.08")),
        (date(2026, 5, 9), Decimal("2.05")),
        (date(2026, 5, 8), Decimal("2.04")),
        (date(2026, 5, 7), Decimal("2.00")),
        (date(2026, 5, 6), Decimal("1.95")),
    ]
    dxy_rows = [
        (date(2026, 5, 13), Decimal("105.30")),
        (date(2026, 5, 12), Decimal("105.10")),
        (date(2026, 5, 9), Decimal("104.80")),
        (date(2026, 5, 8), Decimal("104.50")),
        (date(2026, 5, 7), Decimal("104.20")),
        (date(2026, 5, 6), Decimal("104.00")),
    ]
    session = _mock_session_multi(dfii_rows=dfii_rows, dxy_rows=dxy_rows)
    md, _ = await _section_xau_specific(session, "XAU_USD")
    assert is_adr017_clean(md), "ADR-017 violation in r41 _section_xau_specific output."


# ──────────────────────────── Symmetric language doctrine ──────────────


@pytest.mark.asyncio
async def test_both_signals_emit_symmetric_branches() -> None:
    """ichor-trader r32 + r33 + r38 carry-forward + r40 R24 mirror :
    every interpretive section MUST emit BOTH branches (gold-soft AND
    gold-bid) so the Pass-2 LLM picks consistent with the Pass-1 regime."""
    dfii_rows = [
        (date(2026, 5, 13), Decimal("2.10")),
        (date(2026, 5, 12), Decimal("2.08")),
        (date(2026, 5, 9), Decimal("2.05")),
        (date(2026, 5, 8), Decimal("2.04")),
        (date(2026, 5, 7), Decimal("2.00")),
        (date(2026, 5, 6), Decimal("1.95")),
    ]
    dxy_rows = [
        (date(2026, 5, 13), Decimal("105.30")),
        (date(2026, 5, 12), Decimal("105.10")),
        (date(2026, 5, 9), Decimal("104.80")),
        (date(2026, 5, 8), Decimal("104.50")),
        (date(2026, 5, 7), Decimal("104.20")),
        (date(2026, 5, 6), Decimal("104.00")),
    ]
    session = _mock_session_multi(dfii_rows=dfii_rows, dxy_rows=dxy_rows)
    md, _ = await _section_xau_specific(session, "XAU_USD")
    # DFII10 block symmetric
    assert "XAU-soft" in md
    assert "XAU-bid" in md
    assert "calm regime" in md.lower()
    assert "safe-haven" in md.lower()
    # DTWEXBGS block symmetric
    assert "broken-smile" in md.lower() or "co-bid" in md.lower()
    assert "gold-soft" in md.lower()
    # Composite triangle clarifies opposite-vs-co-move
    assert "OPPOSITE" in md or "opposite" in md.lower()
    assert "CO-MOVE" in md or "co-move" in md.lower() or "CO-MOVES" in md


# ──────────────────────────── Tetlock invalidation discipline ──────────


@pytest.mark.asyncio
async def test_tetlock_invalidation_thresholds_inline() -> None:
    """r39+ doctrine, r40 R23 ichor-trader default-round-opener
    confirmation : threshold-flip conditions MUST be emitted inline
    so a falsified hypothesis is visible immediately."""
    dfii_rows = [
        (date(2026, 5, 13), Decimal("2.10")),
        (date(2026, 5, 12), Decimal("2.08")),
        (date(2026, 5, 9), Decimal("2.05")),
        (date(2026, 5, 8), Decimal("2.04")),
        (date(2026, 5, 7), Decimal("2.00")),
        (date(2026, 5, 6), Decimal("1.95")),
    ]
    dxy_rows = [
        (date(2026, 5, 13), Decimal("105.30")),
        (date(2026, 5, 12), Decimal("105.10")),
        (date(2026, 5, 9), Decimal("104.80")),
        (date(2026, 5, 8), Decimal("104.50")),
        (date(2026, 5, 7), Decimal("104.20")),
        (date(2026, 5, 6), Decimal("104.00")),
    ]
    session = _mock_session_multi(dfii_rows=dfii_rows, dxy_rows=dxy_rows)
    md, _ = await _section_xau_specific(session, "XAU_USD")
    # Tetlock keyword present at least twice (once per signal)
    assert md.count("Tetlock invalidation") >= 2
    # Specific thresholds visible (DFII10 +20 bp r41-ichor-trader-YELLOW
    # calibration ; VIX < 16, SKEW < 135 vol-of-vol regime)
    assert "+20 bp" in md
    assert "VIX drops below 16" in md or "VIX < 16" in md
    assert "SKEW < 135" in md or "SKEW &lt; 135" in md
    # DTWEXBGS threshold +1.5% on DTWEXBGS move ; +50 bp delta on HY OAS
    # (r41-ichor-trader-YELLOW : cycle-invariant delta semantics not
    # absolute-level which drifts with the cycle)
    assert "1.5%" in md
    assert "+50 bp" in md


# ──────────────────────────── Source-stamp format pinned ───────────────


@pytest.mark.asyncio
async def test_source_stamp_format_pinned_dfii10_only() -> None:
    """Regression guard : DFII10 source stamp format pinned. Critic must
    verify each source. Format = `FRED:DFII10@YYYY-MM-DD`."""
    dfii_rows = [(date(2026, 4, 1), Decimal("1.85"))]
    session = _mock_session_multi(dfii_rows=dfii_rows, dxy_rows=[])
    _, sources = await _section_xau_specific(session, "XAU_USD")
    assert sources == ["FRED:DFII10@2026-04-01"]


@pytest.mark.asyncio
async def test_source_stamp_format_pinned_dxy() -> None:
    """DTWEXBGS source stamp format `FRED:DTWEXBGS@YYYY-MM-DD`."""
    dfii_rows = [(date(2026, 5, 13), Decimal("2.10"))]
    dxy_rows = [(date(2026, 5, 12), Decimal("105.30"))]
    session = _mock_session_multi(dfii_rows=dfii_rows, dxy_rows=dxy_rows)
    _, sources = await _section_xau_specific(session, "XAU_USD")
    assert "FRED:DTWEXBGS@2026-05-12" in sources
    assert sources == [
        "FRED:DFII10@2026-05-13",
        "FRED:DTWEXBGS@2026-05-12",
    ]
