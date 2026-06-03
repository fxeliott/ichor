"""Tests for ``GET /v1/dollar-coherence`` — cross-asset USD coherence surface.

The router runs the latest-card-per-asset query INLINE (no service to patch),
so we mock the AsyncSession's ``execute(...).scalars().all()`` to return fake
card rows, then assert the projection + the 2026-05-29 incoherence + honest
empty degradation + the watermark posture.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from ichor_api.db import get_session
from ichor_api.routers.dollar_coherence import router as dollar_coherence_router


class _Card:
    """Minimal stand-in for a SessionCardAudit row (only the fields the
    router projects: asset / bias_direction / conviction_pct)."""

    def __init__(self, asset: str, bias: str, conviction: float) -> None:
        self.asset = asset
        self.bias_direction = bias
        self.conviction_pct = conviction


def _client(cards: list[_Card]) -> TestClient:
    app = FastAPI()
    app.include_router(dollar_coherence_router)
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = cards
    session.execute = AsyncMock(return_value=result)
    app.dependency_overrides[get_session] = lambda: session
    return TestClient(app)


def test_2026_05_29_incoherence_flags_equities() -> None:
    cards = [
        _Card("EUR_USD", "short", 60),
        _Card("XAU_USD", "short", 55),
        _Card("SPX500_USD", "long", 50),
        _Card("NAS100_USD", "long", 50),
    ]
    r = _client(cards).get("/v1/dollar-coherence")
    assert r.status_code == 200
    b = r.json()
    assert b["consensus"] == "usd_up"
    assert b["coherent"] is False
    assert set(b["outliers"]) == {"SPX500_USD", "NAS100_USD"}
    assert r.headers["Cache-Control"] == "private, no-store"
    assert "Incohérence" in b["coach_explanation"]
    # demote-only suggestions present + below original
    for a in b["outliers"]:
        assert b["recommended_demotions"][a] < 50


def test_coherent_strong_dollar_no_outliers() -> None:
    cards = [
        _Card("EUR_USD", "short", 60),
        _Card("XAU_USD", "short", 50),
        _Card("SPX500_USD", "short", 45),
    ]
    b = _client(cards).get("/v1/dollar-coherence").json()
    assert b["consensus"] == "usd_up"
    assert b["coherent"] is True
    assert b["outliers"] == []


def test_empty_db_degrades_honestly_no_404() -> None:
    """No cards today → 200 + neutral/coherent (NOT 404, unlike /v1/verdict)."""
    r = _client([]).get("/v1/dollar-coherence")
    assert r.status_code == 200
    b = r.json()
    assert b["consensus"] == "neutral"
    assert b["coherent"] is True
    assert b["n_directional"] == 0
    assert b["views"] == []


def test_views_projection_shape() -> None:
    cards = [_Card("EUR_USD", "short", 60), _Card("GBP_USD", "short", 55)]
    b = _client(cards).get("/v1/dollar-coherence").json()
    assert len(b["views"]) == 2
    eur = next(v for v in b["views"] if v["asset"] == "EUR_USD")
    assert eur["stance"] == "usd_up"
    assert eur["bias"] == "short"
    assert eur["conviction"] == 60
    assert "weight" in eur


def test_route_is_watermarked() -> None:
    """ADR-079 : the route DERIVES from LLM-origin bias cards → must be in
    the watermarked prefix set (lockstep guarded by test_invariants_ichor)."""
    from ichor_api.middleware.ai_watermark import DEFAULT_WATERMARKED_PREFIXES

    assert "/v1/dollar-coherence" in DEFAULT_WATERMARKED_PREFIXES
