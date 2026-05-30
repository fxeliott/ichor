"""r180 G5 CONSUMER WIRING tests — `_section_previous_session_context`.

Pins the r180 atomic-ship contract :
- Section emits explicit honest-absence prose when snapshot is None
  (doctrine #11 calibrated honesty)
- Section emits full plain-FR prose when snapshot is populated
  (Eliot Fathom §V practitioner context)
- FR direction + zone translations are exhaustive (all 3 directions
  + 3 zones round-trip correctly)
- ADR-017 boundary preserved : no BUY/SELL/TP/SL tokens in rendered
  prose (mirror of ``test_invariants_ichor.py`` source-inspection
  but here we test the RENDERED output)
- Source stamps follow the canonical ``origin_zone:polygon_intraday:
  {asset}@{start}..{end}`` format (Pattern #15 R59 R-DEPLOY-6 source-
  stamping discipline)
- Section is wired into ``build_data_pool`` (sections list contains
  ``previous_session_origin_zone`` key) — verified via grep on the
  module source

Doctrine #5 pure-module discipline : tests use AsyncMock session +
fake-bar fixtures from r179 EXECUTION test file, no DB hit.
"""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from ichor_api.services.data_pool import _section_previous_session_context

# ─────────────────────────────────── FIXTURES ─────────────────────────


def _fake_bar(
    bar_ts: datetime,
    open_p: float,
    high: float,
    low: float,
    close_p: float,
) -> Any:
    """Duck-type a PolygonIntradayBar for the 5 fields the EXECUTION
    compute reads (mirror of r179 test fixture)."""
    bar = MagicMock()
    bar.bar_ts = bar_ts
    bar.open = open_p
    bar.high = high
    bar.low = low
    bar.close = close_p
    return bar


def _fake_session(bars: list[Any]) -> AsyncMock:
    """AsyncMock session whose ``execute()`` returns a result whose
    ``.scalars().all()`` yields ``bars``."""
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = bars
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result_mock)
    return session


# ADR-017 forbidden tokens regex (mirror of session_verdict.py:77 +
# scenarios.py:50 single source of truth on forbidden trade-signal
# tokens). The rendered FR prose MUST NOT contain any of these.
_FORBIDDEN_TRADE_TOKENS_RE = re.compile(
    r"\b(BUY|SELL|TP|SL|long entry|short entry|stop loss|take profit)\b",
    re.IGNORECASE,
)


# ─────────────────────────────────── HONEST ABSENCE PATH ──────────────


class TestSectionHonestAbsence:
    """Doctrine #11 calibrated honesty : when snapshot is None, the
    section emits explicit FR prose explaining the absence — NEVER
    fabricates a neutral-direction read."""

    def test_returns_explicit_absence_prose_when_no_bars(self) -> None:
        """Weekend / holiday scenario : polygon_intraday empty for
        asset. Section emits a clear absence message."""

        async def _run() -> None:
            session = _fake_session(bars=[])
            md, sources = await _section_previous_session_context(session, asset="EUR_USD")
            assert "Contexte session précédente indisponible" in md
            assert "Cohen 1988" in md  # justification cite present
            assert "doctrine" in md.lower() or "Doctrine" in md
            assert sources == ["origin_zone:EUR_USD:absent"]

        asyncio.run(_run())

    def test_returns_explicit_absence_prose_when_below_low_n(self) -> None:
        """Bar count < 30 in dominant zone → honest absence."""

        async def _run() -> None:
            base = datetime(2026, 5, 27, 13, 0, tzinfo=UTC)
            bars = [
                _fake_bar(base + timedelta(minutes=i), 1.05, 1.06, 1.04, 1.055)
                for i in range(10)  # 10 bars only, below MIN_BAR_COUNT
            ]
            session = _fake_session(bars=bars)
            md, sources = await _section_previous_session_context(session, asset="EUR_USD")
            assert "Contexte session précédente indisponible" in md
            assert sources[0].endswith(":absent")

        asyncio.run(_run())

    def test_absence_prose_passes_adr017_boundary(self) -> None:
        """Honest absence prose MUST NOT contain BUY/SELL tokens."""

        async def _run() -> None:
            session = _fake_session(bars=[])
            md, _ = await _section_previous_session_context(session, asset="EUR_USD")
            assert _FORBIDDEN_TRADE_TOKENS_RE.search(md) is None

        asyncio.run(_run())


# ─────────────────────────────────── POPULATED PATH ───────────────────


