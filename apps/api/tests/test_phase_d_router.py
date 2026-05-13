"""Round-21 — `/v1/phase-d/*` observability router tests.

The router is read-only on `auto_improvement_log` and
`brier_aggregator_weights`. The smoke fixtures in conftest.py override
`get_session` so route hits go through ASGITransport without touching
Postgres. We exercise :

1. Route registration : both endpoints are mounted on the app and
   respond (200 or 503, never 404).
2. Query parameter validation : asset / regime regex patterns, since_days
   bounds, limit bounds, unknown loop_kind tolerated (empty result).
3. Response schema : 200 responses match the declared Pydantic shapes.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Lazy : importing main.py wires every router incl. phase_d_router."""
    from ichor_api.main import app

    with TestClient(app) as c:
        yield c


# ──────────────────────────── route registration ──────────────────────────


def test_audit_log_route_registered(client: TestClient) -> None:
    """Hitting the route returns 200 (in-memory smoke DB) or 503 (DB
    unavailable) — never 404."""
    r = client.get("/v1/phase-d/audit-log")
    assert r.status_code in (200, 503), (
        f"Expected 200/503 for registered route, got {r.status_code}: {r.text[:200]}"
    )


def test_aggregator_weights_route_registered(client: TestClient) -> None:
    r = client.get("/v1/phase-d/aggregator-weights")
    assert r.status_code in (200, 503), (
        f"Expected 200/503 for registered route, got {r.status_code}: {r.text[:200]}"
    )


# ──────────────────────────── query validation ──────────────────────────


def test_audit_log_rejects_malformed_asset(client: TestClient) -> None:
    """Asset regex `^[A-Z0-9_]{3,16}$` — lowercase / too-short rejected
    by FastAPI Query validation (422)."""
    r = client.get("/v1/phase-d/audit-log?asset=eu")
    assert r.status_code == 422


def test_audit_log_rejects_malformed_regime(client: TestClient) -> None:
    """Regime regex `^[a-z_]{2,64}$` — uppercase rejected."""
    r = client.get("/v1/phase-d/audit-log?regime=USD_COMPLACENCY")
    assert r.status_code == 422


def test_audit_log_rejects_since_days_out_of_bounds(client: TestClient) -> None:
    """since_days must be in [1, 365]."""
    r = client.get("/v1/phase-d/audit-log?since_days=0")
    assert r.status_code == 422
    r = client.get("/v1/phase-d/audit-log?since_days=500")
    assert r.status_code == 422


def test_audit_log_rejects_limit_out_of_bounds(client: TestClient) -> None:
    """limit must be in [1, 500]."""
    r = client.get("/v1/phase-d/audit-log?limit=0")
    assert r.status_code == 422
    r = client.get("/v1/phase-d/audit-log?limit=10000")
    assert r.status_code == 422


def test_audit_log_unknown_loop_kind_returns_empty_not_400(
    client: TestClient,
) -> None:
    """Unknown loop_kind values are tolerated — return empty result.
    The router stays lenient because operators may typo-ed queries."""
    r = client.get("/v1/phase-d/audit-log?loop_kind=not_a_real_loop")
    assert r.status_code in (200, 503)
    if r.status_code == 200:
        body = r.json()
        assert body["count"] == 0
        assert body["rows"] == []
        assert body["loop_kind_filter"] == "not_a_real_loop"


def test_audit_log_accepts_valid_loop_kinds(client: TestClient) -> None:
    """All 4 ADR-087 canonical loop_kinds must be accepted."""
    for kind in ("brier_aggregator", "adwin_drift", "post_mortem", "meta_prompt"):
        r = client.get(f"/v1/phase-d/audit-log?loop_kind={kind}")
        assert r.status_code in (200, 503), (
            f"Expected 200/503 for valid loop_kind {kind!r}, got {r.status_code}"
        )


def test_aggregator_weights_accepts_pocket_version(client: TestClient) -> None:
    r = client.get("/v1/phase-d/aggregator-weights?pocket_version=1")
    assert r.status_code in (200, 503)


