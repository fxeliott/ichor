"""r152 tests for event_anticipation_view service + /v1/event-anticipation/{asset} router.

Covers atom-level :
- 3 modes : engaged / standby / silent
- Engaged path : Engine 8 returns non-None → projection to wire shape preserved
- Standby path : Engine 8 None + economic_events forward 14d has rows
- Silent path : Engine 8 None + no rows in window
- Parse_failures projection (r150 single_source_direction sentinel + r147 event_class_unmapped)
- ADR-017 boundary (no BUY/SELL in caveat / event_class strings)
- r152 PCE/GDP class extension wired correctly
- Router URL pattern matching (asset shape constraint)
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from ichor_api.services.event_anticipation_view import (
    assess_event_anticipation_view,
)
from ichor_api.services.event_proximity_engine import (
    EVENT_CLASS_BASELINE_BP,
    EventProximityFactor,
    _map_title_to_event_class,
)

# ── helpers ─────────────────────────────────────────────────────────


def _make_econ_event_row(
    *,
    event_id: str | None = None,
    title: str = "Federal Funds Rate",
    impact: str = "high",
    currency: str = "USD",
    scheduled_at: datetime | None = None,
) -> MagicMock:
    """Build an `EconomicEvent`-shaped MagicMock for the STANDBY path."""
    if scheduled_at is None:
        scheduled_at = datetime(2026, 6, 3, 14, 30, tzinfo=UTC)
    row = MagicMock()
    row.id = event_id or str(uuid4())
    row.title = title
    row.impact = impact
    row.currency = currency
    row.scheduled_at = scheduled_at
    return row


def _build_event_rows_session(rows: list[MagicMock]) -> MagicMock:
    """Build AsyncSession mock returning the given event rows for STANDBY query."""
    session = MagicMock()
    events_result = MagicMock()
    events_scalars = MagicMock()
    events_scalars.all = MagicMock(return_value=rows)
    events_result.scalars = MagicMock(return_value=events_scalars)
    session.execute = AsyncMock(side_effect=[events_result])
    return session


# ── r152 PCE/GDP class extension ─────────────────────────────────────


class TestR152PceGdpClassMapping:
    """r152 NEW : PCE / GDP first-class event classes (CPI-class magnitude for
    PCE = 20bp, GDP intermediate at 25bp). Empirically captures the Tue May 26
    Core PCE + Thu May 28 Prelim GDP US events that were previously falling
    through to `high_other` 10bp baseline.
    """

    def test_core_pce_maps_PCE(self) -> None:
        """FOMC's preferred core inflation gauge."""
        assert _map_title_to_event_class("Core PCE Price Index m/m") == "PCE"
        assert _map_title_to_event_class("Core PCE Price Index y/y") == "PCE"

    def test_pce_price_index_maps_PCE(self) -> None:
        """Non-Core PCE variant."""
        assert _map_title_to_event_class("PCE Price Index m/m") == "PCE"

    def test_prelim_gdp_maps_GDP(self) -> None:
        """US Prelim GDP q/q (one of 3 US GDP releases per quarter)."""
        assert _map_title_to_event_class("Prelim GDP q/q") == "GDP"

    def test_advance_gdp_maps_GDP(self) -> None:
        """US Advance GDP q/q."""
        assert _map_title_to_event_class("Advance GDP q/q") == "GDP"

    def test_final_gdp_maps_GDP(self) -> None:
        """US Final GDP q/q."""
        assert _map_title_to_event_class("Final GDP q/q") == "GDP"

    def test_bare_gdp_maps_GDP(self) -> None:
        """EZ / JP / UK / AU GDP variants without prefix."""
        assert _map_title_to_event_class("GDP q/q") == "GDP"

    def test_pce_baseline_present(self) -> None:
        """Engine 8 baseline_bp registry must have PCE."""
        assert "PCE" in EVENT_CLASS_BASELINE_BP
        assert EVENT_CLASS_BASELINE_BP["PCE"] == 20.0  # CPI-class magnitude

    def test_gdp_baseline_present(self) -> None:
        """Engine 8 baseline_bp registry must have GDP."""
        assert "GDP" in EVENT_CLASS_BASELINE_BP
        assert EVENT_CLASS_BASELINE_BP["GDP"] == 25.0  # intermediate FOMC/CPI

    def test_pce_before_cpi_priority(self) -> None:
        """REGRESSION : PCE-specific patterns MUST be ordered BEFORE generic
        CPI patterns. A title like 'Core PCE Price Index m/m' contains no
        'cpi' substring so order doesn't matter for THIS title — but the test
        documents the convention (PCE family declared before CPI family in
        `_TITLE_TO_EVENT_CLASS` tuple)."""
        from ichor_api.services.event_proximity_engine import _TITLE_TO_EVENT_CLASS

        # Find first PCE entry + first CPI-only entry positions in tuple.
        pce_idx = next(i for i, (frag, cls) in enumerate(_TITLE_TO_EVENT_CLASS) if cls == "PCE")
        # The first "CPI" class entry (some r149 variants use Core CPI etc.)
        cpi_idx = next(i for i, (frag, cls) in enumerate(_TITLE_TO_EVENT_CLASS) if cls == "CPI")
        # PCE patterns are positioned EARLIER than ANY CPI pattern.
        # (Both share zero substring overlap, so this is structural discipline
        # documenting first-match-wins convention, not a functional necessity.)
        assert pce_idx < cpi_idx


