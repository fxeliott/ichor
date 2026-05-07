"""Unit tests for the CSP + security headers middleware."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from ichor_api.services.csp_middleware import (
    _BASE_HEADERS,
    CSPSecurityHeadersMiddleware,
    _build_csp,
)


def test_build_csp_includes_strict_dynamic() -> None:
    csp = _build_csp("abc123", html=False).decode()
    assert "default-src 'none'" in csp
    assert "'strict-dynamic'" in csp
    assert "'nonce-abc123'" in csp
    assert "form-action 'self'" in csp


def test_build_csp_html_allows_swagger_cdn() -> None:
    csp = _build_csp("xyz", html=True).decode()
    assert "cdn.jsdelivr.net" in csp


def test_build_csp_json_locks_img_src_to_self() -> None:
    csp = _build_csp("xyz", html=False).decode()
    # img-src should NOT include cdn.jsdelivr.net for JSON routes
    assert "cdn.jsdelivr.net" not in csp


def test_base_headers_include_owasp_set() -> None:
    keys = {k for k, _ in _BASE_HEADERS}
    assert b"x-content-type-options" in keys
    assert b"strict-transport-security" in keys
    assert b"referrer-policy" in keys
    assert b"x-frame-options" in keys
    assert b"permissions-policy" in keys


@pytest.mark.asyncio
async def test_middleware_adds_csp_to_response_start() -> None:
    inner_app = AsyncMock()
    sent: list[dict] = []

    async def _send(msg):
        sent.append(msg)

    async def _inner(scope, receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": b'{"ok":true}'})

    mw = CSPSecurityHeadersMiddleware(_inner)
    scope = {"type": "http", "path": "/v1/today", "method": "GET", "state": {}}
    await mw(scope, AsyncMock(), _send)

    start = next(m for m in sent if m.get("type") == "http.response.start")
    headers = dict(start["headers"])
    assert b"content-security-policy" in headers
    assert b"x-content-type-options" in headers
    assert headers[b"x-frame-options"] == b"DENY"
    # Nonce was generated and is in the CSP
    csp_value = headers[b"content-security-policy"].decode()
    assert "nonce-" in csp_value


@pytest.mark.asyncio
async def test_middleware_stashes_nonce_in_scope_state() -> None:
    sent: list[dict] = []

    async def _send(msg):
        sent.append(msg)

    captured_state: dict = {}

    async def _inner(scope, receive, send):
        captured_state.update(scope.get("state") or {})
        await send(
            {"type": "http.response.start", "status": 200, "headers": []}
        )
        await send({"type": "http.response.body", "body": b""})

    mw = CSPSecurityHeadersMiddleware(_inner)
    scope = {"type": "http", "path": "/v1/today", "method": "GET", "state": {}}
    await mw(scope, AsyncMock(), _send)

    assert "csp_nonce" in captured_state
    assert len(captured_state["csp_nonce"]) >= 32  # token_urlsafe(32) ≥ 32 chars


@pytest.mark.asyncio
async def test_middleware_drops_prior_csp_header() -> None:
    """If an inner layer set its own CSP, ours wins (drops downstream)."""
    sent: list[dict] = []

    async def _send(msg):
        sent.append(msg)

    async def _inner(scope, receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-security-policy", b"default-src *")],
            }
        )
        await send({"type": "http.response.body", "body": b""})

    mw = CSPSecurityHeadersMiddleware(_inner)
    scope = {"type": "http", "path": "/v1/today", "method": "GET", "state": {}}
    await mw(scope, AsyncMock(), _send)

    start = next(m for m in sent if m.get("type") == "http.response.start")
    csp_values = [v for (k, v) in start["headers"] if k == b"content-security-policy"]
    assert len(csp_values) == 1, "exactly one CSP header should be set"
    assert b"default-src *" not in csp_values[0]
    assert b"default-src 'none'" in csp_values[0]


@pytest.mark.asyncio
async def test_middleware_ignores_non_http_scope() -> None:
    inner_app = AsyncMock()
    mw = CSPSecurityHeadersMiddleware(inner_app)
    scope = {"type": "websocket", "path": "/ws"}
    await mw(scope, AsyncMock(), AsyncMock())
    inner_app.assert_called_once()
