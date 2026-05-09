"""Tests for AIWatermarkMiddleware (EU AI Act §50.2 — W88, ADR-079)."""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ichor_api.middleware.ai_watermark import (
    DEFAULT_PROVIDER_TAG,
    DEFAULT_WATERMARKED_PREFIXES,
    AIWatermarkMiddleware,
)

# RFC3339 with Z offset, second precision — matches what the
# middleware emits.
_RFC3339_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _build_app(
    *,
    watermarked_prefixes: tuple[str, ...] | None = None,
    provider_tag: str = DEFAULT_PROVIDER_TAG,
    disclosure_url: str = "https://example.test/legal/ai",
) -> FastAPI:
    """FastAPI app with two contrasting routes : LLM-derived and pure-data."""
    app = FastAPI()
    app.add_middleware(
        AIWatermarkMiddleware,
        watermarked_prefixes=watermarked_prefixes,
        provider_tag=provider_tag,
        disclosure_url=disclosure_url,
    )

    @app.get("/v1/briefings/today")
    def briefing() -> dict[str, str]:
        return {"thesis": "synthetic LLM output"}

    @app.get("/v1/market/eurusd")
    def market() -> dict[str, float]:
        return {"price": 1.0823}

    @app.get("/v1/sessions/abc/scenarios")
    def scenarios() -> dict[str, list[str]]:
        return {"scenarios": ["A", "B"]}

    @app.get("/v1/today")
    def today() -> dict[str, str]:
        return {"summary": "synthetic LLM output"}

    @app.get("/v1/post-mortems/2026-W18")
    def post_mortems() -> dict[str, str]:
        return {"verdict": "synthetic LLM output"}

    return app


def test_watermark_present_on_llm_route() -> None:
    """Briefings route must carry all four AI-Act §50.2 headers."""
    client = TestClient(_build_app())
    r = client.get("/v1/briefings/today")
    assert r.status_code == 200
    assert r.headers["X-Ichor-AI-Generated"] == "true"
    assert r.headers["X-Ichor-AI-Provider"] == DEFAULT_PROVIDER_TAG
    assert r.headers["X-Ichor-AI-Disclosure"].startswith("https://")
    assert "X-Ichor-AI-Generated-At" in r.headers


def test_watermark_absent_on_pure_data_route() -> None:
    """Market route is collector-derived, must NOT be watermarked."""
    client = TestClient(_build_app())
    r = client.get("/v1/market/eurusd")
    assert r.status_code == 200
    for h in (
        "X-Ichor-AI-Generated",
        "X-Ichor-AI-Provider",
        "X-Ichor-AI-Generated-At",
        "X-Ichor-AI-Disclosure",
    ):
        assert h not in r.headers, f"unexpected watermark header on pure-data route: {h}"


def test_watermark_timestamp_is_rfc3339_utc() -> None:
    """`X-Ichor-AI-Generated-At` must be RFC3339, second precision, UTC `Z`."""
    client = TestClient(_build_app())
    before = datetime.now(UTC).replace(microsecond=0)
    r = client.get("/v1/sessions/abc/scenarios")
    after = datetime.now(UTC).replace(microsecond=0)
    ts = r.headers["X-Ichor-AI-Generated-At"]
    assert _RFC3339_Z.match(ts), f"not RFC3339-Z: {ts!r}"
    parsed = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    assert before <= parsed <= after


def test_watermark_default_prefixes_cover_adr029_surface() -> None:
    """Regression guard : the default prefix tuple matches the
    ADR-029 inventory of LLM-derived routes."""
    expected = {
        "/v1/briefings",
        "/v1/sessions",
        "/v1/post-mortems",
        "/v1/today",
        "/v1/scenarios",
    }
    assert set(DEFAULT_WATERMARKED_PREFIXES) == expected


def test_config_override_changes_provider_and_disclosure() -> None:
    """Custom provider_tag + disclosure_url propagate to headers."""
    client = TestClient(
        _build_app(
            provider_tag="anthropic-claude-haiku-4-5",
            disclosure_url="https://other.test/disclose",
        )
    )
    r = client.get("/v1/briefings/today")
    assert r.headers["X-Ichor-AI-Provider"] == "anthropic-claude-haiku-4-5"
    assert r.headers["X-Ichor-AI-Disclosure"] == "https://other.test/disclose"


def test_config_override_restricts_prefix_set() -> None:
    """Shrinking the prefix list at construction excludes routes."""
    client = TestClient(_build_app(watermarked_prefixes=("/v1/today",)))
    # Briefing now NOT watermarked.
    r = client.get("/v1/briefings/today")
    assert "X-Ichor-AI-Generated" not in r.headers
    # /v1/today still watermarked
    r2 = client.get("/v1/today")
    assert r2.headers.get("X-Ichor-AI-Generated") == "true"


@pytest.mark.parametrize(
    "path",
    [
        "/v1/briefings/today",
        "/v1/sessions/abc/scenarios",
        "/v1/today",
        "/v1/post-mortems/2026-W18",
    ],
)
def test_prefix_match_is_path_startswith(path: str) -> None:
    """Verify path-prefix semantics on a representative subset."""
    client = TestClient(_build_app())
    r = client.get(path)
    assert r.headers.get("X-Ichor-AI-Generated") == "true", (
        f"path {path} should be watermarked but isn't"
    )