# ── event_anticipation_view service ──────────────────────────────────


class TestR152EventAnticipationViewModes:
    """3-mode dispatch : ENGAGED (Engine 8 fires) / STANDBY (Engine 8 silent
    but events upcoming) / SILENT (nothing in 14d window). Pure-fn behavior
    verified via AsyncMock — no DB hit.
    """

    @pytest.mark.asyncio
    async def test_engaged_mode_when_engine_returns_factor(self, monkeypatch) -> None:
        """Engine 8 returns non-None → mode='engaged', engaged populated,
        standby_events empty, parse_failures projected from factor."""
        engaged_factor = EventProximityFactor(
            next_event_id="abc-123",
            next_event_title="Core PCE Price Index m/m",
            next_event_currency="USD",
            next_event_minutes_until=2700,  # ~45h
            next_event_impact="high",
            next_event_class="PCE",
            expected_drift_direction="up",
            expected_drift_magnitude_bp=15.0,
            confidence="high",
            vix_regime_gate="p50_to_p75",
            caveat="Magnitude prior littérature, pas calibrée sur historique Ichor",
            literature_anchor="Lucca-Moench 2015 + Kurov 2021",
            parse_failures=frozenset({"r152_test_sentinel"}),
        )

        async def fake_assess(*_args, **_kwargs):
            return engaged_factor

        monkeypatch.setattr(
            "ichor_api.services.event_anticipation_view.assess_event_proximity",
            fake_assess,
        )

        session = MagicMock()
        view = await assess_event_anticipation_view(
            session,
            asset="EUR_USD",
            now=datetime(2026, 5, 24, 12, 0, tzinfo=UTC),
        )
        assert view.mode == "engaged"
        assert view.engaged is engaged_factor
        assert view.standby_events == ()
        assert "r152_test_sentinel" in view.parse_failures
        assert view.asset == "EUR_USD"

    @pytest.mark.asyncio
    async def test_standby_mode_when_engine_silent_but_events_upcoming(self, monkeypatch) -> None:
        """Engine 8 None + economic_events has upcoming rows → mode='standby',
        engaged None, standby_events populated with mapped event_class."""

        async def fake_assess(*_args, **_kwargs):
            return None

        monkeypatch.setattr(
            "ichor_api.services.event_anticipation_view.assess_event_proximity",
            fake_assess,
        )

        # 2 upcoming events : Core PCE Tue + ECB Wed
        rows = [
            _make_econ_event_row(
                title="Core PCE Price Index m/m",
                impact="high",
                currency="USD",
                scheduled_at=datetime(2026, 5, 26, 12, 30, tzinfo=UTC),
            ),
            _make_econ_event_row(
                title="ECB Financial Stability Review",
                impact="medium",
                currency="EUR",
                scheduled_at=datetime(2026, 5, 27, 8, 0, tzinfo=UTC),
            ),
        ]
        session = _build_event_rows_session(rows)

        view = await assess_event_anticipation_view(
            session,
            asset="EUR_USD",
            now=datetime(2026, 5, 24, 12, 0, tzinfo=UTC),
        )
        assert view.mode == "standby"
        assert view.engaged is None
        assert len(view.standby_events) == 2
        # First entry = US Core PCE → PCE class (r152 new)
        assert view.standby_events[0].event_class == "PCE"
        assert view.standby_events[0].currency == "USD"
        assert view.standby_events[0].minutes_until > 0
        # Second entry = ECB → not mapped to any class (ECB family expects
        # "ecb monetary policy statement" / "ecb press conference" etc., not
        # "Financial Stability Review")
        assert view.standby_events[1].currency == "EUR"

    @pytest.mark.asyncio
    async def test_silent_mode_when_engine_none_and_no_upcoming(self, monkeypatch) -> None:
        """Engine 8 None + no rows in window → mode='silent', engaged None,
        standby_events empty. Honest empty state."""

        async def fake_assess(*_args, **_kwargs):
            return None

        monkeypatch.setattr(
            "ichor_api.services.event_anticipation_view.assess_event_proximity",
            fake_assess,
        )

        session = _build_event_rows_session([])

        view = await assess_event_anticipation_view(
            session,
            asset="XAU_USD",  # USD-only currency exposure
            now=datetime(2026, 8, 15, 12, 0, tzinfo=UTC),  # summer lull
        )
        assert view.mode == "silent"
        assert view.engaged is None
        assert view.standby_events == ()
        assert view.parse_failures == frozenset()


