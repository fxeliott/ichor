"""Verify the SessionCardCounterfactual ORM model is properly exported
and bound to the migration 0022 table.
"""

from __future__ import annotations

from ichor_api.models import SessionCardCounterfactual


def test_model_exported_via_models_dunder_all() -> None:
    from ichor_api import models

    assert "SessionCardCounterfactual" in models.__all__


def test_table_name_matches_migration() -> None:
    assert SessionCardCounterfactual.__tablename__ == "session_card_counterfactuals"


def test_model_has_required_columns() -> None:
    cols = SessionCardCounterfactual.__table__.columns
    required = {
        "id",
        "asked_at",
        "created_at",
        "session_card_id",
        "asset",
        "scrubbed_event",
        "original_bias",
        "original_conviction_pct",
        "counterfactual_bias",
        "counterfactual_conviction_pct",
        "delta_narrative",
        "new_dominant_drivers",
        "confidence_delta",
        "robustness_score",
        "model_used",
        "duration_ms",
    }
    actual = {c.name for c in cols}
    missing = required - actual
    assert not missing, f"missing columns: {missing}"


def test_composite_primary_key_id_and_asked_at() -> None:
    pk_cols = {c.name for c in SessionCardCounterfactual.__table__.primary_key.columns}
    assert pk_cols == {"id", "asked_at"}
