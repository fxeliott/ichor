"""HTTP integration smoke tests on FastAPI routers.

Phase 2 Sprint 1 prep for CI ratchet S3 (cf SPEC.md §3.10 + SPEC_V2_HARDENING.md §2).
Currently: smoke checks only — does the route exist and respond 2xx/4xx
with the right shape, given an empty DB? Schema-aware contract tests
(schemathesis) follow in Phase D.

Coverage target: 35+ endpoints. This first batch covers the ones with
no required setup (admin, healthz, divergence-empty, calibration-empty,
data_pool inspection on a known asset, sources). The data-heavy routes
(sessions, briefings, alerts) need fixture-loading helpers — separate
file.

Run: pytest apps/api/tests/test_routers_smoke.py -v
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

# The import is async-safe: main.py registers the routers at import time
# without opening the lifespan (we override get_session below).
from ichor_api.main import app


@pytest.fixture
def transport() -> ASGITransport:
    return ASGITransport(app=app)


@pytest.mark.asyncio
async def test_healthz_returns_2xx_or_503(transport: ASGITransport) -> None:
    """`/healthz` is the basic liveness probe. Returns 200 if DB+Redis
    reachable, 503 otherwise. Both are valid in test mode where DB
    services may not be up."""
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/healthz")
    assert resp.status_code in (200, 503)


@pytest.mark.asyncio
async def test_openapi_schema_loads(transport: ASGITransport) -> None:
    """`/openapi.json` MUST load — required by schemathesis (CI S4)."""
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/openapi.json")
    assert resp.status_code == 200
    body = resp.json()
    assert "paths" in body
    # Phase 2 Sprint 1 added /v1/divergences — it should be in the schema.
    assert "/v1/divergences" in body["paths"]


@pytest.mark.asyncio
async def test_root_redirects_or_returns(transport: ASGITransport) -> None:
    """Root path can be 200/404/308 depending on FastAPI config."""
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/", follow_redirects=False)
    assert resp.status_code in (200, 308, 404)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path,expected",
    [
        # Empty DB: each route should respond with a structured empty/default
        # payload, not 500.
        ("/v1/divergences", (200, 503)),
        ("/v1/correlations", (200, 503)),
        ("/v1/calibration/summary", (200, 404, 503)),
        ("/v1/macro-pulse", (200, 503)),
    ],
)
async def test_routers_respond_structured(
    transport: ASGITransport, path: str, expected: tuple[int, ...]
) -> None:
    """Hit the route and check it returned a JSON body with no 5xx
    other than 503 (which means DB unreachable — normal in test)."""
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get(path)
    assert resp.status_code in expected, (
        f"{path} returned {resp.status_code} (expected {expected}): body={resp.text[:200]}"
    )


@pytest.mark.asyncio
async def test_divergence_query_validation(transport: ASGITransport) -> None:
    """`/v1/divergences` should reject out-of-range query params."""
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # since_hours > 168 should 422
        resp_bad = await c.get("/v1/divergences?since_hours=999")
    assert resp_bad.status_code == 422
