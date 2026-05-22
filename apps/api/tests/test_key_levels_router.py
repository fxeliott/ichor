"""r59 — `GET /v1/key-levels` endpoint tests.

The router exposes the 9 KeyLevel computers (TGA + HKMA + gamma_flip x2 +
SKEW + HY OAS + VIX + polymarket x3) per ADR-083 D3 canonical JSON shape.
Bridge architectural toward ADR-083 D4 frontend (rule 4 frontend gel
décision Eliot critique pour la suite).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Lazy : importing main.py wires every router incl. key_levels_router."""
    from ichor_api.main import app

    with TestClient(app) as c:
        yield c


# ──────────────────────────── route registration ──────────────────────────


def test_key_levels_route_registered(client: TestClient) -> None:
    """Hitting /v1/key-levels returns 200 (in-memory smoke DB) or 503 (DB
    unavailable) — never 404. Pin route mount in main.py."""
    r = client.get("/v1/key-levels")
    assert r.status_code in (200, 503), (
        f"Expected 200/503 for registered route, got {r.status_code}: {r.text[:200]}"
    )


# ──────────────────────────── response schema ──────────────────────────


def test_response_envelope_shape(client: TestClient) -> None:
    """200 response must have envelope `{count, items: list}` per
    KeyLevelsResponse Pydantic model."""
    r = client.get("/v1/key-levels")
    if r.status_code != 200:
        pytest.skip(f"DB unavailable in this test env (got {r.status_code})")
    body = r.json()
    assert "count" in body
    assert "items" in body
    assert isinstance(body["count"], int)
    assert isinstance(body["items"], list)
    assert body["count"] == len(body["items"])


def test_each_item_matches_adr_083_d3_shape(client: TestClient) -> None:
    """Each KeyLevel item must conform to ADR-083 D3 canonical fields :
    asset, level, kind, side, source. `note` optional (default '')."""
    r = client.get("/v1/key-levels")
    if r.status_code != 200:
        pytest.skip(f"DB unavailable (got {r.status_code})")
    items = r.json()["items"]
    for item in items:
        assert {"asset", "level", "kind", "side", "source"}.issubset(item.keys())
        assert isinstance(item["asset"], str)
        assert isinstance(item["level"], (int, float))
        assert isinstance(item["kind"], str)
        assert isinstance(item["side"], str)
        assert isinstance(item["source"], str)


def test_kind_values_in_closed_enum(client: TestClient) -> None:
    """`kind` field must be one of the 9 ADR-083 D3 enum values.
    Drift = ADR amendment required."""
    r = client.get("/v1/key-levels")
    if r.status_code != 200:
        pytest.skip(f"DB unavailable (got {r.status_code})")
    items = r.json()["items"]
    allowed_kinds = {
        "tga_liquidity_gate",
        "rrp_liquidity_gate",
        "gamma_flip",
        "peg_break_hkma",
        "peg_break_pboc_fix",
        "vix_regime_switch",
        "skew_regime_switch",
        "hy_oas_percentile",
        "polymarket_decision",
    }
    for item in items:
        assert item["kind"] in allowed_kinds, (
            f"unexpected kind {item['kind']!r} not in ADR-083 D3 enum"
        )


# ──────────────────────────── OpenAPI exposure ──────────────────────────


def test_openapi_includes_key_levels_endpoint(client: TestClient) -> None:
    """The endpoint must be in OpenAPI spec for docs/Swagger discovery."""
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json().get("paths", {})
    assert "/v1/key-levels" in paths, (
        f"/v1/key-levels missing from OpenAPI : found {sorted(paths.keys())[:10]}..."
    )
    # Tag check
    op = paths["/v1/key-levels"].get("get", {})
    assert "key-levels" in op.get("tags", [])
