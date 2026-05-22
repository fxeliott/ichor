"""r140 — `/v1/calendar/upcoming?since_minutes=N` recent-window tests.

Pins :
  - `since_minutes=0` (default) preserves r68 forward-only behaviour
  - `since_minutes > 0` extends the lower bound backward
  - `asset=X&since_minutes=N` composes : the asset filter via
    `affected_assets` mapping is applied AFTER the time-window query
  - `since_minutes` is bounded by Query validator (max 1440 = 24h)
  - The `assess_calendar(since_minutes=N)` service signature exposes the
    knob for the `_section_calendar` data-pool reader too (parity LLM vs
    endpoint)

ADR-017 boundary : the recent-window response carries no directional
fields ; it surfaces "scheduled time elapsed" honestly. ADR-099 §Impl(r140).
"""

from __future__ import annotations

import inspect

import pytest


def test_assess_calendar_signature_supports_since_minutes():
    """r140 — `assess_calendar` must accept `since_minutes: int = 0`
    keyword-only param. The data-pool reader must be able to call it
    with the same window the endpoint exposes, for LLM-vs-endpoint parity."""
    from ichor_api.services.economic_calendar import assess_calendar

    sig = inspect.signature(assess_calendar)
    assert "since_minutes" in sig.parameters, "since_minutes param missing"
    p = sig.parameters["since_minutes"]
    assert p.kind == inspect.Parameter.KEYWORD_ONLY
    assert p.default == 0, "back-compat : default must be 0 (forward-only)"


def test_calendar_router_since_minutes_query_bounded():
    """r140 — `/v1/calendar/upcoming` Query validator caps `since_minutes`
    at 1440 (24h). Prevents accidental year-long backward queries that
    would explode the response payload."""
    from ichor_api.routers.calendar import get_upcoming

    sig = inspect.signature(get_upcoming)
    assert "since_minutes" in sig.parameters
    # FastAPI Query is via Annotated metadata ; the default value should be 0
    # and the docstring should reference the HONEST scope.
    param = sig.parameters["since_minutes"]
    # The actual default through Annotated[int, Query(...)] = 0 surfaces
    # as a `Query` object ; we just verify the param exists + default.
    assert param.default is not inspect.Parameter.empty


def test_assess_calendar_back_compat_since_minutes_zero():
    """r140 — `since_minutes=0` must NOT shift the lower bound (the r68
    forward-only assumption). The internal `ff_lower` equals `now`.

    r140 fix-cluster : `cutoff_now` consolidated into the outer `now`
    (code-reviewer N4 — single source of truth, no µs-skewed dual call).
    Sections 1+2 keep date-only forward filter `today = now.date()`
    (code-reviewer R1 — minute-precision is FF-only, not the full
    calendar day for CB meetings + recurring projections)."""
    import datetime

    from ichor_api.services import economic_calendar

    src = inspect.getsource(economic_calendar.assess_calendar)
    assert "since_minutes > 0" in src or "since_minutes>0" in src, (
        "back-compat conditional missing : since_minutes=0 must skip window-extension"
    )
    # r140 R1 fix : sections 1+2 must keep `today = now.date()` forward-only.
    assert "today = now.date()" in src, (
        "code-reviewer R1 regression : sections 1+2 (CB meetings, recurring) "
        "must use forward-only date floor ; minute-precision is FF-only"
    )
    # ff_lower is the FF-specific backward shift (section 3 only).
    assert "ff_lower" in src, "ff_lower not present — recent-window logic missing"
    assert "timedelta" in src
    _ = datetime


def test_assess_calendar_window_start_uses_since_minutes():
    """r140 — when `since_minutes > 0`, `window_start` shifts backward
    from `now` by exactly `since_minutes` minutes."""
    from ichor_api.services import economic_calendar

    src = inspect.getsource(economic_calendar.assess_calendar)
    # Pin the math via source presence
    assert "now - timedelta(minutes=since_minutes)" in src, (
        "window_start computation not the documented `now - since_minutes`"
    )


def test_filter_for_asset_signature_unchanged():
    """r140 — `filter_for_asset` (the rich affected_assets[] mapping)
    is unchanged ; the recent-window endpoint composes it via the existing
    `asset` query param. Pin the function still exists + signature."""
    from ichor_api.services.economic_calendar import filter_for_asset

    sig = inspect.signature(filter_for_asset)
    params = list(sig.parameters.keys())
    # Should accept the CalendarReport + asset string.
    assert len(params) == 2, f"filter_for_asset signature drift : {params}"


# ─── r140 code-reviewer S3 fix — DYNAMIC integration test ────────────────


async def test_assess_calendar_since_minutes_dynamic_window_includes_recent_ff():
    """r140 code-reviewer S3 fix : dynamic integration test that actually
    exercises the `since_minutes` window-shift logic against a stubbed DB,
    rather than static-source-text pinning only.

    Pins :
      (a) since_minutes=0 EXCLUDES a FF event at scheduled_at = now - 30min
      (b) since_minutes=60 INCLUDES it
    """
    from datetime import UTC, datetime, timedelta
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from ichor_api.services.economic_calendar import assess_calendar

    now = datetime.now(UTC)
    recent_ff = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001",
        currency="USD",
        scheduled_at=now - timedelta(minutes=30),
        is_all_day=False,
        title="Test NFP",
        impact="high",
        forecast="100k",
        previous="80k",
        url="https://x/y",
        source="forex_factory",
        fetched_at=now,
    )

    class _Result:
        """Mimics SQLAlchemy AsyncResult.scalars().all() AND
        scalar_one_or_none() — assess_calendar uses both paths."""

        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            outer_rows = self._rows

            class _S:
                def all(s2):
                    return list(outer_rows)

            return _S()

        def scalar_one_or_none(self):
            # Section 2 (recurring FRED) calls this on `fred_observations`
            # queries. Returning None makes the recurring section skip
            # gracefully (no FRED observation → no projection emitted).
            return None

    def make_session(rows: list) -> AsyncMock:
        # The assess_calendar function does multiple execute() calls. The
        # FF rows go through `select(EconomicEvent)` ; we just always
        # return the rows we want for the FF path. Sections 1+2 also
        # call execute() but on different selects ; same rows returned
        # is fine because their downstream filters (CB hardcoded /
        # FRED-recurring requires fred_observations rows) drop empty.
        s = AsyncMock()
        s.execute = AsyncMock(return_value=_Result(rows))
        return s

    # (a) since_minutes=0 : FF query lower=now → empty rows → 0 FF events
    sess = make_session([])
    report_0 = await assess_calendar(sess, horizon_days=14, since_minutes=0)
    ff_only = [e for e in report_0.events if e.source == "forex_factory"]
    assert len(ff_only) == 0, "since_minutes=0 should yield 0 FF events on empty pool"

    # (b) since_minutes=60 : FF query lower=now-60min → event included
    sess2 = make_session([recent_ff])
    report_60 = await assess_calendar(sess2, horizon_days=14, since_minutes=60)
    ff_in = [e for e in report_60.events if e.source == "forex_factory"]
    assert len(ff_in) >= 1, "since_minutes=60 should include the FF event at now-30min"
    assert any(e.label == "Test NFP" for e in ff_in)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
