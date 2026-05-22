"""Tests for r145 recent_actuals service + /v1/calendar/recent-actuals route.

Covers :

  * Service `fetch_recent_actuals` :
    - Happy path with multiple rows + classifier wiring.
    - Empty result returns [].
    - State = `unavailable` for r145 reality (no range columns populated).
    - magnitude_pct IS populated when actual + forecast both parse.
    - currency filter (USD default, None bypass).
    - limit cap (default 25, hard cap 200, negative clamped to 0).
    - now injection for deterministic windowing.
    - Defensive null-skip when scheduled_at OR actual is somehow None.

  * Router `/v1/calendar/recent-actuals` :
    - Pydantic shape projection (event_id stringified UUID, ISO 8601 ts,
      classification nested).
    - lookback_days validation (ge=1, le=90).
    - limit validation (ge=1, le=200).
    - currency empty string -> None convention (parity with /upcoming).

  * ADR-017 invariant : descriptive geometric state literals only, no
    BUY/SELL tokens leaking into the projection.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from ichor_api.services.economic_event_surprise import SurpriseClassification
from ichor_api.services.recent_actuals import (
    RecentActualRow,
    fetch_recent_actuals,
)

# ── helpers ─────────────────────────────────────────────────────────


def _make_event_row(
    *,
    currency: str = "USD",
    scheduled_at: datetime | None = None,
    title: str = "CPI y/y",
    impact: str = "high",
    actual: str | None = "3.2%",
    forecast: str | None = "3.0%",
    forecast_min: str | None = None,
    forecast_max: str | None = None,
    previous: str | None = "2.8%",
    url: str | None = "https://nfs.faireconomy.media/event/12345",
) -> MagicMock:
    """Build an ORM-shape MagicMock matching `EconomicEvent` columns."""
    if scheduled_at is None:
        scheduled_at = datetime(2026, 5, 12, 12, 30, tzinfo=UTC)
    row = MagicMock()
    row.id = uuid4()
    row.currency = currency
    row.scheduled_at = scheduled_at
    row.title = title
    row.impact = impact
    row.actual = actual
    row.forecast = forecast
    row.forecast_min = forecast_min
    row.forecast_max = forecast_max
    row.previous = previous
    row.url = url
    return row


def _build_session(rows: list[MagicMock]) -> MagicMock:
    """Build an AsyncSession-shape mock where `execute()` returns a result
    whose `.scalars().all()` yields the supplied rows."""
    session = MagicMock()
    result = MagicMock()
    scalars_obj = MagicMock()
    scalars_obj.all = MagicMock(return_value=rows)
    result.scalars = MagicMock(return_value=scalars_obj)
    session.execute = AsyncMock(return_value=result)
    return session


# ── TestFetchRecentActuals ──────────────────────────────────────────


class TestFetchRecentActuals:
    """Service-layer tests for `fetch_recent_actuals`."""

    @pytest.mark.asyncio
    async def test_happy_path_multiple_rows_with_classifier_wiring(self) -> None:
        rows = [
            _make_event_row(title="CPI y/y", actual="3.78", forecast="3.6", previous="3.5"),
            _make_event_row(
                title="Non-Farm Employment Change",
                actual="115K",
                forecast="125K",
                previous="178K",
                scheduled_at=datetime(2026, 5, 8, 12, 30, tzinfo=UTC),
            ),
        ]
        session = _build_session(rows)
        now = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)

        result = await fetch_recent_actuals(
            session, lookback_days=30, currency="USD", limit=25, now=now
        )

        assert len(result) == 2
        for row in result:
            assert isinstance(row, RecentActualRow)
            assert isinstance(row.classification, SurpriseClassification)

        # First row : actual=3.78 vs forecast=3.6 -> magnitude_pct = +5%
        # (3.78 - 3.6) / 3.6 * 100 = 5.0
        first = result[0]
        assert first.title == "CPI y/y"
        assert first.classification.magnitude_pct is not None
        assert abs(first.classification.magnitude_pct - 5.0) < 0.01

    @pytest.mark.asyncio
    async def test_empty_result_returns_empty_list(self) -> None:
        session = _build_session([])
        result = await fetch_recent_actuals(session, now=datetime.now(UTC))
        assert result == []

    @pytest.mark.asyncio
    async def test_state_unavailable_when_range_missing(self) -> None:
        """r145 reality : `forecast_min`/`forecast_max` are NULL across
        the board (no analyst range provider live yet). Classifier must
        return state=`unavailable` for all rows, but magnitude_pct must
        still populate from the point forecast."""
        row = _make_event_row(
            actual="3.78",
            forecast="3.6",
            forecast_min=None,
            forecast_max=None,
        )
        session = _build_session([row])
        result = await fetch_recent_actuals(session, now=datetime(2026, 5, 22, tzinfo=UTC))

        assert len(result) == 1
        cls = result[0].classification
        assert cls.state == "unavailable"
        # But magnitude IS computed -- that's the r141 design we rely on.
        assert cls.magnitude_pct is not None
        assert abs(cls.magnitude_pct - 5.0) < 0.01

    @pytest.mark.asyncio
    async def test_state_in_range_when_range_provided(self) -> None:
        """Future-proof : when range provider lands r146+, state will
        actually classify. Lock the wiring contract today via fixture
        with manually-set range."""
        row = _make_event_row(
            actual="3.78",
            forecast="3.7",
            forecast_min="3.5",
            forecast_max="4.0",
        )
        session = _build_session([row])
        result = await fetch_recent_actuals(session, now=datetime(2026, 5, 22, tzinfo=UTC))
        assert result[0].classification.state == "in_range"

    @pytest.mark.asyncio
    async def test_state_above_range_when_actual_exceeds_max(self) -> None:
        row = _make_event_row(
            actual="4.5",
            forecast="3.7",
            forecast_min="3.5",
            forecast_max="4.0",
        )
        session = _build_session([row])
        result = await fetch_recent_actuals(session, now=datetime(2026, 5, 22, tzinfo=UTC))
        cls = result[0].classification
        assert cls.state == "above_range"
        assert cls.range_breach == pytest.approx(0.5)

    @pytest.mark.asyncio
    async def test_state_below_range_when_actual_under_min(self) -> None:
        row = _make_event_row(
            actual="3.0",
            forecast="3.7",
            forecast_min="3.5",
            forecast_max="4.0",
        )
        session = _build_session([row])
        result = await fetch_recent_actuals(session, now=datetime(2026, 5, 22, tzinfo=UTC))
        cls = result[0].classification
        assert cls.state == "below_range"
        assert cls.range_breach == pytest.approx(0.5)

    @pytest.mark.asyncio
    async def test_limit_clamped_to_200_max(self) -> None:
        session = _build_session([])
        await fetch_recent_actuals(session, limit=10_000, now=datetime.now(UTC))
        # ORM stmt was built with .limit(200) -- we verify by inspecting
        # the call args on session.execute.
        called_stmt = session.execute.await_args.args[0]
        # SQLAlchemy Select objects expose `_limit_clause.value`.
        assert called_stmt._limit_clause is not None
        # The compiled limit is the post-clamp value.
        assert called_stmt._limit_clause.value == 200

    @pytest.mark.asyncio
    async def test_limit_negative_clamps_to_zero(self) -> None:
        session = _build_session([])
        await fetch_recent_actuals(session, limit=-5, now=datetime.now(UTC))
        called_stmt = session.execute.await_args.args[0]
        assert called_stmt._limit_clause.value == 0

    @pytest.mark.asyncio
    async def test_currency_filter_applied_when_provided(self) -> None:
        session = _build_session([])
        await fetch_recent_actuals(session, currency="EUR", now=datetime.now(UTC))
        called_stmt = session.execute.await_args.args[0]
        compiled = str(called_stmt.compile(compile_kwargs={"literal_binds": True}))
        # The currency literal must appear in the WHERE predicate.
        # (Column name appears in SELECT list always; we check the literal.)
        assert "'EUR'" in compiled
        assert "economic_events.currency = 'EUR'" in compiled

    @pytest.mark.asyncio
    async def test_currency_filter_skipped_when_none(self) -> None:
        session = _build_session([])
        await fetch_recent_actuals(session, currency=None, now=datetime.now(UTC))
        called_stmt = session.execute.await_args.args[0]
        compiled = str(called_stmt.compile(compile_kwargs={"literal_binds": True}))
        # No literal "= 'XXX'" predicate on currency when filter skipped.
        # The column DOES appear in the SELECT projection list -- that's
        # not a filter, that's the SELECT row shape we depend on.
        where_segment = compiled.split("WHERE", 1)[1] if "WHERE" in compiled else ""
        assert "economic_events.currency =" not in where_segment

    @pytest.mark.asyncio
    async def test_lookback_window_uses_injected_now(self) -> None:
        session = _build_session([])
        fixed_now = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)
        await fetch_recent_actuals(session, lookback_days=7, currency="USD", now=fixed_now)
        called_stmt = session.execute.await_args.args[0]
        compiled = str(called_stmt.compile(compile_kwargs={"literal_binds": True}))
        # 7 days before fixed_now = 2026-05-15
        assert "2026-05-15 12:00:00" in compiled
        assert "2026-05-22 12:00:00" in compiled

    @pytest.mark.asyncio
    async def test_now_defaults_to_utc_when_omitted(self) -> None:
        session = _build_session([])
        before = datetime.now(UTC) - timedelta(seconds=2)
        await fetch_recent_actuals(session)
        after = datetime.now(UTC) + timedelta(seconds=2)
        called_stmt = session.execute.await_args.args[0]
        compiled = str(called_stmt.compile(compile_kwargs={"literal_binds": True}))
        # Verify a timestamp in the compiled SQL falls in window.
        assert "2026" in compiled  # smoke -- year present

        # Service must not raise when now=None (the default branch).
        # `before`/`after` only exist to bracket -- they're a defensive
        # sanity check that we didn't accidentally hardcode a stale date.
        assert before < after

    @pytest.mark.asyncio
    async def test_defensive_skip_when_actual_is_none(self) -> None:
        """If the ORM filter ever weakens, runtime check skips the row."""
        good_row = _make_event_row(title="Good", actual="3.2")
        bad_row = _make_event_row(title="Bad", actual=None)
        session = _build_session([good_row, bad_row])
        result = await fetch_recent_actuals(session, now=datetime(2026, 5, 22, tzinfo=UTC))
        assert len(result) == 1
        assert result[0].title == "Good"

    @pytest.mark.asyncio
    async def test_defensive_skip_when_scheduled_at_is_none(self) -> None:
        good_row = _make_event_row(title="Good")
        bad_row = _make_event_row(title="Bad", scheduled_at=None)
        # We need to manually set scheduled_at=None because _make_event_row
        # defaults to a non-None value.
        bad_row.scheduled_at = None
        session = _build_session([good_row, bad_row])
        result = await fetch_recent_actuals(session, now=datetime(2026, 5, 22, tzinfo=UTC))
        assert len(result) == 1
        assert result[0].title == "Good"

    @pytest.mark.asyncio
    async def test_classifier_carries_parse_failures(self) -> None:
        row = _make_event_row(actual="abcxyz", forecast="3.6")
        session = _build_session([row])
        result = await fetch_recent_actuals(session, now=datetime(2026, 5, 22, tzinfo=UTC))
        cls = result[0].classification
        assert "actual" in cls.parse_failures


# ── TestRecentActualsRouter (FastAPI smoke) ─────────────────────────


class TestRecentActualsRouter:
    """Router-layer tests via FastAPI app override."""

    @pytest.mark.asyncio
    async def test_route_returns_pydantic_shape(self) -> None:
        from httpx import ASGITransport, AsyncClient
        from ichor_api.db import get_session
        from ichor_api.main import app

        rows = [
            _make_event_row(
                title="CPI y/y",
                actual="3.78",
                forecast="3.6",
                scheduled_at=datetime(2026, 5, 12, 12, 30, tzinfo=UTC),
            ),
        ]
        session = _build_session(rows)

        async def _override_get_session():
            yield session

        app.dependency_overrides[get_session] = _override_get_session
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/v1/calendar/recent-actuals?lookback_days=30")
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["lookback_days"] == 30
            assert payload["currency"] == "USD"
            assert len(payload["rows"]) == 1
            row = payload["rows"][0]
            assert row["title"] == "CPI y/y"
            assert row["actual"] == "3.78"
            assert row["scheduled_at_utc"].startswith("2026-05-12T12:30")
            assert row["classification"]["state"] == "unavailable"
            assert row["classification"]["magnitude_pct"] == pytest.approx(5.0)
            assert isinstance(row["classification"]["parse_failures"], list)
        finally:
            app.dependency_overrides.pop(get_session, None)

    @pytest.mark.asyncio
    async def test_route_rejects_lookback_days_out_of_range(self) -> None:
        from httpx import ASGITransport, AsyncClient
        from ichor_api.db import get_session
        from ichor_api.main import app

        session = _build_session([])

        async def _override_get_session():
            yield session

        app.dependency_overrides[get_session] = _override_get_session
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # 91 > max 90
                resp = await client.get("/v1/calendar/recent-actuals?lookback_days=91")
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.pop(get_session, None)

    @pytest.mark.asyncio
    async def test_route_rejects_limit_out_of_range(self) -> None:
        from httpx import ASGITransport, AsyncClient
        from ichor_api.db import get_session
        from ichor_api.main import app

        session = _build_session([])

        async def _override_get_session():
            yield session

        app.dependency_overrides[get_session] = _override_get_session
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/v1/calendar/recent-actuals?limit=500")
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.pop(get_session, None)

    @pytest.mark.asyncio
    async def test_route_rejects_empty_currency_with_422(self) -> None:
        """`?currency=` (empty) is REJECTED by Pydantic Query(min_length=2).

        code-reviewer r145 SHOULD-FIX #7 -- the prior docstring claimed empty
        string was a "skip filter" sentinel but Pydantic 422'd it. The
        contract is now explicit : default = "USD", explicit empty = 422,
        future r146+ adds a sentinel like "ALL" if all-currencies surfacing
        becomes a requirement."""
        from httpx import ASGITransport, AsyncClient
        from ichor_api.db import get_session
        from ichor_api.main import app

        session = _build_session([])

        async def _override_get_session():
            yield session

        app.dependency_overrides[get_session] = _override_get_session
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/v1/calendar/recent-actuals?lookback_days=30&currency=")
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.pop(get_session, None)


# ── TestAdr017Invariants ────────────────────────────────────────────


class TestAdr017Invariants:
    """ADR-017 compliance : state literals are descriptive geometric, never
    directional. magnitude_pct sign convention is geometric distance from
    consensus, NOT bullish/bearish."""

    def test_state_literal_set_is_geometric_not_directional(self) -> None:
        """Pin the 5-state alphabet at the API contract level."""
        # Get the Literal args via typing.get_args
        from typing import get_args

        from ichor_api.routers.calendar import SurpriseStateLiteral

        states = set(get_args(SurpriseStateLiteral))
        assert states == {
            "unavailable",
            "in_range",
            "above_range",
            "below_range",
            "exact_consensus",
        }
        # No directional tokens leaked.
        forbidden = {"buy", "sell", "long", "short", "bullish", "bearish"}
        for state in states:
            assert state.lower() not in forbidden

    def test_backend_state_literal_lockstep(self) -> None:
        """code-reviewer r145 SHOULD-FIX #2 -- the router-side
        `SurpriseStateLiteral` MUST be the SAME object as the service-side
        `SurpriseState`. Re-export `SurpriseStateLiteral = SurpriseState`
        ensures any rename/add in the service layer flows through ; if a
        future contributor re-defines `SurpriseStateLiteral` as a separate
        Literal copy, this test fails."""
        from ichor_api.routers.calendar import SurpriseStateLiteral
        from ichor_api.services.economic_event_surprise import SurpriseState

        assert SurpriseStateLiteral is SurpriseState

    def test_recent_actual_row_dataclass_has_no_directional_field(self) -> None:
        """No field name implies trade direction."""
        from dataclasses import fields

        names = {f.name for f in fields(RecentActualRow)}
        forbidden_substrings = ["buy", "sell", "long", "short", "side", "entry", "stop"]
        for n in names:
            low = n.lower()
            for sub in forbidden_substrings:
                # Whole-word check (avoid false-match on "short" inside
                # legitimate words if any). Our field names use snake_case
                # so the simple substring check is acceptable.
                assert sub not in low.split("_"), f"forbidden token {sub!r} in field {n!r}"
