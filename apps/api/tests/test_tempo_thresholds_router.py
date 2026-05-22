"""r126 ADR-099 §Impl(r126) — /v1/tempo-thresholds router contract tests.

Validates :
  - GET /v1/tempo-thresholds → 200 + per-asset latest only
  - GET /v1/tempo-thresholds/{asset} → 200 happy / 400 unknown / 404 absent
  - Response shape (Pydantic) matches what the r127 frontend will consume
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from ichor_api.db import get_session
from ichor_api.main import app


class _StubResult:
    """Mimic SQLAlchemy `Result.scalars().all()` / `.scalar_one_or_none()`."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalars(self) -> _StubResult:
        return self

    def all(self) -> list[Any]:
        return list(self._rows)

    def scalar_one_or_none(self) -> Any | None:
        return self._rows[0] if self._rows else None


class _StubSession:
    """AsyncSession stub. `route_router` decides which rows to return based
    on the stmt — for these tests, just return whatever was set."""

    def __init__(self) -> None:
        self.rows: list[Any] = []
        self.statements: list[Any] = []

    def set_rows(self, rows: list[Any]) -> None:
        self.rows = rows

    async def execute(self, stmt: Any, params: Any = None) -> _StubResult:  # noqa: ARG002
        self.statements.append(stmt)
        return _StubResult(self.rows)


def _make_row(
    asset: str = "EUR_USD",
    breakout: float = 59.10,
    active: float = 54.20,
    trending: float = 47.20,
    range_bound: float = 31.70,
    sample: int = 60,
    window: int = 90,
    computed_at: datetime | None = None,
) -> SimpleNamespace:
    """Mirror the shape of a `TempoThreshold` ORM row for the
    `_to_out` mapper. The router reads only the listed attributes ; we
    don't carry an `id` because the router output schema doesn't surface it."""
    return SimpleNamespace(
        asset=asset,
        breakout_bp=Decimal(str(breakout)),
        active_bp=Decimal(str(active)),
        trending_bp=Decimal(str(trending)),
        range_bound_bp=Decimal(str(range_bound)),
        sample_size=sample,
        window_days=window,
        computed_at=computed_at or datetime(2026, 5, 20, 4, 5, tzinfo=UTC),
    )


@pytest.fixture
def stub_session() -> _StubSession:
    return _StubSession()


@pytest.fixture
def client(stub_session: _StubSession) -> TestClient:
    async def _override():
        yield stub_session

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)


# ─────────────── GET /v1/tempo-thresholds (list) ────────────────


def test_list_returns_items_wrapper(client: TestClient, stub_session: _StubSession) -> None:
    """Happy path — 2 rows return as items[]."""
    stub_session.set_rows(
        [
            _make_row(asset="EUR_USD", breakout=59.10, range_bound=31.70),
            _make_row(asset="GBP_USD", breakout=95.80, range_bound=41.60),
        ]
    )
    r = client.get("/v1/tempo-thresholds")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert len(body["items"]) == 2
    assets = {item["asset"] for item in body["items"]}
    assert assets == {"EUR_USD", "GBP_USD"}


def test_list_empty_returns_empty_items(client: TestClient, stub_session: _StubSession) -> None:
    """When the cron hasn't fired yet, the endpoint returns
    {"items": []} — never crashes (data-honesty per ADR-104)."""
    stub_session.set_rows([])
    r = client.get("/v1/tempo-thresholds")
    assert r.status_code == 200
    assert r.json() == {"items": []}


def test_list_item_shape_matches_pydantic_schema(
    client: TestClient, stub_session: _StubSession
) -> None:
    """Schema contract — r127 frontend fetcher will rely on these keys."""
    stub_session.set_rows([_make_row(asset="EUR_USD", sample=60, window=90)])
    r = client.get("/v1/tempo-thresholds")
    assert r.status_code == 200
    item = r.json()["items"][0]
    assert set(item.keys()) == {
        "asset",
        "breakout_bp",
        "active_bp",
        "trending_bp",
        "range_bound_bp",
        "sample_size",
        "window_days",
        "computed_at",
    }
    assert isinstance(item["breakout_bp"], float)
    assert isinstance(item["sample_size"], int)
    assert item["window_days"] == 90


