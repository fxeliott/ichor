"""S02 socle drift guard — ORM ↔ migration `created_at` / TimestampMixin server_default.

`migrations/env.py` configures both autogenerate paths with
`compare_server_default=True` (env.py:52 + :63). When a migration creates a
column WITH `server_default` but the ORM `mapped_column` omits it, the next
`alembic revision --autogenerate` emits a spurious "drop server default" ALTER
op. This is metadata-only drift — the DB and runtime INSERT behaviour are
unaffected (the Python `default`/explicit value still wins at INSERT) — but the
phantom diff pollutes every future migration.

This guard mirrors the per-column pattern of
`test_session_card_scenario_bucket_column.py`. It asserts EXACTLY the columns
aligned in S02 socle round-8 carry an ORM `server_default` (no more, no less),
so the alignment is both documented and locked against regression.

Scope of the alignment (each verified against the backing migration):
  - `created_at` on 16 models whose creation migration sets
    `server_default=sa.func.now()` (or `sa.text("now()")` for trader_notes).
  - `TimestampMixin.created_at` + `.updated_at` on its 4 consumers (migration
    0001 builds both with `server_default=sa.func.now()` for every consumer).

Deliberate NON-alignment is asserted too (negative guards): models whose
migration created `created_at` WITHOUT a server_default, and the
deliberately-nullable snapshot JSONB columns on session_card_audit, MUST keep
`server_default is None`.
"""

from __future__ import annotations

import pytest

# created_at server_default mirrors sa.func.now() in the creation migration.
# (model class name, migration ref) — each confirmed by reading the migration.
_FUNC_NOW_MODELS = [
    ("FxTick", "0020:47"),
    ("PolygonIntradayBar", "0006:32"),
    ("NewsItem", "0002:47"),
    ("Couche2Output", "0009:41"),
    ("MarketDataBar", "0003:35"),
    ("SessionCardAudit", "0005:226"),
    ("CbSpeech", "0005:146"),
    ("ConfluenceHistory", "0007:32"),
    ("CotPosition", "0005:119"),
    ("GdeltEvent", "0005:69"),
    ("GprObservation", "0005:100"),
    ("KalshiMarket", "0005:174"),
    ("ManifoldMarket", "0002:89"),
    ("FredObservation", "0005:48"),
    ("PolygonGexSnapshot", "0008:40"),
    ("PolymarketSnapshot", "0002:89"),
]

# created_at server_default mirrors sa.text("now()") in the creation migration.
_TEXT_NOW_MODELS = [
    ("TraderNote", "0029:61"),
]

# TimestampMixin consumers — migration 0001 builds created_at + updated_at
# WITH server_default=sa.func.now() for every one of these tables.
_TIMESTAMP_MIXIN_CONSUMERS = [
    ("Alert", "0001:56-60"),
    ("Briefing", "0001:29-33"),
    ("BiasSignal", "0001:130-134"),
    ("Prediction", "0001:95-99"),
]

# Negative guards : these models' migrations created created_at WITHOUT a
# server_default — the ORM must NOT introduce one (that would be reverse drift).
_NO_SERVER_DEFAULT_MODELS = [
    ("FinraShortVolume", "0025:36"),
    ("SessionCardCounterfactual", "0022:36"),
]


def _col(model_name: str, col_name: str) -> object:
    import ichor_api.models as models

    model = getattr(models, model_name)
    return {c.name: c for c in model.__table__.columns}[col_name]


@pytest.mark.parametrize("model_name, migration_ref", _FUNC_NOW_MODELS)
def test_created_at_has_func_now_server_default(model_name: str, migration_ref: str) -> None:
    col = _col(model_name, "created_at")
    assert col.server_default is not None, (
        f"{model_name}.created_at must carry an ORM server_default mirroring its "
        f"migration ({migration_ref} sa.func.now()) — None means the "
        "ORM↔migration drift came back (spurious alembic 'drop server default')."
    )
    rendered = str(col.server_default.arg).lower()
    assert "now()" in rendered, (
        f"{model_name}.created_at server_default must render now() ; got {rendered!r}"
    )


@pytest.mark.parametrize("model_name, migration_ref", _TEXT_NOW_MODELS)
def test_created_at_has_text_now_server_default(model_name: str, migration_ref: str) -> None:
    col = _col(model_name, "created_at")
    assert col.server_default is not None, (
        f"{model_name}.created_at must carry an ORM server_default mirroring its "
        f"migration ({migration_ref} sa.text('now()')) — None means drift."
    )
    rendered = str(col.server_default.arg).lower()
    assert "now()" in rendered, (
        f"{model_name}.created_at server_default must render now() ; got {rendered!r}"
    )


@pytest.mark.parametrize("model_name, migration_ref", _TIMESTAMP_MIXIN_CONSUMERS)
@pytest.mark.parametrize("col_name", ["created_at", "updated_at"])
def test_timestamp_mixin_columns_have_server_default(
    model_name: str, migration_ref: str, col_name: str
) -> None:
    col = _col(model_name, col_name)
    assert col.server_default is not None, (
        f"{model_name}.{col_name} (TimestampMixin) must carry an ORM "
        f"server_default mirroring migration {migration_ref} (sa.func.now()). "
        "Every consumer's migration has it, so the shared mixin is safe to align."
    )
    rendered = str(col.server_default.arg).lower()
    assert "now()" in rendered, (
        f"{model_name}.{col_name} server_default must render now() ; got {rendered!r}"
    )


@pytest.mark.parametrize("model_name, migration_ref", _NO_SERVER_DEFAULT_MODELS)
def test_created_at_intentionally_has_no_server_default(
    model_name: str, migration_ref: str
) -> None:
    col = _col(model_name, "created_at")
    assert col.server_default is None, (
        f"{model_name}.created_at must have NO server_default : its migration "
        f"({migration_ref}) created the column without one. Adding it ORM-side "
        "would be reverse drift (spurious alembic 'add server default')."
    )


def test_session_card_audit_snapshot_columns_stay_nullable_no_default() -> None:
    """The deliberately-nullable snapshot JSONB columns on session_card_audit
    keep NO server_default by design (migrations 0050/0055/0056 — NULL carries
    the honest 'not captured at this card's generation' semantic, distinct from
    a '[]' backfill). Documents that the created_at alignment did not touch
    them."""
    for name in (
        "degraded_inputs",
        "confluence_snapshot",
        "theme_snapshot",
        "dollar_snapshot",
        "dimension_votes",
    ):
        col = _col("SessionCardAudit", name)
        assert col.nullable is True, f"{name} must stay nullable (by design)"
        assert col.server_default is None, (
            f"{name} must keep NO server_default — deliberate divergence from "
            "the scenarios/key_levels NOT NULL DEFAULT '[]' columns."
        )
