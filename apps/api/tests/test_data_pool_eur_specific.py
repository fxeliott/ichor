"""Unit tests for `_section_eur_specific` — ADR-090 P0 step-3 (round-32).

Verifies :
  1. Asset gate : non-EUR_USD assets return ("", []) without DB I/O.
  2. Empty Bund table : returns ("", []) so build_data_pool skips.
  3. Single-row case : renders level, no delta line.
  4. Six-row case : renders level + 5-trading-day delta + symmetric
     interpretation hint.
  5. Source-stamp format pinned ("Bundesbank:BBSIS/Bund10Y@YYYY-MM-DD").
  6. ADR-017 boundary : rendered text contains zero forbidden tokens
     (validated via the round-32 hardened `services.adr017_filter`).
  7. Symmetric language : rendered text mentions BOTH possible
     EUR-direction interpretations (calm regime + funding stress),
     never picks one (ichor-trader round-32 review YELLOW fix).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from ichor_api.services.adr017_filter import is_adr017_clean
from ichor_api.services.data_pool import _section_eur_specific


def _mock_session_with_rows(rows: list[tuple[date, Decimal]]) -> AsyncMock:
    """Return an AsyncMock session whose `execute(...)` returns the
    given rows shaped as a SQLAlchemy result."""
    result_proxy = MagicMock()
    result_proxy.all.return_value = rows
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result_proxy)
    return session


# ──────────────────────────── Asset gate ──────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "asset",
    ["GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD", "XAU_USD", "NAS100_USD", "SPX500_USD"],
)
async def test_returns_empty_on_non_eur_asset(asset: str) -> None:
    """Asset gate : only EUR_USD renders. Other Phase-1 assets get
    a clean empty response WITHOUT touching the DB (early-return
    BEFORE the SQLAlchemy execute call)."""
    session = AsyncMock()
    md, sources = await _section_eur_specific(session, asset)
    assert md == ""
    assert sources == []
    # Crucial : zero DB query was issued — the asset gate runs
    # before any `session.execute` call.
    assert session.execute.await_count == 0


# ──────────────────────────── Empty table ──────────────────────────────


@pytest.mark.asyncio
async def test_returns_empty_when_zero_rows() -> None:
    """Empty `bund_10y_observations` (pre-deploy state OR collector
    dormant) → ('', []) so `build_data_pool` silently skips the
    section. NO crash, NO partial render."""
    session = _mock_session_with_rows([])
    md, sources = await _section_eur_specific(session, "EUR_USD")
    assert md == ""
    assert sources == []


# ──────────────────────────── Single-row case ──────────────────────────


@pytest.mark.asyncio
async def test_renders_single_row_without_delta() -> None:
    """1 row in the table → render the level, omit the delta line."""
    session = _mock_session_with_rows([(date(2026, 5, 13), Decimal("3.130"))])
    md, sources = await _section_eur_specific(session, "EUR_USD")
    assert "Bund 10Y = 3.130%" in md
    assert "2026-05-13" in md
    assert "5-trading-day change" not in md  # only 1 row → no delta
    assert sources == ["Bundesbank:BBSIS/Bund10Y@2026-05-13"]


# ──────────────────────────── 6-row delta case ──────────────────────────


@pytest.mark.asyncio
async def test_renders_six_rows_with_positive_delta() -> None:
    """6 rows → render level + 5-day delta (basis points) + symmetric
    interpretation hint. Yield rise 3.01 → 3.13 = +12 bp."""
    session = _mock_session_with_rows(
        [
            (date(2026, 5, 13), Decimal("3.130")),  # latest
            (date(2026, 5, 12), Decimal("3.120")),
            (date(2026, 5, 9), Decimal("3.100")),
            (date(2026, 5, 8), Decimal("3.080")),
            (date(2026, 5, 7), Decimal("3.050")),
            (date(2026, 5, 6), Decimal("3.010")),  # ~5 trading days ago
        ]
    )
    md, sources = await _section_eur_specific(session, "EUR_USD")
    assert "Bund 10Y = 3.130%" in md
    assert "+12.0 bp" in md  # 3.130% - 3.010% = 12.0 bp
    assert "2026-05-06" in md  # prior date


@pytest.mark.asyncio
async def test_renders_six_rows_with_negative_delta() -> None:
    """Yield fall 3.20 → 3.13 = -7 bp. Minus sign uses Unicode
    '−' (U+2212) for typographic correctness."""
    session = _mock_session_with_rows(
        [
            (date(2026, 5, 13), Decimal("3.130")),
            (date(2026, 5, 12), Decimal("3.150")),
            (date(2026, 5, 9), Decimal("3.170")),
            (date(2026, 5, 8), Decimal("3.180")),
            (date(2026, 5, 7), Decimal("3.190")),
            (date(2026, 5, 6), Decimal("3.200")),
        ]
    )
    md, sources = await _section_eur_specific(session, "EUR_USD")
    # 3.130 - 3.200 = -0.070% = -7.0 bp ; sign char is '−' (minus)
    assert "−7.0 bp" in md or "-7.0 bp" in md


# ──────────────────────────── Source-stamp format ──────────────────────


@pytest.mark.asyncio
async def test_source_stamp_format_pinned() -> None:
    """Critic must be able to verify the source. Format is
    `Bundesbank:BBSIS/Bund10Y@YYYY-MM-DD` — a future reformat
    breaks Pass-2's `mechanisms[].sources[]` round-trip."""
    session = _mock_session_with_rows([(date(2026, 4, 1), Decimal("3.500"))])
    _, sources = await _section_eur_specific(session, "EUR_USD")
    assert sources == ["Bundesbank:BBSIS/Bund10Y@2026-04-01"]