# ─────────────── GET /v1/tempo-thresholds/{asset} ────────────────


def test_get_one_happy_path(client: TestClient, stub_session: _StubSession) -> None:
    stub_session.set_rows([_make_row(asset="EUR_USD")])
    r = client.get("/v1/tempo-thresholds/EUR_USD")
    assert r.status_code == 200
    body = r.json()
    assert body["asset"] == "EUR_USD"


def test_get_one_normalizes_dash_to_underscore(
    client: TestClient, stub_session: _StubSession
) -> None:
    """`EUR-USD` → `EUR_USD` normalization (matches existing asset routers)."""
    stub_session.set_rows([_make_row(asset="EUR_USD")])
    r = client.get("/v1/tempo-thresholds/EUR-USD")
    assert r.status_code == 200
    assert r.json()["asset"] == "EUR_USD"


def test_get_one_lowercases_input(client: TestClient, stub_session: _StubSession) -> None:
    """`eur_usd` → `EUR_USD` normalization (idempotent for canonical asset code)."""
    stub_session.set_rows([_make_row(asset="EUR_USD")])
    r = client.get("/v1/tempo-thresholds/eur_usd")
    assert r.status_code == 200


def test_get_one_returns_404_when_asset_known_but_no_row(
    client: TestClient, stub_session: _StubSession
) -> None:
    """Asset is in DEFAULT_RECALIBRATION_ASSETS but has no row yet (cron
    didn't fire / sample too small) → 404 with helpful message."""
    stub_session.set_rows([])  # No row.
    r = client.get("/v1/tempo-thresholds/EUR_USD")
    assert r.status_code == 404
    assert "EUR_USD" in r.json()["detail"]


def test_get_one_rejects_unknown_asset_with_400(
    client: TestClient,
    stub_session: _StubSession,  # noqa: ARG001
) -> None:
    """Asset not in the canonical universe → 400 (NOT 404 — distinguishes
    `client-side bad input` from `valid asset no data yet`)."""
    r = client.get("/v1/tempo-thresholds/NOT_A_REAL_ASSET")
    assert r.status_code == 400
    assert "NOT_A_REAL_ASSET" in r.json()["detail"]


def test_get_one_accepts_usd_cad_forward_compat(
    client: TestClient, stub_session: _StubSession
) -> None:
    """ADR-083 D1 6th asset is accepted as a valid code even before its
    /briefing/[asset] route ships — the recalibration cron may have
    persisted a row for it once added to DEFAULT_RECALIBRATION_ASSETS."""
    stub_session.set_rows([_make_row(asset="USD_CAD")])
    r = client.get("/v1/tempo-thresholds/USD_CAD")
    assert r.status_code == 200


def test_list_response_sets_cache_control(client: TestClient, stub_session: _StubSession) -> None:
    """Concordant YELLOW (api-designer + code-reviewer) — 5-min public
    cache + 15-min stale-while-revalidate hint for downstream CDN /
    Next.js fetch. Pins the contract."""
    stub_session.set_rows([_make_row(asset="EUR_USD")])
    r = client.get("/v1/tempo-thresholds")
    assert r.status_code == 200
    assert r.headers.get("cache-control") == ("public, max-age=300, stale-while-revalidate=900")


def test_get_one_response_sets_cache_control(
    client: TestClient, stub_session: _StubSession
) -> None:
    stub_session.set_rows([_make_row(asset="EUR_USD")])
    r = client.get("/v1/tempo-thresholds/EUR_USD")
    assert r.status_code == 200
    assert r.headers.get("cache-control") == ("public, max-age=300, stale-while-revalidate=900")


def test_get_one_xau_value_round_trip(client: TestClient, stub_session: _StubSession) -> None:
    """XAU sits at the high end of the bp scale — make sure the
    Decimal → float conversion handles 3-digit bp values cleanly."""
    stub_session.set_rows(
        [
            _make_row(
                asset="XAU_USD",
                breakout=307.40,
                active=273.70,
                trending=177.20,
                range_bound=140.00,
            )
        ]
    )
    r = client.get("/v1/tempo-thresholds/XAU_USD")
    assert r.status_code == 200
    body = r.json()
    assert body["breakout_bp"] == pytest.approx(307.40)
    assert body["range_bound_bp"] == pytest.approx(140.00)