def test_aggregator_weights_rejects_invalid_pocket_version(
    client: TestClient,
) -> None:
    """pocket_version must be ≥ 1."""
    r = client.get("/v1/phase-d/aggregator-weights?pocket_version=0")
    assert r.status_code == 422


def test_aggregator_weights_accepts_asset_filter(client: TestClient) -> None:
    r = client.get("/v1/phase-d/aggregator-weights?asset=EUR_USD")
    assert r.status_code in (200, 503)


# ──────────────────────────── response shape (when 200) ──────────────────


def test_audit_log_response_schema_when_200(client: TestClient) -> None:
    """When the smoke DB returns 200, the response must satisfy the
    declared Pydantic shape."""
    r = client.get("/v1/phase-d/audit-log?since_days=1&limit=5")
    if r.status_code != 200:
        pytest.skip(f"smoke DB unavailable (status {r.status_code})")
    body = r.json()
    assert isinstance(body, dict)
    assert "rows" in body
    assert "count" in body
    assert "window_days" in body
    assert body["window_days"] == 1
    assert isinstance(body["rows"], list)


def test_aggregator_weights_response_schema_when_200(client: TestClient) -> None:
    r = client.get("/v1/phase-d/aggregator-weights")
    if r.status_code != 200:
        pytest.skip(f"smoke DB unavailable (status {r.status_code})")
    body = r.json()
    assert isinstance(body, dict)
    assert "rows" in body
    assert "count" in body
    assert "pocket_version" in body
    assert body["pocket_version"] == 1


# ──────────────────────────── openapi / docs ──────────────────────────


def test_openapi_includes_phase_d_routes(client: TestClient) -> None:
    """The 3 endpoints must appear in the OpenAPI schema — catches
    accidental router-deregister."""
    r = client.get("/openapi.json")
    assert r.status_code == 200
    spec = r.json()
    paths = set(spec["paths"].keys())
    assert "/v1/phase-d/audit-log" in paths
    assert "/v1/phase-d/aggregator-weights" in paths
    assert "/v1/phase-d/pass3-addenda" in paths


# ──────────────────────────── /pass3-addenda (round-22) ──────────────────


def test_pass3_addenda_route_registered(client: TestClient) -> None:
    r = client.get("/v1/phase-d/pass3-addenda")
    assert r.status_code in (200, 503), (
        f"Expected 200/503 for registered route, got {r.status_code}"
    )


def test_pass3_addenda_default_status_filter_is_active(client: TestClient) -> None:
    r = client.get("/v1/phase-d/pass3-addenda")
    if r.status_code != 200:
        pytest.skip(f"smoke DB unavailable (status {r.status_code})")
    body = r.json()
    assert body["status_filter"] == "active"


def test_pass3_addenda_accepts_4_canonical_statuses(client: TestClient) -> None:
    for status in ("active", "expired", "superseded", "rejected"):
        r = client.get(f"/v1/phase-d/pass3-addenda?status={status}")
        assert r.status_code in (200, 503), (
            f"Expected 200/503 for status={status!r}, got {r.status_code}"
        )


def test_pass3_addenda_unknown_status_returns_empty_not_400(
    client: TestClient,
) -> None:
    """Lenient — typo'd status doesn't 400, returns empty + echoes
    the filter in the response."""
    r = client.get("/v1/phase-d/pass3-addenda?status=not_a_real_status")
    assert r.status_code in (200, 503)
    if r.status_code == 200:
        body = r.json()
        assert body["count"] == 0
        assert body["rows"] == []
        assert body["status_filter"] == "not_a_real_status"


def test_pass3_addenda_rejects_malformed_asset(client: TestClient) -> None:
    r = client.get("/v1/phase-d/pass3-addenda?asset=lower")
    assert r.status_code == 422


def test_pass3_addenda_rejects_limit_out_of_bounds(client: TestClient) -> None:
    r = client.get("/v1/phase-d/pass3-addenda?limit=0")
    assert r.status_code == 422
    r = client.get("/v1/phase-d/pass3-addenda?limit=10000")
    assert r.status_code == 422
