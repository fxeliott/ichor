"""Unit tests for `_section_eur_specific` — ADR-090 P0 step-3 (r32) + step-4 (r34).

Verifies the multi-signal EUR-side data-pool section :
  1. Asset gate : non-EUR_USD assets return ("", []) without DB I/O.
  2. Empty Bund table : returns ("", []) so build_data_pool skips.
  3. Single-row Bund case : renders Bund level only.
  4. Six-row Bund case : Bund + 5-day delta + interpretation hint.
  5. €STR addition (round-34) : when estr_observations has rows, section
     includes €STR level + delta + symmetric interpretation.
  6. BTP-via-FRED addition (round-34) : when FRED `IRLTLT01ITM156N` is
     available, section includes BTP-Bund spread + frequency mismatch
     warning + symmetric language.
  7. Source-stamp format pinned (Bund + €STR + FRED).
  8. ADR-017 boundary : all rendered text passes the r32 hardened filter.
  9. Symmetric language preserved (both interpretive branches).

Uses `AsyncMock` + `MagicMock` + side_effect for the multi-query
session, plus monkeypatch of `_latest_fred` for the FRED inline call.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from ichor_api.services.adr017_filter import is_adr017_clean
from ichor_api.services.data_pool import _section_eur_specific


def _mock_session_multi(*, bund_rows=None, estr_rows=None) -> AsyncMock:
    """Build an AsyncMock session that returns DIFFERENT result rows
    for successive `await session.execute(stmt)` calls.

    Call 1 → Bund rows (or [] if not provided).
    Call 2 → €STR rows (or [] if not provided).
    """
    bund_rows = bund_rows or []
    estr_rows = estr_rows or []

    bund_result = MagicMock()
    bund_result.all.return_value = bund_rows
    estr_result = MagicMock()
    estr_result.all.return_value = estr_rows

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[bund_result, estr_result])
    return session


# ──────────────────────────── Asset gate ──────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "asset",
    ["GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD", "XAU_USD", "NAS100_USD", "SPX500_USD"],
)
async def test_returns_empty_on_non_eur_asset(asset: str) -> None:
    """Asset gate : only EUR_USD renders. Zero DB I/O on non-EUR."""
    session = AsyncMock()
    md, sources = await _section_eur_specific(session, asset)
    assert md == ""
    assert sources == []
    assert session.execute.await_count == 0


# ──────────────────────────── Empty Bund table ──────────────────────────


@pytest.mark.asyncio
async def test_returns_empty_when_bund_table_empty(monkeypatch) -> None:
    """Empty `bund_10y_observations` → silent skip (Bund is the anchor
    signal ; without it, the section returns ('', [])). Even if €STR
    or BTP would have data, the section refuses to render without Bund."""
    session = _mock_session_multi(bund_rows=[], estr_rows=[])
    # _latest_fred shouldn't even be called in this path
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        AsyncMock(return_value=None),
    )
    md, sources = await _section_eur_specific(session, "EUR_USD")
    assert md == ""
    assert sources == []


# ──────────────────────────── Bund only path ──────────────────────────


@pytest.mark.asyncio
async def test_renders_bund_only_when_estr_empty_and_fred_none(monkeypatch) -> None:
    """Bund table has rows but €STR table empty + FRED returns None
    → section renders Bund block only (graceful degradation)."""
    bund_rows = [
        (date(2026, 5, 13), Decimal("3.130")),
        (date(2026, 5, 12), Decimal("3.120")),
        (date(2026, 5, 9), Decimal("3.100")),
        (date(2026, 5, 8), Decimal("3.080")),
        (date(2026, 5, 7), Decimal("3.050")),
        (date(2026, 5, 6), Decimal("3.010")),
    ]
    session = _mock_session_multi(bund_rows=bund_rows, estr_rows=[])
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        AsyncMock(return_value=None),
    )
    md, sources = await _section_eur_specific(session, "EUR_USD")
    assert "Bund 10Y = 3.130%" in md
    assert "+12.0 bp" in md
    assert "€STR" not in md  # €STR empty → section omitted
    assert "BTP" not in md  # FRED None → section omitted
    assert sources == ["Bundesbank:BBSIS/Bund10Y@2026-05-13"]


# ──────────────────────────── Bund + €STR path ──────────────────────────


@pytest.mark.asyncio
async def test_renders_bund_plus_estr_when_both_have_rows(monkeypatch) -> None:
    """Both Bund + €STR populated → section renders BOTH blocks +
    sources include both stamps."""
    bund_rows = [
        (date(2026, 5, 13), Decimal("3.130")),
        (date(2026, 5, 12), Decimal("3.120")),
        (date(2026, 5, 9), Decimal("3.100")),
        (date(2026, 5, 8), Decimal("3.080")),
        (date(2026, 5, 7), Decimal("3.050")),
        (date(2026, 5, 6), Decimal("3.010")),
    ]
    estr_rows = [
        (date(2026, 5, 12), Decimal("1.929")),
        (date(2026, 5, 9), Decimal("1.931")),
        (date(2026, 5, 8), Decimal("1.930")),
        (date(2026, 5, 7), Decimal("1.932")),
        (date(2026, 5, 6), Decimal("1.935")),
        (date(2026, 5, 5), Decimal("1.940")),
    ]
    session = _mock_session_multi(bund_rows=bund_rows, estr_rows=estr_rows)
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        AsyncMock(return_value=None),
    )
    md, sources = await _section_eur_specific(session, "EUR_USD")
    # Bund block
    assert "Bund 10Y = 3.130%" in md
    # €STR block
    assert "€STR = 1.929%" in md
    assert "ECB Data Portal" in md
    # Spread block ABSENT (FRED None)
    assert "BTP-Bund" not in md
    # Source-stamps both present
    assert "Bundesbank:BBSIS/Bund10Y@2026-05-13" in sources
    assert "ECB:EST/ESTR@2026-05-12" in sources
    assert len(sources) == 2


# ──────────────────────────── Bund + €STR + BTP spread path ────────────


@pytest.mark.asyncio
async def test_renders_full_bund_estr_btp_spread(monkeypatch) -> None:
    """All 3 signals populated → BTP-Bund spread computed + frequency
    mismatch warning surfaced + symmetric language for spread."""
    bund_rows = [
        (date(2026, 5, 13), Decimal("3.130")),
        (date(2026, 5, 12), Decimal("3.120")),
        (date(2026, 5, 9), Decimal("3.100")),
        (date(2026, 5, 8), Decimal("3.080")),
        (date(2026, 5, 7), Decimal("3.050")),
        (date(2026, 5, 6), Decimal("3.010")),
    ]
    estr_rows = [(date(2026, 5, 12), Decimal("1.929"))]
    # FRED Italy 10Y for round-34 BTP-via-FRED inline lookup
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        AsyncMock(return_value=(3.87, date(2026, 4, 30))),  # Trading Economics r33 cross-check
    )
    session = _mock_session_multi(bund_rows=bund_rows, estr_rows=estr_rows)
    md, sources = await _section_eur_specific(session, "EUR_USD")
    assert "Bund 10Y = 3.130%" in md
    assert "€STR = 1.929%" in md
    assert "Italy 10Y = 3.87%" in md
    # Spread = BTP - Bund = 3.87 - 3.13 = +0.74 pp
    assert "+0.74 pp" in md or "+0.74" in md
    # Frequency mismatch warning required
    assert "Frequency mismatch" in md
    # Symmetric spread interpretation
    assert "fragmentation" in md.lower()
    # 3 source stamps
    assert "Bundesbank:BBSIS/Bund10Y@2026-05-13" in sources
    assert "ECB:EST/ESTR@2026-05-12" in sources
    assert "FRED:IRLTLT01ITM156N@2026-04-30" in sources
    assert len(sources) == 3


# ──────────────────────────── ADR-017 boundary ──────────────────────


@pytest.mark.asyncio
async def test_rendered_text_passes_adr017_filter(monkeypatch) -> None:
    """The rendered text (Bund + €STR + BTP spread) MUST pass the
    round-32 hardened ADR-017 filter — no BUY/SELL/TARGET tokens,
    no Unicode-confusable bypass, no FR/ES/DE imperatives. Round-34
    extension MUST NOT regress this guard."""
    bund_rows = [
        (date(2026, 5, 13), Decimal("3.130")),
        (date(2026, 5, 12), Decimal("3.120")),
        (date(2026, 5, 9), Decimal("3.100")),
        (date(2026, 5, 8), Decimal("3.080")),
        (date(2026, 5, 7), Decimal("3.050")),
        (date(2026, 5, 6), Decimal("3.010")),
    ]
    estr_rows = [
        (date(2026, 5, 12), Decimal("1.929")),
        (date(2026, 5, 9), Decimal("1.931")),
        (date(2026, 5, 8), Decimal("1.930")),
        (date(2026, 5, 7), Decimal("1.932")),
        (date(2026, 5, 6), Decimal("1.935")),
        (date(2026, 5, 5), Decimal("1.940")),
    ]
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        AsyncMock(return_value=(3.87, date(2026, 4, 30))),
    )
    session = _mock_session_multi(bund_rows=bund_rows, estr_rows=estr_rows)
    md, _ = await _section_eur_specific(session, "EUR_USD")
    assert is_adr017_clean(md), "ADR-017 violation in r34-extended _section_eur_specific output."


# ──────────────────────────── Symmetric language (all 3 signals) ─────


@pytest.mark.asyncio
async def test_all_signals_emit_symmetric_branches(monkeypatch) -> None:
    """ichor-trader r32 + r33 carry-forward : every interpretive
    section must emit BOTH branches (calm regime + funding stress)."""
    bund_rows = [(date(2026, 5, 13), Decimal("3.130"))] + [
        (date(2026, 5, 12 - i), Decimal("3.12")) for i in range(5)
    ]
    estr_rows = [(date(2026, 5, 12), Decimal("1.929"))] + [
        (date(2026, 5, 11 - i), Decimal("1.93")) for i in range(5)
    ]
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        AsyncMock(return_value=(3.87, date(2026, 4, 30))),
    )
    session = _mock_session_multi(bund_rows=bund_rows, estr_rows=estr_rows)
    md, _ = await _section_eur_specific(session, "EUR_USD")
    # Bund block symmetric
    assert "calm regime" in md.lower()
    assert "convertibility" in md.lower() or "funding stress" in md.lower()
    # €STR block symmetric (ECB tightening vs front-end stress)
    assert "ECB tightening" in md or "front-end" in md
    # BTP spread block symmetric (widening vs tightening)
    assert "Spread widening" in md or "widening" in md.lower()
    assert "Spread tightening" in md or "tightening" in md.lower()


# ──────────────────────────── Source-stamp format ──────────────────────


@pytest.mark.asyncio
async def test_source_stamp_format_pinned_bund_only(monkeypatch) -> None:
    """Regression guard : Bund source stamp format pinned. Critic must
    be able to verify each source."""
    bund_rows = [(date(2026, 4, 1), Decimal("3.500"))]
    session = _mock_session_multi(bund_rows=bund_rows, estr_rows=[])
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        AsyncMock(return_value=None),
    )
    _, sources = await _section_eur_specific(session, "EUR_USD")
    assert sources == ["Bundesbank:BBSIS/Bund10Y@2026-04-01"]


@pytest.mark.asyncio
async def test_source_stamp_format_pinned_estr(monkeypatch) -> None:
    """€STR source stamp format `ECB:EST/ESTR@YYYY-MM-DD`."""
    bund_rows = [(date(2026, 5, 13), Decimal("3.130"))]
    estr_rows = [(date(2026, 5, 12), Decimal("1.929"))]
    session = _mock_session_multi(bund_rows=bund_rows, estr_rows=estr_rows)
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        AsyncMock(return_value=None),
    )
    _, sources = await _section_eur_specific(session, "EUR_USD")
    assert "ECB:EST/ESTR@2026-05-12" in sources


@pytest.mark.asyncio
async def test_source_stamp_format_pinned_fred_btp(monkeypatch) -> None:
    """BTP-via-FRED source stamp `FRED:IRLTLT01ITM156N@YYYY-MM-DD`."""
    bund_rows = [(date(2026, 5, 13), Decimal("3.130"))]
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        AsyncMock(return_value=(3.87, date(2026, 4, 30))),
    )
    session = _mock_session_multi(bund_rows=bund_rows, estr_rows=[])
    _, sources = await _section_eur_specific(session, "EUR_USD")
    assert "FRED:IRLTLT01ITM156N@2026-04-30" in sources
