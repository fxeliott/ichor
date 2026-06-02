"""Tests for Phase 2 push-on-alert wiring (_maybe_notify).

A trader-relevant (critical) alert now also pushes a web notification.
Pins: critical fires send_to_all, non-critical is silent, an
ADR-017-dirty copy is never sent, and a push failure never propagates
(alert persistence must not break).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from ichor_api.services.alerts_runner import _maybe_notify


def _hit(*, severity: str = "critical"):
    alert_def = SimpleNamespace(
        code="VIX_SPIKE",
        severity=severity,
        title_template="VIX à {value}",
        metric_name="VIXCLS",
        description="Volatilité en forte hausse — régime de marché à surveiller.",
    )
    return SimpleNamespace(
        alert_def=alert_def,
        metric_value=35.0,
        threshold=30.0,
        direction_observed="above",
        source_payload={},
    )


@pytest.mark.asyncio
async def test_critical_fires_push(monkeypatch):
    calls: list[tuple] = []

    async def fake_send(title, body, *, url="/"):
        calls.append((title, body, url))
        return 1

    monkeypatch.setattr("ichor_api.services.push.send_to_all", fake_send)
    monkeypatch.setattr("ichor_api.services.adr017_filter.is_adr017_clean", lambda _t: True)

    await _maybe_notify(_hit(severity="critical"), asset="EUR_USD")
    assert len(calls) == 1
    title, body, url = calls[0]
    assert title == "VIX à 35.0"
    assert "Volatilité" in body
    assert url == "/briefing/EUR_USD"


@pytest.mark.asyncio
async def test_non_critical_is_silent(monkeypatch):
    calls: list[int] = []

    async def fake_send(*_a, **_k):
        calls.append(1)
        return 1

    monkeypatch.setattr("ichor_api.services.push.send_to_all", fake_send)
    await _maybe_notify(_hit(severity="warning"), asset="EUR_USD")
    await _maybe_notify(_hit(severity="info"), asset="EUR_USD")
    assert calls == []


@pytest.mark.asyncio
async def test_adr017_dirty_copy_not_sent(monkeypatch):
    calls: list[int] = []

    async def fake_send(*_a, **_k):
        calls.append(1)
        return 1

    monkeypatch.setattr("ichor_api.services.push.send_to_all", fake_send)
    monkeypatch.setattr("ichor_api.services.adr017_filter.is_adr017_clean", lambda _t: False)
    await _maybe_notify(_hit(severity="critical"), asset="EUR_USD")
    assert calls == []


@pytest.mark.asyncio
async def test_no_asset_uses_root_url(monkeypatch):
    calls: list[tuple] = []

    async def fake_send(title, body, *, url="/"):
        calls.append((title, body, url))
        return 0

    monkeypatch.setattr("ichor_api.services.push.send_to_all", fake_send)
    monkeypatch.setattr("ichor_api.services.adr017_filter.is_adr017_clean", lambda _t: True)
    await _maybe_notify(_hit(severity="critical"), asset=None)
    assert calls[0][2] == "/"


@pytest.mark.asyncio
async def test_push_failure_is_swallowed(monkeypatch):
    async def boom(*_a, **_k):
        raise RuntimeError("push service down")

    monkeypatch.setattr("ichor_api.services.push.send_to_all", boom)
    monkeypatch.setattr("ichor_api.services.adr017_filter.is_adr017_clean", lambda _t: True)
    # Must not raise — alert persistence must never break on a push failure.
    await _maybe_notify(_hit(severity="critical"), asset="EUR_USD")