class TestR152StandbyEventViewProjection:
    """STANDBY mode honest mapping : `_map_title_to_event_class()` projects
    each row's title to event_class (None if unmapped). UI renders fallback
    "Catalyseur non-classé" when class is None per r149 honest scope."""

    @pytest.mark.asyncio
    async def test_unmapped_title_event_class_is_None(self, monkeypatch) -> None:
        async def fake_assess(*_args, **_kwargs):
            return None

        monkeypatch.setattr(
            "ichor_api.services.event_anticipation_view.assess_event_proximity",
            fake_assess,
        )

        rows = [
            _make_econ_event_row(
                title="Construction Spending m/m",  # not in mapping
                impact="medium",
                currency="USD",
                scheduled_at=datetime(2026, 5, 26, 14, 0, tzinfo=UTC),
            )
        ]
        session = _build_event_rows_session(rows)
        view = await assess_event_anticipation_view(
            session,
            asset="EUR_USD",
            now=datetime(2026, 5, 24, 12, 0, tzinfo=UTC),
        )
        assert view.standby_events[0].event_class is None


# ── r152 Phase 2 code-reviewer SF-1 — router wire-shape tests ──────


class TestR152RouterAssetPattern:
    """r152 Phase 2 code-reviewer CRIT-1 closure — the path regex MUST
    accept all 6 priority assets including index codes (NAS100_USD /
    SPX500_USD) which carry digits in the prefix. The original
    `^[A-Z]{3,8}_[A-Z]{3,8}$|^[A-Z]{3,8}$` pattern silently rejected
    them at the path layer → HTTP 422 → frontend `apiGet` returned null
    → Mission centrale axis-4 broken on 25% of priority universe.

    These tests pin the regex at the wire boundary. Empirical TestClient
    invocations (NOT just service-layer mocks) — closes the meta-gap that
    let CRIT-1 slip past Phase 1.
    """

    def test_priority_assets_accepted_by_path_pattern(self) -> None:
        """All 6 briefing priority assets MUST pass the regex.

        Uses a stripped FastAPI app with only the router mounted, so the
        DB dependency is harmless (we override `get_session` with a
        no-op AsyncMock that yields empty STANDBY + None Engine 8 →
        SILENT mode → 200 OK).
        """
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from ichor_api.db import get_session
        from ichor_api.routers.event_anticipation import router as event_router

        priority_assets = [
            "EUR_USD",
            "GBP_USD",
            "USD_CAD",
            "XAU_USD",
            "NAS100_USD",  # ← was 422 pre-fix
            "SPX500_USD",  # ← was 422 pre-fix
        ]
        app = FastAPI()
        app.include_router(event_router)

        async def fake_session():
            # Yield a session-shaped MagicMock that returns no events.
            session = MagicMock()
            events_result = MagicMock()
            events_scalars = MagicMock()
            events_scalars.all = MagicMock(return_value=[])
            events_result.scalars = MagicMock(return_value=events_scalars)
            session.execute = AsyncMock(return_value=events_result)
            yield session

        app.dependency_overrides[get_session] = fake_session

        # ALSO patch assess_event_proximity to return None (SILENT path)
        # so we don't hit FRED/DB for VIX/event lookups.
        import ichor_api.services.event_anticipation_view as view_mod

        async def fake_assess(*_args, **_kwargs):
            return None

        original_assess = view_mod.assess_event_proximity
        view_mod.assess_event_proximity = fake_assess
        try:
            client = TestClient(app)
            for asset in priority_assets:
                resp = client.get(f"/v1/event-anticipation/{asset}")
                assert resp.status_code == 200, (
                    f"asset={asset} got {resp.status_code} — CRIT-1 regression"
                )
                body = resp.json()
                # SILENT mode wire shape :
                assert body["asset"] == asset
                assert body["mode"] == "silent"
                assert body["engaged"] is None
                assert body["standby_events"] == []
                assert body["parse_failures"] == []
        finally:
            view_mod.assess_event_proximity = original_assess
            app.dependency_overrides.clear()

    def test_path_pattern_rejects_lowercase_and_special_chars(self) -> None:
        """The regex MUST still reject genuinely malformed asset codes.

        Belt-and-suspenders : code-reviewer CRIT-1 fix widens the prefix
        to `[A-Z0-9]` but the suffix MUST stay alpha-only (currency
        codes), and lowercase / hyphens / spaces / unicode confusables
        MUST 422.
        """
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from ichor_api.routers.event_anticipation import router as event_router

        app = FastAPI()
        app.include_router(event_router)
        client = TestClient(app)

        bad_paths = [
            "/v1/event-anticipation/eur_usd",  # lowercase
            "/v1/event-anticipation/EUR-USD",  # hyphen
            "/v1/event-anticipation/EUR USD",  # space (becomes %20)
            "/v1/event-anticipation/EUR_usd",  # mixed case
            "/v1/event-anticipation/AB",  # too short
        ]
        for path in bad_paths:
            resp = client.get(path)
            # Either 422 (path regex fail) or 404 (path didn't match
            # router at all). Both are honest rejections.
            assert resp.status_code in (404, 422), (
                f"path={path} got {resp.status_code} — should reject"
            )


