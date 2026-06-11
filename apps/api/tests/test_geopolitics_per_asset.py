"""Tests for the S04 TIER-2 #3 per-asset geopolitics section.

`data_pool._section_geopolitics(session, asset)` must narrow the GDELT
negative-event cluster to the asset's conversation (mirroring the
/v1/geopolitics/briefing router), while AI-GPR stays the GLOBAL index.
No DB: an ordered AsyncSession stub (call 0 = GPR .first(), call 1 = GDELT
.all()) mirrors the project's geopolitics-router test pattern.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from ichor_api.services.adr017_filter import is_adr017_clean
from ichor_api.services.data_pool import _section_geopolitics

_TODAY = datetime.now(UTC).date()


def _gdelt(idx: int, title: str, tone: float, *, query_label: str = "global") -> SimpleNamespace:
    return SimpleNamespace(
        seendate=datetime(2026, 6, 8, 18, 0, tzinfo=UTC),
        tone=tone,
        title=title,
        domain="example.com",
        query_label=query_label,
        url=f"https://example.com/{idx}",
    )


def _gpr(value: float = 180.0, obs: date | None = None) -> SimpleNamespace:
    return SimpleNamespace(ai_gpr=value, observation_date=obs or _TODAY)


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        rows = self._rows

        class _S:
            def all(self):
                return list(rows)

            def first(self):
                return rows[0] if rows else None

        return _S()


def _session(*, gpr: SimpleNamespace | None, gdelt: list[SimpleNamespace]):
    """Ordered stub: execute call 0 = GPR, call 1 = GDELT."""
    state = {"i": 0}

    async def _execute(stmt, *a, **kw):
        i = state["i"]
        state["i"] += 1
        if i == 0:
            return _RowsResult([gpr] if gpr is not None else [])
        return _RowsResult(gdelt)

    s = AsyncMock()
    s.execute = AsyncMock(side_effect=_execute)
    return s


# Mixed pool: 3 EUR-affinity, 3 XAU-affinity, 1 generic.
def _mixed_pool() -> list[SimpleNamespace]:
    return [
        _gdelt(1, "ECB holds rates steady", -3.0, query_label="ecb-policy"),
        _gdelt(2, "Lagarde signals caution", -2.5, query_label="ecb-policy"),
        _gdelt(3, "eurozone PMI contracts", -1.5, query_label="ez-macro"),
        _gdelt(4, "gold reserves bullion bid surges", -4.0, query_label="metals"),
        _gdelt(5, "spot metals desk sees inflows", -2.0, query_label="metals"),
        _gdelt(6, "XAUUSD intraday squeeze", -1.0, query_label="metals"),
        _gdelt(7, "Generic market chatter", -3.5, query_label="global"),
    ]


async def test_geopolitics_differs_per_asset() -> None:
    """The whole point: EUR_USD and XAU_USD must NOT get the same GDELT block."""
    eur_md, _, _ = await _section_geopolitics(_session(gpr=_gpr(), gdelt=_mixed_pool()), "EUR_USD")
    xau_md, _, _ = await _section_geopolitics(_session(gpr=_gpr(), gdelt=_mixed_pool()), "XAU_USD")
    assert eur_md != xau_md
    # EUR card surfaces ECB/Lagarde/eurozone, not the gold stories.
    assert "ECB" in eur_md and "Lagarde" in eur_md
    assert "bullion" not in eur_md and "XAUUSD" not in eur_md
    # XAU card surfaces gold/bullion/XAUUSD, not the ECB stories.
    assert "bullion" in xau_md or "spot metals" in xau_md or "XAUUSD" in xau_md
    assert "ECB" not in xau_md and "Lagarde" not in xau_md


async def test_geopolitics_applied_header_and_adr017() -> None:
    md, sources, degraded = await _section_geopolitics(
        _session(gpr=_gpr(), gdelt=_mixed_pool()), "EUR_USD"
    )
    assert "ticker-linked to EUR_USD" in md
    assert degraded == []  # GPR fresh
    assert sources  # event URLs cited
    assert is_adr017_clean(md)


async def test_geopolitics_scarce_fallback_to_global() -> None:
    # Only generic events → 0 EUR matches < 3 → fall back to global ranking.
    pool = [_gdelt(i, f"Generic story {i}", -float(i)) for i in range(1, 5)]
    md, _, _ = await _section_geopolitics(_session(gpr=_gpr(), gdelt=pool), "EUR_USD")
    assert "match scarce" in md
    assert "matched=0" in md
    # Global fallback still surfaces the most-negative event.
    assert "Generic story 4" in md


async def test_geopolitics_gpr_is_global_unaffected_by_asset() -> None:
    pool = _mixed_pool()
    eur_md, _, _ = await _section_geopolitics(_session(gpr=_gpr(220.0), gdelt=pool), "EUR_USD")
    xau_md, _, _ = await _section_geopolitics(_session(gpr=_gpr(220.0), gdelt=pool), "XAU_USD")
    assert "AI-GPR = 220.0" in eur_md
    assert "AI-GPR = 220.0" in xau_md  # single-index doctrine: identical for both


async def test_geopolitics_no_asset_is_global_backcompat() -> None:
    md, _, _ = await _section_geopolitics(_session(gpr=_gpr(), gdelt=_mixed_pool()), None)
    assert "GDELT 5 most-negative events last 24h:" in md  # no per-asset suffix
    assert "ticker-linked" not in md
    assert "match scarce" not in md


async def test_geopolitics_no_events() -> None:
    md, _, _ = await _section_geopolitics(_session(gpr=_gpr(), gdelt=[]), "EUR_USD")
    assert "GDELT: no events in the last 24h" in md


async def test_geopolitics_gpr_absent_is_degraded() -> None:
    md, _, degraded = await _section_geopolitics(_session(gpr=None, gdelt=_mixed_pool()), "EUR_USD")
    assert len(degraded) == 1
    assert degraded[0].series_id == "AI-GPR"
    assert degraded[0].status == "absent"
    assert "AI-GPR ABSENT" in md


def test_geo_candidate_pool_parity_brain_vs_router() -> None:
    """Brain↔panel parity lockstep (S04 TIER-2 #3): the data_pool section and
    the /v1/geopolitics/briefing router must draw the SAME candidate pool for
    the router's default top=5, or the brain's card and the frontend panel
    silently diverge on which events qualify as the asset's conversation."""
    from ichor_api.routers.geopolitics import (
        _FILTER_FETCH_MULTIPLIER,
        _FILTER_MAX_FETCH,
        _MIN_ASSET_MATCHES,
    )
    from ichor_api.services.data_pool import _GEO_GDELT_POOL

    router_default_top = 5  # Query(5, ...) default in routers/geopolitics.briefing
    router_pool = min(
        _FILTER_MAX_FETCH,
        max(router_default_top * _FILTER_FETCH_MULTIPLIER, _MIN_ASSET_MATCHES * 8),
    )
    assert _GEO_GDELT_POOL == router_pool


def test_geo_candidate_pool_wide_enough_for_low_share_assets() -> None:
    """Pin the 2026-06-11 widening (40 → 400). The pool is the whole-window
    most-negative ranking; prod witness on a 2,387-event/24h window showed the
    40-cap structurally starves low-share-of-voice assets (XAU matched 0
    despite 403 gold rows; GBP 0; SPX 1 → systematic global fallback), while
    400 gives 5/5 assets margin (XAU 48, GBP 9, SPX 11). Shrinking this back
    re-opens the S04 'identical geopolitics block for all assets' gap."""
    from ichor_api.services.data_pool import _GEO_GDELT_POOL

    assert _GEO_GDELT_POOL == 400
