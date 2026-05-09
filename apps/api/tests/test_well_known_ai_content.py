"""Tests for /.well-known/ai-content endpoint (W89, ADR-080).

EU Code of Practice draft (Dec-2025) discovery hint : the endpoint
publishes a machine-readable inventory of LLM-derived URL prefixes
on the host so audit tools / crawlers / downstream API consumers can
fetch it once and know the watermark boundary.
"""

from __future__ import annotations

import re

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ichor_api.routers.well_known import router

# RFC3339 with Z offset, second precision.
_RFC3339_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _build_app() -> FastAPI:
    """Mount the router on a bare FastAPI for isolation."""
    app = FastAPI()
    app.include_router(router)
    return app


def test_inventory_returns_200_and_json() -> None:
    """Endpoint is GET-only, public, returns JSON."""
    client = TestClient(_build_app())
    r = client.get("/.well-known/ai-content")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/json")


def test_inventory_schema_v1_contract() -> None:
    """Schema version 1 — frozen field set, ordered keys not required."""
    client = TestClient(_build_app())
    r = client.get("/.well-known/ai-content")
    body = r.json()
    expected_keys = {
        "schema_version",
        "spec",
        "host_role",
        "provider",
        "disclosure_url",
        "watermarked_prefixes",
        "watermark_headers",
        "generated_at",
    }
    assert set(body.keys()) == expected_keys, (
        f"schema drift : got {sorted(body.keys())}, expected {sorted(expected_keys)}"
    )
    assert body["schema_version"] == 1
    assert body["spec"] == "EU AI Act Article 50(2)"
    assert body["host_role"] == "deployer"


def test_inventory_provider_and_disclosure_url() -> None:
    """Provider tag + disclosure URL come from Settings — not hard-coded."""
    client = TestClient(_build_app())
    r = client.get("/.well-known/ai-content")
    body = r.json()
    assert body["provider"].startswith("anthropic-")
    assert body["disclosure_url"].startswith("https://")
    assert "ai-disclosure" in body["disclosure_url"]


def test_inventory_watermarked_prefixes_match_adr_079() -> None:
    """Default 5 prefixes must align with the AIWatermarkMiddleware
    DEFAULT_WATERMARKED_PREFIXES tuple (single source of truth)."""
    client = TestClient(_build_app())
    r = client.get("/.well-known/ai-content")
    body = r.json()
    assert set(body["watermarked_prefixes"]) == {
        "/v1/briefings",
        "/v1/sessions",
        "/v1/post-mortems",
        "/v1/today",
        "/v1/scenarios",
    }


def test_inventory_watermark_headers_full_set() -> None:
    """All 4 watermark headers must be advertised."""
    client = TestClient(_build_app())
    r = client.get("/.well-known/ai-content")
    body = r.json()
    assert body["watermark_headers"] == [
        "X-Ichor-AI-Generated",
        "X-Ichor-AI-Provider",
        "X-Ichor-AI-Generated-At",
        "X-Ichor-AI-Disclosure",
    ]


def test_inventory_generated_at_is_rfc3339_utc() -> None:
    """`generated_at` must be RFC3339 UTC second precision."""
    client = TestClient(_build_app())
    r = client.get("/.well-known/ai-content")
    body = r.json()
    assert _RFC3339_Z.match(body["generated_at"]), f"not RFC3339-Z: {body['generated_at']!r}"


def test_inventory_cache_control_header() -> None:
    """5-minute public cache so audit crawlers don't hammer the host."""
    client = TestClient(_build_app())
    r = client.get("/.well-known/ai-content")
    cc = r.headers.get("cache-control", "")
    assert "public" in cc
    assert "max-age=300" in cc
