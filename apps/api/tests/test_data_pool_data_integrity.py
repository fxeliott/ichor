"""Unit tests for the ADR-103 runtime FRED-liveness degraded-data surface
(round-93, ADR-099 §T3.2 "human-visible degraded-data alert — break the
silent-skip chain").

Covers:
  1. `_fred_liveness` fresh/stale/absent classification + the
     byte-consistency boundary invariant (its `fresh` boundary is the
     same `age <= max_age` ⟺ `_latest_fred` `>= cutoff` predicate).
  2. `_section_data_integrity` is ALWAYS rendered (never the `("", [])`
     sentinel) — including for an asset with no per-asset anchor map.
  3. The AUD China-M1 dead-series real scenario (ADR-093 §r49) surfaces
     explicitly instead of silently dropping.
  4. Class-A asset-gating skips are NEVER counted as degraded (the audit
     inspects FRED anchors, not section asset-gates).
  5. ADR-017 boundary preserved on both ALL-FRESH and DEGRADED renders.
  6. macro-core/per-asset dedup (VIXCLS in both for SPX → audited once).
  7. The critical-anchor registry shape (series_ids verified, not guessed).

Mocks `_fred_liveness` for the section tests (canned verdict per series)
and a stubbed AsyncSession for the `_fred_liveness` query-logic tests.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from ichor_api.services.adr017_filter import is_adr017_clean
from ichor_api.services.data_pool import (
    _ASSET_CRITICAL_ANCHORS,
    _MACRO_CORE_ANCHORS,
    DegradedInput,
    FredLiveness,
    _fred_liveness,
    _section_data_integrity,
)

_TODAY = datetime.now(UTC).date()


# ─────────────────────── _fred_liveness logic ──────────────────────────


def _session_returning(latest: date | None) -> AsyncMock:
    """AsyncSession stub whose `(await execute(...)).scalars().first()`
    yields `latest` (a date) or None (no row → absent)."""
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.first.return_value = latest
    session.execute.return_value = result
    return session


@pytest.mark.asyncio
async def test_fred_liveness_absent_when_no_row() -> None:
    """No non-null observation ever ingested → status=absent, all
    metadata None, max_age still resolved (from the override here)."""
    session = _session_returning(None)
    lv = await _fred_liveness(session, "MYAGM1CNM189N", override=60)
    assert lv == FredLiveness("MYAGM1CNM189N", "absent", None, None, 60)


@pytest.mark.asyncio
async def test_fred_liveness_fresh_within_max_age() -> None:
    """Latest obs within max-age → fresh, age computed, date carried."""
    latest = _TODAY - timedelta(days=5)
    session = _session_returning(latest)
    lv = await _fred_liveness(session, "DGS10", override=14)
    assert lv.status == "fresh"
    assert lv.series_id == "DGS10"
    assert lv.latest_date == latest
    assert lv.age_days == 5
    assert lv.max_age_days == 14


@pytest.mark.asyncio
async def test_fred_liveness_stale_beyond_max_age() -> None:
    """Latest obs OLDER than max-age → stale (the China-M1 class : the
    series exists but is years old — `_latest_fred` would return None,
    indistinguishable from absent ; THIS makes the distinction)."""
    latest = date(2019, 8, 1)  # the real MYAGM1CNM189N last obs (ADR-093 §r49)
    session = _session_returning(latest)
    lv = await _fred_liveness(session, "MYAGM1CNM189N", override=60)
    assert lv.status == "stale"
    assert lv.latest_date == date(2019, 8, 1)
    assert lv.age_days == (_TODAY - date(2019, 8, 1)).days
    assert lv.age_days > 60
    assert lv.max_age_days == 60


@pytest.mark.asyncio
async def test_fred_liveness_boundary_is_inclusive_like_latest_fred() -> None:
    """Byte-consistency invariant : `_latest_fred` uses
    `observation_date >= today - max_age` (a row exactly at the cutoff
    is INCLUDED). So age == max_age MUST classify `fresh`, and
    age == max_age + 1 MUST classify `stale` — the exact same boundary."""
    on_cutoff = _TODAY - timedelta(days=14)
    one_past = _TODAY - timedelta(days=15)
    lv_on = await _fred_liveness(_session_returning(on_cutoff), "DGS10", override=14)
    lv_past = await _fred_liveness(_session_returning(one_past), "DGS10", override=14)
    assert lv_on.status == "fresh"  # age 14 <= 14  (⟺ obs_date >= cutoff)
    assert lv_past.status == "stale"  # age 15 > 14  (⟺ obs_date <  cutoff)


# ─────────────────────── registry shape (R59-verified) ─────────────────


def test_critical_anchor_registry_shape() -> None:
    """The registry encodes the verified per-asset primary anchors +
    the ADR-093 AUD composite sub-drivers (incl. the dead China-M1).
    EUR_USD intentionally absent (its Bund anchor is NON-FRED — ADR-103
    §Negative)."""
    macro_ids = {a.series_id for a in _MACRO_CORE_ANCHORS}
    assert macro_ids == {
        "VIXCLS",
        "BAMLH0A0HYM2",
        "NFCI",
        "USALOLITOAASTSAM",
        "EXPINF1YR",
        "THREEFYTP10",
    }
    assert {a.series_id for a in _ASSET_CRITICAL_ANCHORS["XAU_USD"]} == {"DFII10"}
    assert {a.series_id for a in _ASSET_CRITICAL_ANCHORS["NAS100_USD"]} == {"DGS10"}
    assert {a.series_id for a in _ASSET_CRITICAL_ANCHORS["SPX500_USD"]} == {"VIXCLS"}
    assert {a.series_id for a in _ASSET_CRITICAL_ANCHORS["USD_JPY"]} == {"IRLTLT01JPM156N"}
    assert {a.series_id for a in _ASSET_CRITICAL_ANCHORS["GBP_USD"]} == {"IRLTLT01GBM156N"}
    aud_ids = {a.series_id for a in _ASSET_CRITICAL_ANCHORS["AUD_USD"]}
    assert aud_ids == {"IRLTLT01AUM156N", "MYAGM1CNM189N", "PIORECRUSDM", "PCOPPUSDM"}
    assert "EUR_USD" not in _ASSET_CRITICAL_ANCHORS
    # VIXCLS uses the @7 override the consuming sections actually pass.
    vix_macro = next(a for a in _MACRO_CORE_ANCHORS if a.series_id == "VIXCLS")
    assert vix_macro.max_age_override == 7


# ─────────────────────── _section_data_integrity ──────────────────────


def _liveness_stub(verdicts: dict[str, FredLiveness]):
    """Replacement for `_fred_liveness` returning a canned verdict per
    series_id (defaults to fresh@today-1 for any series not listed)."""

    async def _stub(session, series_id, *, override=None):
        if series_id in verdicts:
            return verdicts[series_id]
        return FredLiveness(series_id, "fresh", _TODAY - timedelta(days=1), 1, override or 14)

    return _stub


@pytest.mark.asyncio
async def test_section_always_renders_all_fresh(monkeypatch) -> None:
    """ALWAYS-rendered (key_levels doctrine) : all anchors fresh →
    non-empty md, `ALL FRESH` status, fresh source-stamps, degraded=[]"""
    monkeypatch.setattr("ichor_api.services.data_pool._fred_liveness", _liveness_stub({}))
    md, sources, degraded = await _section_data_integrity(AsyncMock(), "GBP_USD")
    assert md.startswith("## Data integrity — FRED critical-anchor liveness (ADR-103)")
    assert "Status : ALL FRESH" in md
    assert degraded == []
    assert sources  # fresh anchors are source-stamped
    assert all(s.startswith("FRED:") for s in sources)


@pytest.mark.asyncio
async def test_section_always_renders_for_asset_without_per_asset_map(monkeypatch) -> None:
    """USD_CAD has no `_ASSET_CRITICAL_ANCHORS` entry → the section
    STILL renders (macro-core only) — never the ("", []) sentinel.
    This is the silent-skip chain broken : no critical input vanishes
    without a trace, even for a non-priority asset."""
    monkeypatch.setattr("ichor_api.services.data_pool._fred_liveness", _liveness_stub({}))
    md, sources, degraded = await _section_data_integrity(AsyncMock(), "USD_CAD")
    assert md  # non-empty — always rendered
    assert "Status : ALL FRESH" in md
    assert degraded == []
    # Exactly the 6 macro-core anchors audited (no per-asset anchors).
    assert len(sources) == len(_MACRO_CORE_ANCHORS)


@pytest.mark.asyncio
async def test_aud_china_m1_dead_series_surfaces_explicitly(monkeypatch) -> None:
    """The real ADR-093 §r49 scenario : China-M1 MYAGM1CNM189N dead
    since 2019-08-01. Pre-r93 it silently dropped the AUD composite
    driver with ZERO trace. Now it surfaces explicitly as STALE with
    the impacted driver named — the silent-skip chain broken."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._fred_liveness",
        _liveness_stub(
            {
                "MYAGM1CNM189N": FredLiveness(
                    "MYAGM1CNM189N",
                    "stale",
                    date(2019, 8, 1),
                    (_TODAY - date(2019, 8, 1)).days,
                    60,
                )
            }
        ),
    )
    md, sources, degraded = await _section_data_integrity(AsyncMock(), "AUD_USD")
    assert "Status : ⚠️ DEGRADED" in md
    assert "1 of " in md
    assert "**MYAGM1CNM189N** — STALE (latest obs 2019-08-01" in md
    assert "China-credit driver (ADR-093 composite)" in md
    assert "ADR-017 boundary" in md  # the data-provenance boundary note
    assert len(degraded) == 1
    d = degraded[0]
    assert isinstance(d, DegradedInput)
    assert d.series_id == "MYAGM1CNM189N"
    assert d.status == "stale"
    assert d.latest_date == date(2019, 8, 1)
    assert "China-credit" in d.impacted
    # The dead series is NOT source-stamped (no valid provenance) ; the
    # still-fresh AUD anchors ARE.
    assert not any("MYAGM1CNM189N" in s for s in sources)
    assert any("IRLTLT01AUM156N" in s for s in sources)


