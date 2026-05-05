"""Cheap sanity tests : the FastAPI app imports cleanly + the new
routes (Wave 1.1, 1.4, 1.5, 4.5) are registered with the right path
prefixes. Catches __init__.py drift, missing imports, name collisions.

These tests run BEFORE any DB-dependent integration tests so a broken
import surfaces immediately as a red CI on apps/api (pytest blocking).
"""

from __future__ import annotations


def test_main_module_imports_without_error() -> None:
    """Importing `ichor_api.main` triggers router registration. Must
    succeed without raising (no missing exports, no circular imports)."""
    from ichor_api import main  # noqa: F401


def test_all_expected_routers_in_init() -> None:
    """Wave 1 added `divergence_router`, `yield_curve_router`,
    `sources_router` to `routers/__init__.py`. Make sure they're
    exported."""
    from ichor_api import routers as r

    expected = {
        "divergence_router",
        "sources_router",
        "yield_curve_router",
        "today_router",
        "scenarios_router",
        "sessions_router",
        "macro_pulse_router",
    }
    actual = set(getattr(r, "__all__", []))
    missing = expected - actual
    assert not missing, f"missing exports in routers/__init__.py: {missing}"


def test_new_routes_registered_in_app() -> None:
    """The 3 routes added in this audit pass must be reachable on the app."""
    from ichor_api.main import app

    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
    expected = {
        "/v1/divergences",
        "/v1/yield-curve",
        "/v1/sources",
        "/v1/macro-pulse/heatmap",
        "/v1/sessions/{asset}/scenarios",
    }
    missing = expected - paths
    assert not missing, f"routes missing from app: {missing}"


def test_fx_tick_model_exported() -> None:
    """Wave 2.2 added `FxTick` to models. Check it's importable + on the
    `Base.metadata` so Alembic autogenerate sees it."""
    from ichor_api.models import Base, FxTick

    assert FxTick.__tablename__ == "fx_ticks"
    assert "fx_ticks" in Base.metadata.tables


def test_session_card_out_has_typed_enrichment_fields() -> None:
    """Phase 2 added optional thesis/trade_plan/ideas/confluence_drivers/
    calibration. They must remain in the schema."""
    from ichor_api.schemas import SessionCardOut

    fields = SessionCardOut.model_fields
    assert "thesis" in fields
    assert "trade_plan" in fields
    assert "ideas" in fields
    assert "confluence_drivers" in fields
    assert "calibration" in fields


def test_session_card_out_from_orm_row_classmethod_present() -> None:
    """Wave 4.1 added the classmethod constructor. Used by routers/sessions.py."""
    from ichor_api.schemas import SessionCardOut

    assert hasattr(SessionCardOut, "from_orm_row")
    assert callable(SessionCardOut.from_orm_row)


def test_extractors_are_importable_from_schemas() -> None:
    """The 5 extractors must be public (callers in today.py + sessions.py)."""
    from ichor_api.schemas import (
        extract_calibration_stat,
        extract_confluence_drivers,
        extract_ideas,
        extract_thesis,
        extract_trade_plan,
    )

    for fn in (
        extract_thesis,
        extract_trade_plan,
        extract_ideas,
        extract_confluence_drivers,
        extract_calibration_stat,
    ):
        assert callable(fn)


def test_feature_flags_subscriber_helpers_importable() -> None:
    """Wave 6.2 added Redis pub/sub. `lifespan` calls these names."""
    from ichor_api.services.feature_flags import (
        start_invalidation_subscriber,
        stop_invalidation_subscriber,
    )

    assert callable(start_invalidation_subscriber)
    assert callable(stop_invalidation_subscriber)


def test_cross_asset_heatmap_service_importable() -> None:
    from ichor_api.services.cross_asset_heatmap import (
        CrossAssetHeatmap,
        HeatmapCell,
        HeatmapRow,
        assess_cross_asset_heatmap,
    )

    assert callable(assess_cross_asset_heatmap)
    # Dataclasses present
    cell = HeatmapCell(sym="X", value=None, bias="neutral", unit="%")
    row = HeatmapRow(row="r", cells=[cell])
    assert row.cells[0].sym == "X"
    _ = CrossAssetHeatmap  # ensure name exists


def test_polygon_fx_stream_module_imports_without_websocket_present() -> None:
    """The collector module wraps the websockets import in a clear error.
    Even if the dep isn't installed, the import error path must be
    explicit, not a generic ModuleNotFoundError lost in the stack."""
    import importlib

    try:
        mod = importlib.import_module("ichor_api.collectors.polygon_fx_stream")
        assert hasattr(mod, "stream_forever")
        assert hasattr(mod, "DEFAULT_PAIRS")
    except ImportError as exc:
        # The friendly error from the module's try/except.
        assert "websockets" in str(exc)
