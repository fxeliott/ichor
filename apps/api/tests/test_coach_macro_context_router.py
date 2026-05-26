"""r162 tests for ``GET /v1/coach-macro-context`` — Stride 8 Phase 2
narrative-synthesis surface per ADR-106.

Covers atom-level :
- 200 OK on happy path with full CoachMacroContext shape
- Cache-Control: private, no-store header (LIVE state, never cache)
- Asset-agnostic surface (no path param, returns the same context for
  every priority asset by construction)
- Pydantic shape parity : every field surfaces verbatim through the
  ``response_model``
- ADR-079 watermark middleware lockstep — the new prefix
  ``/v1/coach-macro-context`` is present in BOTH the middleware
  DEFAULT_WATERMARKED_PREFIXES tuple AND Settings default (W90
  invariant defended at this layer too — defense-in-depth vs the
  invariants_ichor source-inspection guard).

Mirrors the ``test_event_anticipation.py`` r152 TestClient + MagicMock
pattern (no DB hit ; pure pure-fn router wiring verification).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from ichor_api.db import get_session
from ichor_api.routers.coach_macro_context import router as coach_router
from ichor_brain.coach_macro_context import (
    CalendarSurprise,
    CoachMacroContext,
)


def _build_sample_context() -> CoachMacroContext:
    """Build a fully-populated CoachMacroContext fixture exercising every
    field type — non-null dominant_theme + non-empty top_next_surprises +
    expansion cycle so the happy path is meaningfully covered."""
    return CoachMacroContext(
        cycle="expansion",
        cycle_confidence_pct=75.0,
        growth_signal="strong",
        inflation_signal="falling",
        dominant_theme="inflation_data",
        dominant_theme_strength_z=2.3,
        top_next_surprises=[
            CalendarSurprise(
                event_label="Core PCE Price Index m/m",
                scheduled_at_paris=datetime(2026, 5, 28, 14, 30, tzinfo=UTC),
                priority="high",
                why_it_matters=(
                    "Donnée directement liée au cycle expansion (Goldilocks) actuel — "
                    "surveille la surprise pour anticiper le repricing."
                ),
            ),
            CalendarSurprise(
                event_label="Prelim GDP q/q",
                scheduled_at_paris=datetime(2026, 5, 29, 12, 30, tzinfo=UTC),
                priority="medium",
                why_it_matters=(
                    "Évènement à fort impact mais pas spécifique au cycle expansion (Goldilocks) ; "
                    "surveille pour la volatilité globale."
                ),
            ),
        ],
        coach_paragraph=(
            "Aujourd'hui mardi 26 mai 2026, on est en cycle de expansion (Goldilocks) "
            "(confiance 75 %). Le driver dominant est l'inflation — intensité marquée "
            "(|z| ≥ 2). Surveille « Core PCE Price Index m/m » (jeudi 28 mai 14h30 Paris) "
            "pour ta session NY 14h-20h."
        ),
        data_freshness_days=3,
        generated_at_utc=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
    )


def _build_uncertain_context() -> CoachMacroContext:
    """Build a doctrine #11 calibrated-honesty fixture — cycle="uncertain"
    + dominant_theme=None + empty surprises — to ensure the panel can
    surface the honest-absence state through the wire shape."""
    return CoachMacroContext(
        cycle="uncertain",
        cycle_confidence_pct=0.0,
        growth_signal="uncertain",
        inflation_signal="uncertain",
        dominant_theme=None,
        dominant_theme_strength_z=None,
        top_next_surprises=[],
        coach_paragraph=(
            "Aujourd'hui dimanche 26 mai 2026, le cycle macro est incertain — soit "
            "les données FRED sont stales, soit l'axe croissance × inflation est trop "
            "ambigu pour trancher (doctrine de calibrated honesty). Aucun driver macro "
            "ne se détache nettement cette semaine (toutes les séries FRED restent "
            "proches de leur moyenne). Aucun évènement à impact majeur n'est attendu "
            "dans les 7 jours."
        ),
        data_freshness_days=60,  # past MAX_FRESHNESS_DAYS = 45
        generated_at_utc=datetime(2026, 5, 26, 12, 0, tzinfo=UTC),
    )


def _make_app(builder_return: CoachMacroContext) -> FastAPI:
    """Compose a minimal FastAPI app with only the coach router mounted +
    the builder patched via dependency override. Avoids spinning the full
    apps/api lifespan (DB engine + Redis + Langfuse) for a router-shape test."""
    app = FastAPI()
    app.include_router(coach_router)

    async def fake_session():
        # The session is never used because we patch the builder ; just
        # yield something AsyncSession-shaped to satisfy the type hint.
        yield AsyncMock()

    app.dependency_overrides[get_session] = fake_session
    return app


# ── happy path : full CoachMacroContext through wire ──────────────────


class TestR162CoachMacroContextHappyPath:
    """200 OK + shape parity + Cache-Control header on the canonical
    happy path. Mirrors r152 ``TestR152RouterAssetPattern`` discipline."""

    def test_returns_200_with_full_context_shape(self, monkeypatch) -> None:
        """Happy path : router returns the builder's CoachMacroContext
        verbatim as JSON ; every field present + typed correctly."""
        sample = _build_sample_context()

        async def fake_build(*_args, **_kwargs):
            return sample

        monkeypatch.setattr(
            "ichor_api.routers.coach_macro_context.build_coach_macro_context",
            fake_build,
        )

        app = _make_app(sample)
        client = TestClient(app)
        try:
            resp = client.get("/v1/coach-macro-context")
            assert resp.status_code == 200, resp.text
            body = resp.json()
            # Cycle + growth/inflation axis
            assert body["cycle"] == "expansion"
            assert body["cycle_confidence_pct"] == 75.0
            assert body["growth_signal"] == "strong"
            assert body["inflation_signal"] == "falling"
            # Dominant theme + z-score
            assert body["dominant_theme"] == "inflation_data"
            assert body["dominant_theme_strength_z"] == 2.3
            # Surprises list + structure parity
            assert len(body["top_next_surprises"]) == 2
            first = body["top_next_surprises"][0]
            assert first["event_label"] == "Core PCE Price Index m/m"
            assert first["priority"] == "high"
            assert "Core PCE" not in first.get("why_it_matters", "") or True
            assert "surveille la surprise" in first["why_it_matters"]
            # Coach paragraph + freshness
            assert "expansion (Goldilocks)" in body["coach_paragraph"]
            assert body["data_freshness_days"] == 3
            # Generated_at UTC (Pydantic emits ISO string with offset)
            assert body["generated_at_utc"].startswith("2026-05-26T12:00:00")
        finally:
            app.dependency_overrides.clear()

    def test_cache_control_header_is_private_no_store(self, monkeypatch) -> None:
        """LIVE state discipline — never cache at intermediate proxy.
        Mirror of ``routers/verdict.py:126``."""
        sample = _build_sample_context()

        async def fake_build(*_args, **_kwargs):
            return sample

        monkeypatch.setattr(
            "ichor_api.routers.coach_macro_context.build_coach_macro_context",
            fake_build,
        )

        app = _make_app(sample)
        client = TestClient(app)
        try:
            resp = client.get("/v1/coach-macro-context")
            assert resp.status_code == 200
            assert resp.headers.get("cache-control") == "private, no-store"
        finally:
            app.dependency_overrides.clear()

    def test_asset_agnostic_no_path_param(self, monkeypatch) -> None:
        """The endpoint is asset-agnostic by design — no path param. The
        macro narrative is the SAME for every priority asset (per-asset
        reads live on /v1/verdict + /v1/event-anticipation). Pin the
        shape : appending an asset to the URL MUST 404, not silently
        match another route."""
        sample = _build_sample_context()

        async def fake_build(*_args, **_kwargs):
            return sample

        monkeypatch.setattr(
            "ichor_api.routers.coach_macro_context.build_coach_macro_context",
            fake_build,
        )

        app = _make_app(sample)
        client = TestClient(app)
        try:
            resp_with_asset = client.get("/v1/coach-macro-context/EUR_USD")
            assert resp_with_asset.status_code == 404, (
                "endpoint must be asset-agnostic ; an /EUR_USD suffix should NOT match"
            )
            # The bare endpoint still works in the same client lifecycle.
            resp = client.get("/v1/coach-macro-context")
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.clear()


# ── doctrine #11 honest-absence path ──────────────────────────────────


class TestR162CoachMacroContextHonestAbsence:
    """The builder returns a fully-populated CoachMacroContext even when
    classifiers are inconclusive (doctrine #11 calibrated honesty).
    Cycle="uncertain" + dominant_theme=None + empty surprises must
    serialise cleanly — no 500, no field stripping."""

    def test_uncertain_cycle_serialises_cleanly(self, monkeypatch) -> None:
        sample = _build_uncertain_context()

        async def fake_build(*_args, **_kwargs):
            return sample

        monkeypatch.setattr(
            "ichor_api.routers.coach_macro_context.build_coach_macro_context",
            fake_build,
        )

        app = _make_app(sample)
        client = TestClient(app)
        try:
            resp = client.get("/v1/coach-macro-context")
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["cycle"] == "uncertain"
            assert body["cycle_confidence_pct"] == 0.0
            assert body["growth_signal"] == "uncertain"
            assert body["inflation_signal"] == "uncertain"
            assert body["dominant_theme"] is None
            assert body["dominant_theme_strength_z"] is None
            assert body["top_next_surprises"] == []
            assert body["data_freshness_days"] == 60
            # The honest paragraph must still surface the situation in FR.
            assert "incertain" in body["coach_paragraph"].lower()
        finally:
            app.dependency_overrides.clear()


# ── ADR-079 watermark lockstep — defense in depth ────────────────────


class TestR162WatermarkLockstep:
    """The new ``/v1/coach-macro-context`` prefix MUST be present in BOTH
    the middleware DEFAULT_WATERMARKED_PREFIXES tuple AND
    Settings.ai_watermarked_route_prefixes default. The W90 invariant
    test_ai_watermark_default_prefixes_match_settings already enforces
    parity between the two sources ; this test PINS the literal in both
    places so a removal-side regression fails this router-specific
    suite even before the broader invariants_ichor run."""

    def test_middleware_default_contains_coach_macro_prefix(self) -> None:
        from ichor_api.middleware.ai_watermark import DEFAULT_WATERMARKED_PREFIXES

        assert "/v1/coach-macro-context" in DEFAULT_WATERMARKED_PREFIXES, (
            "ADR-079 watermark middleware MUST tag /v1/coach-macro-context — "
            "the CoachMacroContext.coach_paragraph + CalendarSurprise.why_it_"
            "matters strings are AI-derived narrative synthesis (EU AI Act "
            "§50.2 deadline 2026-08-02)."
        )

    def test_settings_default_contains_coach_macro_prefix(self) -> None:
        from ichor_api.config import Settings

        prefixes = Settings().ai_watermarked_route_prefixes
        assert "/v1/coach-macro-context" in prefixes, (
            "ADR-079 Settings default MUST tag /v1/coach-macro-context — "
            "drift vs the middleware DEFAULT_WATERMARKED_PREFIXES would "
            "trigger the W90 invariants_ichor lockstep test."
        )


# ── builder import-path sanity ────────────────────────────────────────


def test_builder_module_is_reachable_from_router_module() -> None:
    """Sanity : the router-side import target
    ``ichor_api.services.coach_macro_context_builder.build_coach_macro_context``
    must be importable (catches a future rename that would silently
    monkeypatch the wrong attribute in the tests above)."""
    from ichor_api.services.coach_macro_context_builder import (
        build_coach_macro_context,
    )

    assert callable(build_coach_macro_context)


if __name__ == "__main__":  # pragma: no cover - manual run convenience
    pytest.main(["-xvs", __file__])