# ──────────────────────────── ADR-017 boundary ──────────────────────


@pytest.mark.asyncio
async def test_rendered_text_passes_adr017_filter() -> None:
    """The rendered text MUST pass the round-32 hardened ADR-017
    filter — no BUY/SELL/TARGET/ENTRY/leverage/MARGIN CALL tokens,
    no Unicode-confusable bypass surface, no FR/ES/DE imperatives.

    Even though the section is pure-numeric data, the symmetric
    interpretation language could regress into directive phrasing
    on a future edit. This guard catches that drift."""
    session = _mock_session_with_rows(
        [
            (date(2026, 5, 13), Decimal("3.130")),
            (date(2026, 5, 12), Decimal("3.120")),
            (date(2026, 5, 9), Decimal("3.100")),
            (date(2026, 5, 8), Decimal("3.080")),
            (date(2026, 5, 7), Decimal("3.050")),
            (date(2026, 5, 6), Decimal("3.010")),
        ]
    )
    md, _ = await _section_eur_specific(session, "EUR_USD")
    assert is_adr017_clean(md), (
        "ADR-017 violation in _section_eur_specific output : "
        "the symmetric interpretation language regressed into "
        "directive phrasing. The boundary is non-negotiable."
    )


# ──────────────────────────── Symmetric language ──────────────────────


@pytest.mark.asyncio
async def test_renders_both_eur_directions_when_delta_present() -> None:
    """ichor-trader round-32 review YELLOW : the rendered text MUST
    NOT bias toward ONE interpretation of a Bund yield move. Both
    "EUR-positive in calm regime" AND "EUR-negative under funding
    stress" must be mentioned. The Pass-2 LLM picks based on the
    Pass-1 regime label."""
    session = _mock_session_with_rows(
        [
            (date(2026, 5, 13), Decimal("3.130")),
            (date(2026, 5, 12), Decimal("3.120")),
            (date(2026, 5, 9), Decimal("3.100")),
            (date(2026, 5, 8), Decimal("3.080")),
            (date(2026, 5, 7), Decimal("3.050")),
            (date(2026, 5, 6), Decimal("3.010")),
        ]
    )
    md, _ = await _section_eur_specific(session, "EUR_USD")
    # Both interpretive branches must appear.
    assert "regime" in md.lower()
    assert "rate differential" in md.lower() or "rate diff" in md.lower()
    assert "convertibility" in md.lower() or "Bund/Treasury spread" in md
    # And the Pass-2 LLM hand-off cue.
    assert "Pass-2" in md or "Pass-1" in md


@pytest.mark.asyncio
async def test_single_row_skips_interpretation_hint() -> None:
    """The interpretation hint accompanies the delta. With no delta
    (single-row case), the hint MUST be suppressed too — emitting
    interpretive language without numeric backing is noise."""
    session = _mock_session_with_rows([(date(2026, 5, 13), Decimal("3.130"))])
    md, _ = await _section_eur_specific(session, "EUR_USD")
    assert "Interpretation depends" not in md