# ── r152 Phase 2 code-reviewer SF-4 — field-set lockstep invariants ─


class TestR152WireFieldSetLockstep:
    """r152 Phase 2 code-reviewer SF-4 — pin the field set of the
    Pydantic wire models against the engine + view dataclasses, so a
    future field added on either side drops a CI signal instead of
    silently disappearing in the JSON projection.

    Mirrors the r142 docstring-strip + r143 pocketSkill SSOT lockstep
    pattern (source-inspection CI invariants).
    """

    def test_event_proximity_factor_out_mirrors_dataclass_fields(self) -> None:
        from dataclasses import fields

        from ichor_api.routers.event_anticipation import EventProximityFactorOut
        from ichor_api.services.event_proximity_engine import (
            EventProximityFactor,
        )

        dataclass_fields = {f.name for f in fields(EventProximityFactor)}
        wire_fields = set(EventProximityFactorOut.model_fields.keys())
        # The wire model MUST mirror the dataclass verbatim. Drift in
        # either direction = silent JSON contract change.
        assert dataclass_fields == wire_fields, (
            f"EventProximityFactor ⇄ EventProximityFactorOut drift : "
            f"dataclass-only={dataclass_fields - wire_fields}, "
            f"wire-only={wire_fields - dataclass_fields}"
        )

    def test_upcoming_event_out_mirrors_view_fields(self) -> None:
        from dataclasses import fields

        from ichor_api.routers.event_anticipation import UpcomingEventOut
        from ichor_api.services.event_anticipation_view import (
            UpcomingEventView,
        )

        view_fields = {f.name for f in fields(UpcomingEventView)}
        wire_fields = set(UpcomingEventOut.model_fields.keys())
        assert view_fields == wire_fields, (
            f"UpcomingEventView ⇄ UpcomingEventOut drift : "
            f"view-only={view_fields - wire_fields}, "
            f"wire-only={wire_fields - view_fields}"
        )


# ── r152 Phase 2 code-reviewer SF-2 — STANDBY cap two-sided lockstep ─


class TestR152StandbyMaxLockstep:
    """r152 Phase 2 code-reviewer SF-2 — the backend cap
    `_STANDBY_MAX_EVENTS=3` and the frontend cap `STANDBY_MAX_VISIBLE=3`
    are conceptually paired but live in two separate trees. The
    frontend vitest pins `STANDBY_MAX_VISIBLE === 3` against a hardcoded
    expectation ; this backend test pins the OTHER side against the
    same literal so a change on EITHER tree fails CI.
    """

    def test_backend_standby_max_events_is_3(self) -> None:
        from ichor_api.services.event_anticipation_view import (
            _STANDBY_MAX_EVENTS,
        )

        # Frontend `apps/web2/lib/eventAnticipation.ts:STANDBY_MAX_VISIBLE`
        # MUST track this literal. If you change one, change the other +
        # update both the backend (this) and frontend (vitest) tests.
        assert _STANDBY_MAX_EVENTS == 3