@pytest.mark.asyncio
async def test_absent_anchor_surfaces_explicitly(monkeypatch) -> None:
    """An absent primary anchor (collector never ran) surfaces as
    ABSENT with the impacted section named — not a vanished section."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._fred_liveness",
        _liveness_stub(
            {"IRLTLT01GBM156N": FredLiveness("IRLTLT01GBM156N", "absent", None, None, 120)}
        ),
    )
    md, _, degraded = await _section_data_integrity(AsyncMock(), "GBP_USD")
    assert "Status : ⚠️ DEGRADED" in md
    assert "**IRLTLT01GBM156N** — ABSENT (no observation ever ingested)" in md
    assert "gbp_specific section (primary UK anchor)" in md
    assert degraded[0].status == "absent"
    assert degraded[0].latest_date is None


@pytest.mark.asyncio
async def test_class_a_asset_gating_never_counted_degraded(monkeypatch) -> None:
    """An asset whose per-asset section is asset-gated OUT (Class-A skip,
    e.g. USD_CAD has no _section_*_specific) but whose macro-core anchors
    are all fresh → ZERO degraded. The audit inspects FRED anchors, NOT
    section asset-gates, so a correct asset-gate skip is never a false
    'degraded' (the exact Class-A/Class-B distinction from R59)."""
    monkeypatch.setattr("ichor_api.services.data_pool._fred_liveness", _liveness_stub({}))
    _, _, degraded = await _section_data_integrity(AsyncMock(), "USD_CAD")
    assert degraded == []


@pytest.mark.asyncio
async def test_spx_dedups_vixcls_macro_core_and_per_asset(monkeypatch) -> None:
    """SPX500_USD has VIXCLS in BOTH macro-core and its per-asset map
    (same @7 override) → audited ONCE (deduped by series_id). The
    rendered fresh list must not list VIXCLS twice."""
    monkeypatch.setattr("ichor_api.services.data_pool._fred_liveness", _liveness_stub({}))
    md, sources, _ = await _section_data_integrity(AsyncMock(), "SPX500_USD")
    assert sum(1 for s in sources if s.startswith("FRED:VIXCLS@")) == 1
    # 6 macro-core ; SPX adds only VIXCLS which dedups away → still 6.
    assert len(sources) == len(_MACRO_CORE_ANCHORS)


@pytest.mark.asyncio
@pytest.mark.parametrize("asset", ["GBP_USD", "AUD_USD", "USD_CAD", "XAU_USD"])
async def test_adr017_clean_all_fresh(monkeypatch, asset: str) -> None:
    """ADR-017 boundary : the ALL-FRESH render is data-provenance only,
    no BUY/SELL/directional vocabulary."""
    monkeypatch.setattr("ichor_api.services.data_pool._fred_liveness", _liveness_stub({}))
    md, _, _ = await _section_data_integrity(AsyncMock(), asset)
    assert is_adr017_clean(md), f"ADR-017 violation in ALL-FRESH render for {asset}"


@pytest.mark.asyncio
async def test_adr017_clean_degraded(monkeypatch) -> None:
    """ADR-017 boundary : the DEGRADED render (incl. the boundary note)
    is still data-provenance only — no BUY/SELL leakage."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._fred_liveness",
        _liveness_stub(
            {
                "MYAGM1CNM189N": FredLiveness("MYAGM1CNM189N", "stale", date(2019, 8, 1), 2000, 60),
                "PIORECRUSDM": FredLiveness("PIORECRUSDM", "absent", None, None, 60),
            }
        ),
    )
    md, _, degraded = await _section_data_integrity(AsyncMock(), "AUD_USD")
    assert is_adr017_clean(md), "ADR-017 violation in DEGRADED render"
    assert len(degraded) == 2


