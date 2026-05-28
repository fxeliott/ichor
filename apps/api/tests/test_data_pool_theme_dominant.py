"""r183 N1 Theme CONSUMER WIRING tests — `_section_theme_dominant`.

Pins the r183 atomic-ship contract :
- Section emits explicit honest-absence prose when classifier returns
  None (doctrine #11 calibrated honesty)
- Section emits full plain-FR prose when ranking is populated (Eliot
  Fathom transcript étape 1 vocabulary verbatim)
- All 8 driver FR labels round-trip correctly (exhaustive dispatch)
- ADR-017 boundary preserved : no BUY/SELL/TP/SL tokens in rendered
  prose
- Source stamps follow the canonical ``theme_dominant:{top_theme}@
  {computed_at_utc}`` format (populated) OR ``theme_dominant:{asset}:
  absent`` (honest absence)
- Section is wired into ``build_data_pool``

Doctrine #5 pure-module discipline : tests use monkeypatch on the
internal classify_dominant_theme call, no DB hit.
"""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from ichor_api.services import data_pool as dp_mod
from ichor_api.services.data_pool import _section_theme_dominant
from ichor_api.services.theme_classifier import (
    THEME_DRIVERS,
    ThemeDriverKey,
    ThemeRanking,
)

# ADR-017 forbidden tokens regex (mirror of test_data_pool_previous_
# session_context.py same regex). The rendered FR prose MUST NOT contain
# any of these.
_FORBIDDEN_TRADE_TOKENS_RE = re.compile(
    r"\b(BUY|SELL|TP|SL|long entry|short entry|stop loss|take profit)\b",
    re.IGNORECASE,
)


# ─────────────────────────────────── HONEST ABSENCE PATH ──────────────


class TestSectionHonestAbsence:
    """Doctrine #11 calibrated honesty : when classifier returns None,
    section emits explicit FR prose explaining the absence."""

    def test_returns_explicit_absence_prose_when_classifier_returns_none(
        self,
    ) -> None:
        """No dominant theme → section emits clear absence message."""

        async def _run() -> None:
            with patch.object(dp_mod, "classify_dominant_theme", AsyncMock(return_value=None)):
                md, sources = await _section_theme_dominant(session=AsyncMock(), asset="EUR_USD")
            assert "Aucun thème sous-jacent ne domine" in md
            assert "Doctrine #11" in md
            assert "ADR-017" in md
            assert sources == ["theme_dominant:EUR_USD:absent"]

        asyncio.run(_run())

    def test_absence_prose_passes_adr017_boundary(self) -> None:
        """Honest absence prose MUST NOT contain BUY/SELL tokens."""

        async def _run() -> None:
            with patch.object(dp_mod, "classify_dominant_theme", AsyncMock(return_value=None)):
                md, _ = await _section_theme_dominant(session=AsyncMock(), asset="EUR_USD")
            assert _FORBIDDEN_TRADE_TOKENS_RE.search(md) is None

        asyncio.run(_run())


# ─────────────────────────────────── POPULATED PATH ───────────────────


def _build_ranking(
    top: ThemeDriverKey,
    top_strength: float,
    secondary: list[ThemeDriverKey] | None = None,
    secondary_strength: float = 0.55,
) -> ThemeRanking:
    """Helper : build a valid ThemeRanking for tests."""
    strengths: dict[ThemeDriverKey, float] = {top: top_strength}
    if secondary:
        for s in secondary:
            strengths[s] = secondary_strength
    return ThemeRanking(
        top_theme=top,
        secondary_themes=secondary or [],
        driver_strengths=strengths,
        computed_at_utc=datetime(2026, 5, 28, 13, 0, tzinfo=UTC),
    )


