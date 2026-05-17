"""First unit test for the ADR-097 FRED-liveness CI guard (r92).

The guard (`scripts/ci/fred_liveness_check.py`) shipped r61 but was
NEVER tested and had 2 latent defects (A : imported the registry from
data_pool's heavy SQLAlchemy graph while the workflow installed only
httpx → exit-4 every run ; B : key-absent exit-3 reds the nightly cron
pre-secret). r92 fixed both (registry extracted to the dep-free
`fred_age_registry.py` ; workflow `pip install httpx structlog` +
secret-gate). This test pins:

  1. `_classify_severity` GREEN/YELLOW/RED boundaries (pure fn).
  2. `check_series` 200-ok / 404 / empty-obs / missing-date / http-error
     via httpx MockTransport (mirrors test_bundesbank_bund.py idiom).
  3. `_import_canonical_sources` resolves from the NEW dep-free
     `fred_age_registry` + `merged_series()` and the registry values are
     byte-identical post-extraction (the data_pool re-export regression
     guard — IRLTLT01GBM156N must still be 120, default still 14).
  4. The ADR-097 fail-closed contract is intact : key-absent → exit 3
     (the additive-safe behaviour lives in the workflow, NOT the script).
"""

from __future__ import annotations

import asyncio
import importlib.util
import pathlib
from datetime import date, timedelta

import httpx
import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_SCRIPT = _REPO_ROOT / "scripts" / "ci" / "fred_liveness_check.py"
_spec = importlib.util.spec_from_file_location("fred_liveness_check", _SCRIPT)
assert _spec and _spec.loader
flc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(flc)


# ─── 1. _classify_severity boundaries (pure) ────────────────────────────


@pytest.mark.parametrize(
    ("days_ago", "threshold", "expected"),
    [
        (0, 14, "GREEN"),
        (14, 14, "GREEN"),  # staleness == threshold → GREEN (≤)
        (15, 14, "YELLOW"),  # > threshold
        (28, 14, "YELLOW"),  # == 2× → still YELLOW (≤ 2×)
        (29, 14, "RED"),  # > 2× → RED
        (200, 14, "RED"),  # discontinued-class (China-M1 2019 analogue)
        (0, 120, "GREEN"),  # monthly OECD series, fresh
        (130, 120, "YELLOW"),  # monthly, mildly stale
    ],
)
def test_classify_severity_boundaries(days_ago: int, threshold: int, expected: str) -> None:
    last = (date.today() - timedelta(days=days_ago)).isoformat()
    sev, stale = flc._classify_severity(last, threshold)
    assert sev == expected
    assert stale == days_ago


def test_classify_severity_none_and_bad_date_are_red() -> None:
    assert flc._classify_severity(None, 14) == ("RED", None)
    assert flc._classify_severity("not-a-date", 14) == ("RED", None)


# ─── 2. check_series via httpx MockTransport ────────────────────────────


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_check_series_ok_returns_last_obs_no_severity() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"observations": [{"date": "2026-05-14"}]})

    async with _client(handler) as c:
        r = await flc.check_series(c, "DGS10", "k")
    assert r["series_id"] == "DGS10"
    assert r["api_status"] == 200
    assert r["last_obs_date"] == "2026-05-14"
    assert "severity" not in r  # severity assigned later in main()


@pytest.mark.asyncio
async def test_check_series_http_404_is_red() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "bad series"})

    async with _client(handler) as c:
        r = await flc.check_series(c, "DEADXXX", "k")
    assert r["severity"] == "RED"
    assert r["error"] == "http_404"


@pytest.mark.asyncio
async def test_check_series_empty_observations_is_red() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"observations": []})

    async with _client(handler) as c:
        r = await flc.check_series(c, "X", "k")
    assert r["severity"] == "RED"
    assert r["error"] == "empty_observations"


@pytest.mark.asyncio
async def test_check_series_missing_date_field_is_red() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"observations": [{"value": "1.0"}]})

    async with _client(handler) as c:
        r = await flc.check_series(c, "X", "k")
    assert r["severity"] == "RED"
    assert r["error"] == "missing_date_field"


@pytest.mark.asyncio
async def test_check_series_transport_error_is_red() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    async with _client(handler) as c:
        r = await flc.check_series(c, "X", "k")
    assert r["severity"] == "RED"
    assert r["error"].startswith("http_error")


# ─── 3. canonical-source import (byte-identical registry guard) ─────────


def test_import_canonical_sources_resolves_from_dep_free_registry() -> None:
    """Defect-A regression guard : the script must resolve the series
    tuple + registry WITHOUT data_pool's heavy graph, and the extracted
    registry values must be byte-identical to the pre-r92 inline dict."""
    series, registry, default_days = flc._import_canonical_sources()
    assert isinstance(series, tuple) and len(series) > 20
    assert "DGS10" in series  # base SERIES_TO_POLL merged in
    # Byte-identical extraction pins (the r92 data_pool re-export must
    # not have changed any value) :
    assert registry["IRLTLT01GBM156N"] == 120  # UK 10y monthly (r90)
    assert registry["MYAGM1CNM189N"] == 60  # China M1 monthly (r46)
    assert registry["USREC"] == 365
    assert default_days == 14  # _FRED_DEFAULT_MAX_AGE_DAYS unchanged

    # And the data_pool re-export is the SAME object (zero-diff backward
    # compat — _max_age_days_for / _latest_fred stay byte-identical).
    from ichor_api.services import data_pool, fred_age_registry

    assert data_pool._FRED_SERIES_MAX_AGE_DAYS is fred_age_registry.FRED_SERIES_MAX_AGE_DAYS
    assert data_pool._FRED_DEFAULT_MAX_AGE_DAYS == fred_age_registry.FRED_DEFAULT_MAX_AGE_DAYS


# ─── 4. ADR-097 fail-closed contract intact (script unchanged) ──────────


def test_key_absent_returns_exit_3_failclosed(monkeypatch) -> None:
    """ADR-097 fail-closed : no ICHOR_CI_FRED_API_KEY → exit 3, BEFORE
    any network. The additive-safe skip is the WORKFLOW's job (secret-
    gate step), NOT a weakening of the script's contract (r92 decision)."""
    monkeypatch.delenv("ICHOR_CI_FRED_API_KEY", raising=False)
    rc = asyncio.run(flc.main())
    assert rc == 3