# ───────────── r94 iron/copper registry recalibration proof ────────────
# ADR-092 §Round-94 amendment : PIORECRUSDM/PCOPPUSDM 60→120d. These pin
# the END-TO-END behavioural consequence (not just the registry value,
# which test_fred_frequency_registry covers) : at the exact r93-observed
# age, the corrected registry makes _fred_liveness classify the live
# monthly series FRESH (false-DEGRADED gone) while a genuine death is
# still caught at 120d. _fred_liveness reads the registry via
# _max_age_days_for (override=None for these per _ASSET_CRITICAL_ANCHORS).


@pytest.mark.asyncio
@pytest.mark.parametrize("series_id", ["PIORECRUSDM", "PCOPPUSDM"])
async def test_iron_copper_77d_is_fresh_post_r94_recalibration(series_id: str) -> None:
    """The exact r93 ground-truth scenario : latest obs 77 days old.
    Pre-r94 (registry 60d) → STALE = false-DEGRADED every AUD card.
    Post-r94 (registry 120d) → FRESH. This is the false-alarm fix,
    proven at the _fred_liveness layer that the ADR-103 audit consumes."""
    lv = await _fred_liveness(_session_returning(_TODAY - timedelta(days=77)), series_id)
    assert lv.status == "fresh"
    assert lv.max_age_days == 120  # the r94-recalibrated registry value
    assert lv.age_days == 77