class TestSectionPopulatedShape:
    """Pass-2 narrative consumer reads the populated path : top_theme +
    secondaries + strengths + provenance all rendered FR."""

    def test_populated_geopolitics_dominant(self) -> None:
        """ai_gpr elevated → geopolitics top, no secondaries."""

        async def _run() -> None:
            ranking = _build_ranking(top="geopolitics", top_strength=0.75)
            with patch.object(
                dp_mod,
                "classify_dominant_theme",
                AsyncMock(return_value=ranking),
            ):
                md, sources = await _section_theme_dominant(session=AsyncMock(), asset="XAU_USD")
            assert "## Theme sous-jacent dominant" in md
            assert "géopolitique" in md
            assert "`geopolitics`" in md
            assert "75% sur 1.0" in md
            assert "aucun driver secondaire au-dessus de 0.40" in md
            assert "Bekaert-Hoerova-Lo Duca" in md
            assert sources == [f"theme_dominant:geopolitics@{ranking.computed_at_utc.isoformat()}"]

        asyncio.run(_run())

    def test_populated_monetary_policy_with_secondaries(self) -> None:
        """FOMC + GPR + VIX panic → monetary_policy top + 2 secondaries."""

        async def _run() -> None:
            ranking = _build_ranking(
                top="monetary_policy",
                top_strength=0.95,
                secondary=["geopolitics", "market_interconnexions"],
                secondary_strength=0.7,
            )
            with patch.object(
                dp_mod,
                "classify_dominant_theme",
                AsyncMock(return_value=ranking),
            ):
                md, sources = await _section_theme_dominant(session=AsyncMock(), asset="EUR_USD")
            assert "politique monétaire" in md
            assert "`monetary_policy`" in md
            assert "95% sur 1.0" in md
            # Both secondaries rendered with their FR labels
            assert "géopolitique" in md
            assert "interconnexions marché" in md
            assert "Secondaire" in md

        asyncio.run(_run())

    def test_populated_prose_passes_adr017_boundary(self) -> None:
        """Populated path MUST NOT contain BUY/SELL tokens."""

        async def _run() -> None:
            ranking = _build_ranking(top="market_interconnexions", top_strength=0.7)
            with patch.object(
                dp_mod,
                "classify_dominant_theme",
                AsyncMock(return_value=ranking),
            ):
                md, _ = await _section_theme_dominant(session=AsyncMock(), asset="EUR_USD")
            assert _FORBIDDEN_TRADE_TOKENS_RE.search(md) is None
            assert "ADR-017" in md
            assert "jamais un signal" in md

        asyncio.run(_run())


class TestSectionAllDriversFRTranslations:
    """All 8 driver FR labels round-trip correctly (exhaustive dispatch)."""

    @pytest.mark.parametrize(
        "driver,expected_fr_fragment",
        [
            ("macroeconomic", "macroéconomique"),
            ("monetary_policy", "politique monétaire"),
            ("economic_data", "données économiques"),
            ("fiscal_policy", "politique fiscale"),
            ("market_interconnexions", "interconnexions marché"),
            ("geopolitics", "géopolitique"),
            ("price_action_flow", "price action"),
            ("supply_demand", "offre / demande"),
        ],
    )
    def test_each_driver_fr_label_renders(
        self, driver: ThemeDriverKey, expected_fr_fragment: str
    ) -> None:
        """For each of the 8 canonical drivers, the FR label fragment
        MUST appear in the rendered prose when that driver is top_theme.
        """

        async def _run() -> None:
            ranking = _build_ranking(top=driver, top_strength=0.8)
            with patch.object(
                dp_mod,
                "classify_dominant_theme",
                AsyncMock(return_value=ranking),
            ):
                md, _ = await _section_theme_dominant(session=AsyncMock(), asset="EUR_USD")
            assert expected_fr_fragment in md, (
                f"driver={driver}: expected FR fragment '{expected_fr_fragment}' "
                f"missing from rendered prose"
            )

        asyncio.run(_run())

    @pytest.mark.parametrize("driver", list(THEME_DRIVERS))
    def test_all_drivers_have_fr_label_mapping(self, driver: ThemeDriverKey) -> None:
        """Defensive : verify the driver_fr dict in the section function
        covers ALL 8 canonical drivers (no silent KeyError fallback).
        Parametrized to avoid B023 loop-variable binding."""

        async def _run() -> None:
            ranking = _build_ranking(top=driver, top_strength=0.8)
            with patch.object(
                dp_mod,
                "classify_dominant_theme",
                AsyncMock(return_value=ranking),
            ):
                md, _ = await _section_theme_dominant(session=AsyncMock(), asset="EUR_USD")
            top_line = next(line for line in md.split("\n") if "Top theme" in line)
            assert len(top_line) > len(f"- **Top theme** : `{driver}` ()") + 5

        asyncio.run(_run())


class TestSectionWiredIntoBuildDataPool:
    """Doctrine #2 strict scope verification : section wired into
    ``build_data_pool`` via grep on the module source."""

    def test_section_key_present_in_build_data_pool(self) -> None:
        """``theme_dominant`` appears as section key in build_data_pool."""
        from pathlib import Path

        src_path = Path(__file__).parent.parent / "src" / "ichor_api" / "services" / "data_pool.py"
        text = src_path.read_text(encoding="utf-8")
        assert '("theme_dominant"' in text, (
            "r183 N1 CONSUMER WIRING regression : section key dropped "
            "from build_data_pool sections list."
        )
        assert "_section_theme_dominant" in text
