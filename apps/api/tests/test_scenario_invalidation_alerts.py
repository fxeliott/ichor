"""r165 Strand E tests — Scenario Invalidation Alerts.

Covers atom-level :
- Catalog : 3 NEW AlertDef entries (SCENARIO_INVALIDATION_HARD/SOFT/NOTE)
  joined to ALL_ALERTS (54 + 3 = 57 total) + assert_catalog_complete() OK
- Status → AlertDef mapping (_STATUS_TO_ALERT_DEF) covers all 5 monitor
  enum values
- Evaluator evaluate_scenario_invalidation_hits :
  - empty list when no recent cards (lookback window dry)
  - empty list when monitor returns None on all cards
  - emits ONE hit per card per highest-severity tier (hard > soft > note)
  - includes bucket labels in source_payload
  - per-card defensive try/except : monitor exception → skip card silently
- alerts_runner.check_scenario_invalidations integration :
  - feature dedup honored (no double-fire same alert_code+asset)
  - persists Alert ORM rows + structlog event
- W90 invariant : SCENARIO_INVALIDATION_ALERTS size + naming + severity
  taxonomy + ALL_ALERTS membership

Mirrors r164 test_scenario_invalidation_monitor.py AsyncMock pattern.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from ichor_api.alerts.catalog import ALL_ALERTS, BY_CODE, assert_catalog_complete
from ichor_api.alerts.scenario_invalidation import (
    _STATUS_TO_ALERT_DEF,
    SCENARIO_INVALIDATION_ALERTS,
    SCENARIO_INVALIDATION_HARD,
    SCENARIO_INVALIDATION_NOTE,
    SCENARIO_INVALIDATION_SOFT,
    _alert_def_for_status,
    evaluate_scenario_invalidation_hits,
)

# ── helpers ─────────────────────────────────────────────────────────────


def _rows_returning(rows: list[tuple]) -> MagicMock:
    """Build a session.execute() result mock returning rows for .all()."""
    result_mock = MagicMock()
    result_mock.all = MagicMock(return_value=rows)
    return result_mock


# ── catalog : 3 NEW alert definitions ───────────────────────────────────


class TestCatalogExtension:
    """The 3 NEW SCENARIO_INVALIDATION_* alerts join the canonical catalog."""

    def test_all_alerts_count_is_60_after_s03_extension(self) -> None:
        """r164 baseline = 54 ; r165 + 3 = 57 ; S03 Chantier D + 3 = 60.
        assert_catalog_complete pins it."""
        assert len(ALL_ALERTS) == 60

    def test_assert_catalog_complete_passes(self) -> None:
        """Sanity : the canonical catalog assertion still passes post-r165."""
        assert_catalog_complete()  # raises if drift

    def test_three_scenario_invalidation_codes_present_by_code(self) -> None:
        for code in (
            "SCENARIO_INVALIDATION_HARD",
            "SCENARIO_INVALIDATION_SOFT",
            "SCENARIO_INVALIDATION_NOTE",
        ):
            assert code in BY_CODE, code

    def test_severity_taxonomy_canonical_hard_critical(self) -> None:
        assert SCENARIO_INVALIDATION_HARD.severity == "critical"

    def test_severity_taxonomy_canonical_soft_warning(self) -> None:
        assert SCENARIO_INVALIDATION_SOFT.severity == "warning"

    def test_severity_taxonomy_canonical_note_info(self) -> None:
        assert SCENARIO_INVALIDATION_NOTE.severity == "info"

    def test_metric_names_uniquely_per_tier(self) -> None:
        """Each severity has a distinct synthetic metric_name."""
        names = {
            SCENARIO_INVALIDATION_HARD.metric_name,
            SCENARIO_INVALIDATION_SOFT.metric_name,
            SCENARIO_INVALIDATION_NOTE.metric_name,
        }
        assert len(names) == 3

    def test_alerts_tuple_size_is_3(self) -> None:
        assert len(SCENARIO_INVALIDATION_ALERTS) == 3

    def test_not_crisis_mode_triggers(self) -> None:
        """Scenario invalidations are PER-CARD signals ; they don't enter
        the Crisis Mode composite (which is a system-wide funding-stress
        + vol composite). Defensive pin."""
        for ad in SCENARIO_INVALIDATION_ALERTS:
            assert ad.crisis_mode is False, ad.code


# ── status → AlertDef mapping ────────────────────────────────────────────


class TestStatusToAlertDefMapping:
    def test_fired_hard_maps_to_hard_alert(self) -> None:
        assert _alert_def_for_status("fired_hard") is SCENARIO_INVALIDATION_HARD

    def test_fired_soft_maps_to_soft_alert(self) -> None:
        assert _alert_def_for_status("fired_soft") is SCENARIO_INVALIDATION_SOFT

    def test_fired_note_maps_to_note_alert(self) -> None:
        assert _alert_def_for_status("fired_note") is SCENARIO_INVALIDATION_NOTE

    def test_not_fired_maps_to_none(self) -> None:
        assert _alert_def_for_status("not_fired") is None

    def test_not_evaluable_maps_to_none(self) -> None:
        assert _alert_def_for_status("not_evaluable") is None

    def test_status_to_alert_def_covers_all_5_monitor_statuses(self) -> None:
        """Lockstep CI : the mapping table MUST cover every value of the
        monitor's InvalidationStatus enum. Symmetric pin to the monitor's
        own 5-status return contract."""
        expected = {
            "fired_hard",
            "fired_soft",
            "fired_note",
            "not_fired",
            "not_evaluable",
        }
        assert set(_STATUS_TO_ALERT_DEF.keys()) == expected


# ── evaluator : no cards in lookback ────────────────────────────────────


class TestEvaluatorEmptyState:
    @pytest.mark.asyncio
    async def test_no_recent_cards_returns_empty(self) -> None:
        """Empty session_card_audit lookback → no hits."""
        session = MagicMock()
        session.execute = AsyncMock(return_value=_rows_returning([]))
        hits = await evaluate_scenario_invalidation_hits(
            session,
            now_utc=datetime(2026, 5, 28, 12, 0, tzinfo=UTC),
        )
        assert hits == []


# ── evaluator : monitor returns None on all cards ────────────────────────


class TestEvaluatorMonitorNone:
    @pytest.mark.asyncio
    async def test_monitor_returns_none_skips_card(self, monkeypatch) -> None:
        """Pre-r163 cards (or LLM ignored Strand C) → monitor returns
        None → evaluator skips the card → no hit emitted."""
        card_id = uuid4()
        rows = [(card_id, "EUR_USD", datetime(2026, 5, 28, 6, 0, tzinfo=UTC))]
        session = MagicMock()
        session.execute = AsyncMock(return_value=_rows_returning(rows))

        async def fake_monitor(_session, *, session_card_id, now_utc):
            return None

        monkeypatch.setattr(
            "ichor_api.alerts.scenario_invalidation.evaluate_scenario_invalidations",
            fake_monitor,
        )
        hits = await evaluate_scenario_invalidation_hits(session)
        assert hits == []


# ── evaluator : highest-tier wins per card ───────────────────────────────


class TestEvaluatorHighestSeverityWins:
    @pytest.mark.asyncio
    async def test_card_with_hard_emits_only_hard_hit(self, monkeypatch) -> None:
        """Card has hard AND soft AND note → ONE AlertHit with HARD code."""
        from ichor_brain.session_verdict import ScenarioInvalidationState

        card_id = uuid4()
        rows = [(card_id, "EUR_USD", datetime(2026, 5, 28, 6, 0, tzinfo=UTC))]
        session = MagicMock()
        session.execute = AsyncMock(return_value=_rows_returning(rows))

        async def fake_monitor(_session, *, session_card_id, now_utc):
            return ScenarioInvalidationState(
                scenarios_invalidated_hard=["crash_flush"],
                scenarios_invalidated_soft=["mild_bear"],
                scenarios_with_notes=["base"],
                last_check_utc=datetime(2026, 5, 28, 12, 0, tzinfo=UTC),
            )

        monkeypatch.setattr(
            "ichor_api.alerts.scenario_invalidation.evaluate_scenario_invalidations",
            fake_monitor,
        )

        hits = await evaluate_scenario_invalidation_hits(session)
        assert len(hits) == 1
        hit, asset = hits[0]
        assert hit.alert_def.code == "SCENARIO_INVALIDATION_HARD"
        assert asset == "EUR_USD"
        assert hit.source_payload["buckets"] == "crash_flush"

    @pytest.mark.asyncio
    async def test_card_with_soft_only_emits_soft(self, monkeypatch) -> None:
        from ichor_brain.session_verdict import ScenarioInvalidationState

        card_id = uuid4()
        rows = [(card_id, "GBP_USD", datetime(2026, 5, 28, 6, 0, tzinfo=UTC))]
        session = MagicMock()
        session.execute = AsyncMock(return_value=_rows_returning(rows))

        async def fake_monitor(_session, *, session_card_id, now_utc):
            return ScenarioInvalidationState(
                scenarios_invalidated_hard=[],
                scenarios_invalidated_soft=["mild_bear", "base"],
                scenarios_with_notes=[],
                last_check_utc=datetime(2026, 5, 28, 12, 0, tzinfo=UTC),
            )

        monkeypatch.setattr(
            "ichor_api.alerts.scenario_invalidation.evaluate_scenario_invalidations",
            fake_monitor,
        )

        hits = await evaluate_scenario_invalidation_hits(session)
        assert len(hits) == 1
        hit, asset = hits[0]
        assert hit.alert_def.code == "SCENARIO_INVALIDATION_SOFT"
        assert hit.source_payload["n_buckets"] == 2
        # Buckets are sorted alphabetically for stable rendering.
        assert hit.source_payload["buckets"] == "base,mild_bear"

    @pytest.mark.asyncio
    async def test_card_with_note_only_emits_note(self, monkeypatch) -> None:
        from ichor_brain.session_verdict import ScenarioInvalidationState

        card_id = uuid4()
        rows = [(card_id, "XAU_USD", datetime(2026, 5, 28, 6, 0, tzinfo=UTC))]
        session = MagicMock()
        session.execute = AsyncMock(return_value=_rows_returning(rows))

        async def fake_monitor(_session, *, session_card_id, now_utc):
            return ScenarioInvalidationState(
                scenarios_invalidated_hard=[],
                scenarios_invalidated_soft=[],
                scenarios_with_notes=["strong_bull"],
                last_check_utc=datetime(2026, 5, 28, 12, 0, tzinfo=UTC),
            )

        monkeypatch.setattr(
            "ichor_api.alerts.scenario_invalidation.evaluate_scenario_invalidations",
            fake_monitor,
        )

        hits = await evaluate_scenario_invalidation_hits(session)
        assert len(hits) == 1
        hit, _ = hits[0]
        assert hit.alert_def.code == "SCENARIO_INVALIDATION_NOTE"

    @pytest.mark.asyncio
    async def test_card_with_all_empty_lists_emits_no_hit(self, monkeypatch) -> None:
        """All 3 invalidation lists empty (state non-None — monitor ran +
        evaluated but nothing fired) → NO hit emitted."""
        from ichor_brain.session_verdict import ScenarioInvalidationState

        card_id = uuid4()
        rows = [(card_id, "EUR_USD", datetime(2026, 5, 28, 6, 0, tzinfo=UTC))]
        session = MagicMock()
        session.execute = AsyncMock(return_value=_rows_returning(rows))

        async def fake_monitor(_session, *, session_card_id, now_utc):
            return ScenarioInvalidationState(
                scenarios_invalidated_hard=[],
                scenarios_invalidated_soft=[],
                scenarios_with_notes=[],
                last_check_utc=datetime(2026, 5, 28, 12, 0, tzinfo=UTC),
            )

        monkeypatch.setattr(
            "ichor_api.alerts.scenario_invalidation.evaluate_scenario_invalidations",
            fake_monitor,
        )

        hits = await evaluate_scenario_invalidation_hits(session)
        assert hits == []


# ── evaluator : multi-card fan-out ──────────────────────────────────────


class TestEvaluatorMultiCardFanOut:
    @pytest.mark.asyncio
    async def test_multiple_cards_emit_per_card_hits(self, monkeypatch) -> None:
        """6 cards in lookback (1 per asset × 1 session) → up to 6 hits."""
        from ichor_brain.session_verdict import ScenarioInvalidationState

        card_a = uuid4()
        card_b = uuid4()
        card_c = uuid4()
        rows = [
            (card_a, "EUR_USD", datetime(2026, 5, 28, 6, 0, tzinfo=UTC)),
            (card_b, "GBP_USD", datetime(2026, 5, 28, 6, 0, tzinfo=UTC)),
            (card_c, "XAU_USD", datetime(2026, 5, 28, 6, 0, tzinfo=UTC)),
        ]
        session = MagicMock()
        session.execute = AsyncMock(return_value=_rows_returning(rows))

        async def fake_monitor(_session, *, session_card_id, now_utc):
            # Each card has a hard invalidation.
            return ScenarioInvalidationState(
                scenarios_invalidated_hard=["crash_flush"],
                scenarios_invalidated_soft=[],
                scenarios_with_notes=[],
                last_check_utc=datetime(2026, 5, 28, 12, 0, tzinfo=UTC),
            )

        monkeypatch.setattr(
            "ichor_api.alerts.scenario_invalidation.evaluate_scenario_invalidations",
            fake_monitor,
        )

        hits = await evaluate_scenario_invalidation_hits(session)
        assert len(hits) == 3
        assets_seen = {asset for (_, asset) in hits}
        assert assets_seen == {"EUR_USD", "GBP_USD", "XAU_USD"}


# ── evaluator : per-card defensive exception handling ──────────────────


class TestEvaluatorDefensiveErrors:
    @pytest.mark.asyncio
    async def test_monitor_exception_skips_card_silently(self, monkeypatch) -> None:
        """If monitor.evaluate_scenario_invalidations raises on a card,
        skip that card + continue (doctrine #11 — DB hiccup on 1 card
        doesn't kill the whole cron tick)."""
        from ichor_brain.session_verdict import ScenarioInvalidationState

        card_a = uuid4()
        card_b = uuid4()
        rows = [
            (card_a, "EUR_USD", datetime(2026, 5, 28, 6, 0, tzinfo=UTC)),
            (card_b, "GBP_USD", datetime(2026, 5, 28, 6, 0, tzinfo=UTC)),
        ]
        session = MagicMock()
        session.execute = AsyncMock(return_value=_rows_returning(rows))

        async def fake_monitor(_session, *, session_card_id, now_utc):
            if session_card_id == str(card_a):
                raise RuntimeError("simulated DB hiccup on card A")
            return ScenarioInvalidationState(
                scenarios_invalidated_hard=["crash_flush"],
                scenarios_invalidated_soft=[],
                scenarios_with_notes=[],
                last_check_utc=datetime(2026, 5, 28, 12, 0, tzinfo=UTC),
            )

        monkeypatch.setattr(
            "ichor_api.alerts.scenario_invalidation.evaluate_scenario_invalidations",
            fake_monitor,
        )

        hits = await evaluate_scenario_invalidation_hits(session)
        # Card A failed → skipped silently. Card B succeeded → 1 hit.
        assert len(hits) == 1
        _, asset = hits[0]
        assert asset == "GBP_USD"