@pytest.mark.asyncio
@pytest.mark.parametrize("series_id", ["PIORECRUSDM", "PCOPPUSDM"])
async def test_iron_copper_genuine_death_still_caught_at_120d(series_id: str) -> None:
    """The 60→120 widening must NOT blind the surface to a genuine
    China-M1-class death : an observation older than 120d still
    classifies STALE (the death-catch is preserved, just at a
    correctly-calibrated threshold — ~4 months for a sub-driver)."""
    lv = await _fred_liveness(_session_returning(_TODAY - timedelta(days=130)), series_id)
    assert lv.status == "stale"
    assert lv.age_days == 130
    assert lv.max_age_days == 120


# ──────── ADR-104 : DegradedInputOut SSOT + producer→wire parity ───────
# r95 (ADR-104) extracts DegradedInputOut to the schemas.py SSOT (consumed
# by BOTH DataPoolOut and SessionCardOut) and persists the manifest on the
# card. These pin (a) the byte-identical re-export (anti-accumulation
# doctrine #4 — identity, not a duplicated definition) and (b) the
# producer DegradedInput dataclass → schemas SSOT model → JSON dict parity
# run_session_card relies on (no Pydantic-projection-gap at the persist
# boundary — the r66/r68 failure class structurally closed here).


def test_degraded_input_out_is_single_source_of_truth() -> None:
    """routers.data_pool.DegradedInputOut must BE schemas.DegradedInputOut
    (object identity) — a re-export, not a 3rd duplicated definition
    (ADR-104 §Decision-1). DataPoolOut's shape therefore stays
    byte-identical to pre-r95."""
    from ichor_api.routers.data_pool import DegradedInputOut as RouterDIO
    from ichor_api.schemas import DegradedInputOut as SchemaDIO

    assert RouterDIO is SchemaDIO
    assert set(SchemaDIO.model_fields) == {
        "series_id",
        "status",
        "latest_date",
        "age_days",
        "max_age_days",
        "impacted",
    }


def test_degraded_input_dataclass_serialises_through_ssot_for_persistence() -> None:
    """The exact run_session_card persist serialisation : producer
    DegradedInput frozen dataclass → schemas SSOT DegradedInputOut →
    model_dump(mode="json"). Pins date→ISO + 6-key shape parity with the
    SessionCardOut projection (the anti-projection-gap property end to
    end : what the persist path writes is exactly what the card endpoint
    reads back)."""
    from ichor_api.schemas import DegradedInputOut

    di = DegradedInput(
        series_id="MYAGM1CNM189N",
        status="stale",
        latest_date=date(2019, 8, 1),
        age_days=2481,
        max_age_days=60,
        impacted="AUD composite — China M1 credit-impulse driver",
    )
    payload = DegradedInputOut(
        series_id=di.series_id,
        status=di.status,
        latest_date=di.latest_date,
        age_days=di.age_days,
        max_age_days=di.max_age_days,
        impacted=di.impacted,
    ).model_dump(mode="json")
    assert payload == {
        "series_id": "MYAGM1CNM189N",
        "status": "stale",
        "latest_date": "2019-08-01",  # date → ISO string for the JSONB column
        "age_days": 2481,
        "max_age_days": 60,
        "impacted": "AUD composite — China M1 credit-impulse driver",
    }