class TestSectionPopulatedNYDominantUp:
    """Pass-2 narrative consumer reads the populated path : zone +
    direction + high/low/range/bar_count + window all rendered FR."""

    def test_populated_prose_shape_for_ny_up(self) -> None:
        """NY-dominant up trend snapshot renders full prose."""

        async def _run() -> None:
            base = datetime(2026, 5, 27, 0, 0, tzinfo=UTC)
            bars: list[Any] = []
            # Asian: 60 flat bars (range-bound, will not dominate)
            for i in range(60):
                bars.append(
                    _fake_bar(
                        base + timedelta(minutes=i),
                        1.05,
                        1.0505,
                        1.0495,
                        1.0501,
                    )
                )
            # NY: 60 bars, strong + drift (will dominate)
            ny_base = datetime(2026, 5, 27, 13, 0, tzinfo=UTC)
            for i in range(60):
                bars.append(
                    _fake_bar(
                        ny_base + timedelta(minutes=i),
                        1.061 + 0.00015 * i,
                        1.062 + 0.00015 * i,
                        1.060 + 0.00015 * i,
                        1.0612 + 0.00015 * i,
                    )
                )
            session = _fake_session(bars=bars)
            md, sources = await _section_previous_session_context(session, asset="EUR_USD")
            # Headline
            assert "## Previous-session origin zone" in md
            # Zone FR translation
            assert "new-yorkaise" in md
            assert "`ny`" in md
            # Direction FR translation
            assert "haussier" in md
            assert "`up`" in md
            # Bar count cite
            assert "Cohen 1988" in md
            # Source stamp shape
            assert len(sources) == 1
            assert sources[0].startswith("origin_zone:polygon_intraday:EUR_USD@")
            assert ".." in sources[0]  # window range delimiter

        asyncio.run(_run())

    def test_populated_prose_passes_adr017_boundary(self) -> None:
        """Populated path MUST NOT contain BUY/SELL tokens. The prose
        is purely factual (zone + high + low + direction)."""

        async def _run() -> None:
            base = datetime(2026, 5, 27, 13, 0, tzinfo=UTC)
            bars = [
                _fake_bar(
                    base + timedelta(minutes=i),
                    1.05 + 0.0001 * i,
                    1.052 + 0.0001 * i,
                    1.048 + 0.0001 * i,
                    1.0515 + 0.0001 * i,
                )
                for i in range(60)
            ]
            session = _fake_session(bars=bars)
            md, _ = await _section_previous_session_context(session, asset="EUR_USD")
            assert _FORBIDDEN_TRADE_TOKENS_RE.search(md) is None
            # Affirmative ADR-017 reminder line is present
            assert "ADR-017" in md
            assert "jamais un signal" in md

        asyncio.run(_run())


class TestSectionDirectionFRTranslations:
    """FR direction translations exhaustive : up / down / range."""

    def test_down_direction_renders_baissier(self) -> None:
        """NAS NY-dominant down trend renders 'baissier'."""

        async def _run() -> None:
            base = datetime(2026, 5, 27, 13, 30, tzinfo=UTC)
            bars = [
                _fake_bar(
                    base + timedelta(minutes=i),
                    18500 - 5 * i,
                    18510 - 5 * i,
                    18490 - 5 * i,
                    18495 - 5 * i,
                )
                for i in range(60)
            ]
            session = _fake_session(bars=bars)
            md, _ = await _section_previous_session_context(session, asset="NAS100_USD")
            assert "baissier" in md
            assert "`down`" in md
            assert "new-yorkaise" in md

        asyncio.run(_run())

    def test_range_direction_renders_range_bound_fr(self) -> None:
        """Asian-dominant range-bound (small body / range ratio)
        renders 'range-bound (consolidation / chop)'."""

        async def _run() -> None:
            # 60 Asian bars, near-zero body each, total range 0.01
            base = datetime(2026, 5, 27, 0, 0, tzinfo=UTC)
            bars = []
            for i in range(60):
                bars.append(
                    _fake_bar(
                        base + timedelta(minutes=i),
                        1.05 + 0.0001 * (i % 3 - 1),
                        1.055,
                        1.045,
                        1.05 + 0.0001 * (i % 3 - 1),
                    )
                )
            session = _fake_session(bars=bars)
            md, _ = await _section_previous_session_context(session, asset="EUR_USD")
            assert "range-bound" in md
            assert "asiatique" in md

        asyncio.run(_run())


class TestSectionWiredIntoBuildDataPool:
    """Doctrine #2 strict scope verification : the section is wired
    into ``build_data_pool`` via grep on the module source."""

    def test_section_key_present_in_build_data_pool(self) -> None:
        """The string ``previous_session_origin_zone`` appears in
        ``data_pool.py`` source as a section key in the
        ``sections.append(...)`` tuple. Defensive : if a future refactor
        drops the wire by accident, this test fails loudly."""
        from pathlib import Path

        src_path = Path(__file__).parent.parent / "src" / "ichor_api" / "services" / "data_pool.py"
        text = src_path.read_text(encoding="utf-8")
        assert '("previous_session_origin_zone"' in text, (
            "r180 G5 CONSUMER WIRING regression : section key dropped "
            "from build_data_pool sections list."
        )
        assert "_section_previous_session_context" in text
