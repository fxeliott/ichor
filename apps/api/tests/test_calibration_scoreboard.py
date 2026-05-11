"""HTTP integration tests for `GET /v1/calibration/scoreboard` (W101).

This is the new endpoint introduced in W101 (cf ADR-082/083). It exposes
a multi-window matrix of (asset × session_type) calibration cells for
the trader-grade Living Analysis View frontend.

Coverage :
  - Smoke : endpoint exists, responds 200 or 503 (DB stub mode).
  - OpenAPI schema includes the new route.
  - Default windows = ["30d", "90d", "all"] (3-window default).
  - Window parsing : valid formats accepted, invalid → 400.
  - Window cap : `731d` rejected (must be 1..730).
  - All-invalid request → 400 with explicit detail message.
  - Single-window query works (e.g. windows=14d alone).
  - Session-type regex now accepts all 5 SessionType values from
    `ichor_brain.types.VALID_SESSION_TYPES` (was a bug pre-W101 — the
    overall route rejected `ny_mid` / `ny_close` even though the type
    contract allows them).

These tests use the same ASGITransport + AsyncClient pattern as
`test_routers_smoke.py`. The DB is stubbed via the conftest autouse
fixture, so any query path returns HTTPException(503). Routes that
respond before touching the DB (e.g. param-validation 400s, OpenAPI
schema) still return 200/400 as expected.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from ichor_api.main import app


@pytest.fixture
def transport() -> ASGITransport:
    return ASGITransport(app=app)


# ──────────────────────────── Smoke ─────────────────────────────────────


@pytest.mark.asyncio
async def test_scoreboard_smoke_default(transport: ASGITransport) -> None:
    """Smoke : endpoint exists and responds without crash.

    Either 200 (real DB, possibly empty result) or 503 (stub DB raises
    HTTPException(503) on `session.execute`). Both prove the route is
    correctly registered and the param-default path runs."""
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/v1/calibration/scoreboard")
    assert resp.status_code in (200, 503), (
        f"unexpected status {resp.status_code}: {resp.text[:200]}"
    )


@pytest.mark.asyncio
async def test_scoreboard_in_openapi_schema(transport: ASGITransport) -> None:
    """OpenAPI must list the new route so schemathesis/CI can pick it
    up (S4 contract gate). Drift guard against a future refactor that
    accidentally drops the route from the FastAPI app."""
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    assert "/v1/calibration/scoreboard" in paths
    # GET is the only verb expected.
    assert "get" in paths["/v1/calibration/scoreboard"]


# ──────────────────────────── Window parsing ────────────────────────────


@pytest.mark.asyncio
async def test_scoreboard_explicit_single_window(transport: ASGITransport) -> None:
    """A single explicit window works (e.g. `?windows=14d`). Tests that
    `Query(default=[...])` doesn't force the default when user supplies
    one value."""
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/v1/calibration/scoreboard", params={"windows": "14d"})
    assert resp.status_code in (200, 503)


@pytest.mark.asyncio
async def test_scoreboard_all_invalid_windows_returns_400(transport: ASGITransport) -> None:
    """All-invalid windows → 400 with detail message. This is the only
    path that responds 400 (param validation done before any DB hit),
    so we can assert on 400 strictly here even with stub DB."""
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get(
            "/v1/calibration/scoreboard",
            params=[("windows", "garbage"), ("windows", "nope"), ("windows", "")],
        )
    assert resp.status_code == 400
    detail = resp.json().get("detail", "")
    assert "no valid windows" in detail
    # The detail should echo the bad inputs so the caller can debug.
    assert "garbage" in detail


@pytest.mark.asyncio
async def test_scoreboard_window_above_cap_filtered_out(transport: ASGITransport) -> None:
    """`731d` is above the 730-day cap. If it's the only window, the
    request fails 400 (no valid windows). This pins the cap behaviour
    so a future relax doesn't silently regress."""
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/v1/calibration/scoreboard", params={"windows": "731d"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_scoreboard_window_zero_days_filtered_out(transport: ASGITransport) -> None:
    """`0d` is below the 1-day minimum. Same treatment as cap."""
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/v1/calibration/scoreboard", params={"windows": "0d"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_scoreboard_mixed_valid_and_invalid_windows(transport: ASGITransport) -> None:
    """If at least ONE window is valid, the request proceeds. Invalid
    windows are silently dropped (lenient parsing). This avoids
    surfacing 400 to UIs that pass extra/legacy window labels."""
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get(
            "/v1/calibration/scoreboard",
            params=[("windows", "garbage"), ("windows", "30d"), ("windows", "trash")],
        )
    # Not 400 — at least one window parsed. Either 200 or 503 from DB.
    assert resp.status_code in (200, 503)


@pytest.mark.asyncio
async def test_scoreboard_all_alias_accepted(transport: ASGITransport) -> None:
    """`all` is a special label that maps to the 730-day cap. The
    route must accept it even without numeric suffix."""
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/v1/calibration/scoreboard", params={"windows": "all"})
    assert resp.status_code in (200, 503)


# ──────────────────────────── Session-type regex bug fix ────────────────


@pytest.mark.asyncio
async def test_overall_route_accepts_ny_mid_session_type(transport: ASGITransport) -> None:
    """W101 fix : the overall `/v1/calibration` route used to reject
    `session_type=ny_mid` with 422 (regex was hardcoded to 3 windows).
    Now it must accept all 5 SessionType values from
    `ichor_brain.types.VALID_SESSION_TYPES`. This test pins the fix.
    """
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/v1/calibration", params={"session_type": "ny_mid"})
    # Either 200 (real DB) or 503 (stub) — but NOT 422 (regex reject).
    assert resp.status_code != 422, (
        f"session_type=ny_mid still rejected by regex : {resp.text[:200]}"
    )
    assert resp.status_code in (200, 503)


@pytest.mark.asyncio
async def test_overall_route_accepts_ny_close_session_type(transport: ASGITransport) -> None:
    """Same as above for `ny_close`."""
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/v1/calibration", params={"session_type": "ny_close"})
    assert resp.status_code != 422
    assert resp.status_code in (200, 503)


@pytest.mark.asyncio
async def test_overall_route_rejects_unknown_session_type(transport: ASGITransport) -> None:
    """The regex still works as a allowlist : unknown values rejected
    with 422 (FastAPI param validation)."""
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get(
            "/v1/calibration",
            params={"session_type": "asia_open_definitely_not_a_real_session"},
        )
    assert resp.status_code == 422


# ──────────────────────────── Unit : _parse_window ──────────────────────


def test_parse_window_helper_accepts_valid_formats() -> None:
    """Direct unit test on the `_parse_window` helper. Faster than
    HTTP smoke for the parse layer ; pins all the accepted forms."""
    from ichor_api.routers.calibration import _parse_window

    assert _parse_window("30d") == 30
    assert _parse_window("1d") == 1
    assert _parse_window("730d") == 730
    assert _parse_window("all") == 730


def test_parse_window_helper_rejects_invalid_formats() -> None:
    from ichor_api.routers.calibration import _parse_window

    assert _parse_window("") is None
    assert _parse_window("30") is None  # no suffix
    assert _parse_window("0d") is None  # below min
    assert _parse_window("731d") is None  # above max
    assert _parse_window("30days") is None  # wrong suffix
    assert _parse_window("everything") is None  # not "all"
    assert _parse_window("-5d") is None  # negative
    assert _parse_window("3.5d") is None  # fractional not supported
