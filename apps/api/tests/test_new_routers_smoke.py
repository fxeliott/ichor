"""Smoke tests for routers added in this audit pass.

Phase 2 audit (2026-05-05) shipped 3 new routes :
  - GET /v1/yield-curve              (Wave 1.4)
  - GET /v1/sources                  (Wave 1.5)
  - GET /v1/macro-pulse/heatmap      (Wave 4.5)

And re-wired :
  - GET /v1/divergences              (Wave 1.1, was already in test_routers_smoke)
  - GET /v1/sessions/{asset}/scenarios (Wave 4.3 frontend wiring)

These tests assert each route is registered (in the OpenAPI schema) and
responds with a structured payload (200) or DB-not-ready (503) when
hit against an empty DB. No 500s allowed.

Pattern follows `test_routers_smoke.py`.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from ichor_api.main import app


@pytest.fixture
def transport() -> ASGITransport:
    return ASGITransport(app=app)


@pytest.mark.asyncio
async def test_openapi_schema_includes_new_routes(transport: ASGITransport) -> None:
    """The 3 new routes must appear in /openapi.json (schemathesis-ready)."""
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json().get("paths", {})
    assert "/v1/yield-curve" in paths
    assert "/v1/sources" in paths
    assert "/v1/macro-pulse/heatmap" in paths
    assert "/v1/sessions/{asset}/scenarios" in paths


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path,expected",
    [
        ("/v1/yield-curve", (200, 503)),
        ("/v1/sources", (200, 503)),
        ("/v1/macro-pulse/heatmap", (200, 503)),
    ],
)
async def test_new_routers_respond_structured(
    transport: ASGITransport, path: str, expected: tuple[int, ...]
) -> None:
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get(path)
    assert resp.status_code in expected, (
        f"{path} returned {resp.status_code} (expected {expected}): body={resp.text[:200]}"
    )


@pytest.mark.asyncio
async def test_yield_curve_returns_typed_shape(transport: ASGITransport) -> None:
    """When 200, the body must include the typed top-level keys."""
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/v1/yield-curve")
    if resp.status_code != 200:
        pytest.skip(f"DB not ready ({resp.status_code}) — content shape can't be checked")
    body = resp.json()
    assert "points" in body
    assert "shape" in body
    assert "sources" in body
    assert isinstance(body["points"], list)


@pytest.mark.asyncio
async def test_sources_returns_catalog_metadata(transport: ASGITransport) -> None:
    """The catalog has 26+ entries with the typed shape, even on empty DB
    (status counters become 'down' / rows_24h=0, but the catalog is
    server-side static metadata)."""
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/v1/sources")
    if resp.status_code != 200:
        pytest.skip(f"DB not ready ({resp.status_code})")
    body = resp.json()
    assert "sources" in body
    assert isinstance(body["sources"], list)
    assert body["n_sources"] >= 25
    # Each entry must carry the contract fields
    for entry in body["sources"][:3]:
        assert {"id", "name", "category", "cadence", "status", "rows_24h"} <= entry.keys()


@pytest.mark.asyncio
async def test_heatmap_returns_4_rows_4_cells(transport: ASGITransport) -> None:
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/v1/macro-pulse/heatmap")
    if resp.status_code != 200:
        pytest.skip(f"DB not ready ({resp.status_code})")
    body = resp.json()
    assert "rows" in body
    assert len(body["rows"]) == 4
    for row in body["rows"]:
        assert len(row["cells"]) == 4
        # Every cell carries `bias` even when value is None
        for cell in row["cells"]:
            assert "bias" in cell
            assert cell["bias"] in ("bull", "bear", "neutral")


@pytest.mark.asyncio
async def test_session_scenarios_validates_asset_pattern(transport: ASGITransport) -> None:
    """`/v1/sessions/{asset}/scenarios` rejects non-uppercase / too-short asset names."""
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # Below the 3-char minimum
        resp = await c.get("/v1/sessions/AB/scenarios")
    assert resp.status_code in (400, 404, 422, 503)
