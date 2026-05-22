"""Unit tests for `_section_aud_specific` — Round-46 GAP-A continuation 5/5 closure.

Verifies the AUD/USD commodity-currency triangulation data-pool section
(ADR-092 Tier 1 inline-FRED ship + ADR-093 "degraded explicit" surface
pattern) :

  1. Asset gate : non-AUD_USD assets return ("", []) without DB I/O.
  2. Empty IRLTLT01AUM156N → silent skip (primary AUD anchor absent).
  3. AU10Y-only path (no DGS10/M2/commodity) renders Australia anchor only.
  4. Full 4-FRED path renders all 3 drivers + composite triangle.
  5. US-AU differential computed correctly (DGS10 - AU 10Y) — sign matches
     legacy `_section_rate_diff` `US - foreign` convention per ichor-trader
     r46 RED-1 review post-sign-flip.
  6. Source-stamp format pinned (FRED:IRLTLT01AUM156N@*, etc.).
  7. ADR-017 boundary preserved on rendered text.
  8. Symmetric language doctrine (AUD-bid + AUD-soft branches both present
     in EACH driver paragraph).
  9. Tetlock invalidation thresholds visible on all 3 drivers with DXY
     "within 20 sessions" time horizon (ichor-trader r46 RED-2 review).
 10. Degraded-explicit annotation cites ADR-093 in header + composite.
 11. Frequency mismatch warning emitted inline (BTP r34 + JPY r45 precedent).
 12. R24 SUBSET-not-SUPERSET via "degraded explicit" documented inline.
 13. China M1 (currency + demand deposits) TSF caveat + r46-round-2 audit
     swap trail (M2 series MYAGM2CNM189N DISCONTINUED Aug 2019).
 14. Composite triangle absent when any of 4 secondary drivers missing.
 15. Iron-without-copper renders Driver 3 with PARTIAL Tetlock note.
 16. Copper-without-iron silently skips Driver 3 entirely (M1 fix gate).
 17. Future upgrade path (ADR-096 RBA F1.1 + AKShare re-vetting) mentioned.
 18. Framework DOIs present (Engel-West + Chen-Rogoff + Ready-Roussanov-Ward).
 19. Monthly-cadence Tetlock thresholds (2-month, NOT n-day) + DXY 20-sessions
     horizon for daily cross-confirmation.

Uses _latest_fred monkeypatch (for 4 FRED series in arbitrary order). Zero
DB I/O on asset-gate fail path.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest
from ichor_api.services.adr017_filter import is_adr017_clean
from ichor_api.services.data_pool import _section_aud_specific


def _make_fred_stub(au10y=None, dgs10=None, china_m1=None, iron=None, copper=None):
    """Build a _latest_fred replacement that returns canned values per
    series_id. None means "series not available" (returns None)."""

    async def _stub(session, series_id, max_age_days=None):
        if series_id == "IRLTLT01AUM156N":
            return au10y
        if series_id == "DGS10":
            return dgs10
        if series_id == "MYAGM1CNM189N":
            return china_m1
        if series_id == "PIORECRUSDM":
            return iron
        if series_id == "PCOPPUSDM":
            return copper
        return None

    return _stub


# Canonical post-2026 prints used across happy-path tests
_AU10Y = (4.45, date(2026, 4, 1))  # AU 10Y monthly
_DGS10 = (4.45, date(2026, 5, 13))  # US 10Y daily
_CHINA_M1 = (320000.0, date(2026, 4, 1))  # China M1 monthly (CNY-bn)
_IRON = (108.50, date(2026, 4, 1))  # Iron Ore composite monthly
_COPPER = (9420.0, date(2026, 4, 1))  # Copper composite monthly


# ──────────────────────────── Asset gate ──────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "asset",
    [
        "EUR_USD",
        "GBP_USD",
        "USD_CAD",
        "USD_JPY",
        "XAU_USD",
        "NAS100_USD",
        "SPX500_USD",
    ],
)
async def test_returns_empty_on_non_aud_asset(asset: str) -> None:
    """Asset gate : only AUD_USD renders. Zero DB I/O on non-AUD assets."""
    session = AsyncMock()
    md, sources = await _section_aud_specific(session, asset)
    assert md == ""
    assert sources == []
    assert session.execute.await_count == 0


# ──────────────────────────── Empty AU10Y path ─────────────────────────


@pytest.mark.asyncio
async def test_returns_empty_when_au10y_missing(monkeypatch) -> None:
    """Empty IRLTLT01AUM156N → silent skip (Australia 10Y is the PRIMARY
    AUD-specific anchor ; without it section refuses to render even if
    secondary drivers have data)."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(au10y=None, dgs10=_DGS10, china_m1=_CHINA_M1, iron=_IRON, copper=_COPPER),
    )
    session = AsyncMock()
    md, sources = await _section_aud_specific(session, "AUD_USD")
    assert md == ""
    assert sources == []


# ──────────────────────────── AU10Y-only path ──────────────────────────


@pytest.mark.asyncio
async def test_renders_au10y_only_when_secondary_absent(monkeypatch) -> None:
    """AU10Y populated but all secondaries absent → section renders
    Australia anchor only (graceful degradation, no rate-diff, no M2,
    no commodity, no composite)."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(au10y=_AU10Y),
    )
    session = AsyncMock()
    md, sources = await _section_aud_specific(session, "AUD_USD")
    assert "AU 10Y = 4.45%" in md
    assert "OECD MEI monthly" in md
    # No secondary blocks
    assert "DGS10 = " not in md
    assert "China M1" not in md
    assert "Iron Ore" not in md
    assert "Copper" not in md
    # No composite triangle
    assert "commodity-currency triangle composite" not in md
    assert sources == ["FRED:IRLTLT01AUM156N@2026-04-01"]


# ──────────────────────────── Full 4-FRED path ─────────────────────────


@pytest.mark.asyncio
async def test_renders_full_triangle_when_all_drivers_present(monkeypatch) -> None:
    """All 4 secondary FRED series populated → renders all 3 drivers
    + composite triangle + 5 source-stamps."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(au10y=_AU10Y, dgs10=_DGS10, china_m1=_CHINA_M1, iron=_IRON, copper=_COPPER),
    )
    session = AsyncMock()
    md, sources = await _section_aud_specific(session, "AUD_USD")
    # Australia anchor block
    assert "AU 10Y = 4.45%" in md
    # Rate-differential block
    assert "DGS10 = 4.45%" in md
    assert "US-AU 10Y differential = " in md
    # China M1 block
    assert "China M1 = " in md
    assert "MYAGM1CNM189N" in md
    # Commodity block
    assert "Iron Ore (PIORECRUSDM)" in md
    assert "Copper (PCOPPUSDM)" in md
    # r94 YELLOW-1 (ichor-trader R28) : the iron/copper composite MUST
    # carry the staleness/no-extrapolate caveat — material now that the
    # registry tolerance doubled 60→120d (ADR-092 §Round-94). Mirrors the
    # China-M1 single-print constraint precedent. Regression-pinned.
    assert "Staleness caveat (r94, ADR-092 §Round-94)" in md
    assert "IMF-PCPS MONTHLY" in md
    assert "SHOULD NOT extrapolate near-term direction" in md
    assert "SLOW terms-of-trade REGIME marker" in md
    assert "60→120 d" in md
    # Composite triangle
    assert "commodity-currency triangle composite" in md
    # 5 source-stamps
    assert "FRED:IRLTLT01AUM156N@2026-04-01" in sources
    assert "FRED:DGS10@2026-05-13" in sources
    assert "FRED:MYAGM1CNM189N@2026-04-01" in sources
    assert "FRED:PIORECRUSDM@2026-04-01" in sources
    assert "FRED:PCOPPUSDM@2026-04-01" in sources
    assert len(sources) == 5


# ──────────────────────────── Differential math ────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("au10y_value", "dgs10_value", "expected_diff_str"),
    [
        (4.45, 4.45, "+0.00 pp"),  # parity (2026 print)
        (4.20, 3.80, "-0.40 pp"),  # US-negative (AU=4.20 > US=3.80)
        (3.50, 4.45, "+0.95 pp"),  # US-positive (AU=3.50 < US=4.45)
        (5.10, 4.20, "-0.90 pp"),  # US-negative wide (AU=5.10 > US=4.20)
        (6.50, 3.50, "-3.00 pp"),  # US-negative very-wide (code-reviewer L6 add)
    ],
)
async def test_us_au_differential_computed_correctly(
    monkeypatch, au10y_value: float, dgs10_value: float, expected_diff_str: str
) -> None:
    """5 scenarios : differential = DGS10 - AU 10Y (US - AU sign convention
    matching legacy `_section_rate_diff` per ichor-trader r46 RED-1 review),
    signed format `+X.XX pp` or `-X.XX pp`."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            au10y=(au10y_value, date(2026, 4, 1)),
            dgs10=(dgs10_value, date(2026, 5, 13)),
        ),
    )
    session = AsyncMock()
    md, _ = await _section_aud_specific(session, "AUD_USD")
    assert expected_diff_str in md


# ──────────────────────────── ADR-017 boundary ─────────────────────────


@pytest.mark.asyncio
async def test_rendered_text_passes_adr017_filter(monkeypatch) -> None:
    """Full-render text MUST pass the r32 hardened ADR-017 filter (no
    BUY/SELL/LONG NOW/SHORT NOW/etc. token in any rendered branch)."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(au10y=_AU10Y, dgs10=_DGS10, china_m1=_CHINA_M1, iron=_IRON, copper=_COPPER),
    )
    session = AsyncMock()
    md, _ = await _section_aud_specific(session, "AUD_USD")
    assert is_adr017_clean(md), "ADR-017 violation in r46 _section_aud_specific output."


# ──────────────────────────── Symmetric language doctrine ──────────────


@pytest.mark.asyncio
async def test_symmetric_AUD_bid_and_AUD_soft_branches_emitted(monkeypatch) -> None:
    """ichor-trader r32/r41/r42/r43/r45 carry-forward : EACH driver
    interpretive paragraph emits BOTH AUD-bid (carry-bid regime,
    reflation, China credit expansion) AND AUD-soft (carry-unwind,
    deflation, China credit contraction) branches."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(au10y=_AU10Y, dgs10=_DGS10, china_m1=_CHINA_M1, iron=_IRON, copper=_COPPER),
    )
    session = AsyncMock()
    md, _ = await _section_aud_specific(session, "AUD_USD")
    # AUD-bid + AUD-soft tokens present
    assert "AUD-bid" in md
    assert "AUD-soft" in md
    # Regime references
    md_lower = md.lower()
    assert "carry-bid" in md_lower
    assert "carry-unwind" in md_lower
    assert "risk-off" in md_lower or "vol_elevated" in md_lower


# ──────────────────────────── Tetlock invalidation (all 3 drivers) ─────


@pytest.mark.asyncio
async def test_tetlock_invalidation_thresholds_visible_all_drivers(monkeypatch) -> None:
    """r39 codified + r42+r43+r45 carry-forward : ALL 3 driver paragraphs
    MUST emit explicit Tetlock invalidation lines with cross-driver
    confirmation thresholds at monthly cadence + DXY 20-session horizon
    (ichor-trader r46 RED-2 review post-time-horizon-fix)."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(au10y=_AU10Y, dgs10=_DGS10, china_m1=_CHINA_M1, iron=_IRON, copper=_COPPER),
    )
    session = AsyncMock()
    md, _ = await _section_aud_specific(session, "AUD_USD")
    # Tetlock invalidation appears multiple times (one per driver)
    assert md.count("Tetlock invalidation") >= 3
    # Specific monthly-cadence thresholds (NOT n-day for the AUD-internal series)
    assert "monthly prints" in md
    # Cross-driver DXY confirmation with explicit time horizon (RED-2 fix)
    assert "DXY rises by > 2.0% within 20 sessions" in md
    assert "DXY falls below its trailing 6-month mean within 20 sessions" in md
    # Iron-ore + copper Tetlock cross-confirmation
    assert "iron-ore" in md.lower()
    assert "copper" in md.lower()


# ──────────────────────────── Degraded explicit (ADR-093) ──────────────


@pytest.mark.asyncio
async def test_degraded_explicit_annotation_in_header_and_composite(monkeypatch) -> None:
    """ADR-093 surface pattern : section header AND composite triangle
    paragraph BOTH cite ADR-093 by number + 'degraded explicit' +
    'commodity surface gap'."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(au10y=_AU10Y, dgs10=_DGS10, china_m1=_CHINA_M1, iron=_IRON, copper=_COPPER),
    )
    session = AsyncMock()
    md, _ = await _section_aud_specific(session, "AUD_USD")
    # ADR-093 cited
    assert "ADR-093" in md
    # "degraded explicit" + "commodity surface gap" tokens present
    assert "degraded explicit" in md.lower()
    assert "commodity surface gap" in md.lower()
    # Header mentions all 3 are monthly + DGS10 daily anchor
    assert "monthly" in md.lower()
    # Composite triangle present (since all 4 drivers fresh)
    assert "commodity-currency triangle composite" in md


# ──────────────────────────── Frequency mismatch warning ───────────────


@pytest.mark.asyncio
async def test_frequency_mismatch_warning_emitted(monkeypatch) -> None:
    """BTP r34 + JPY r45 cadence-mismatch precedent : the section MUST
    surface the daily/monthly cadence mismatch inline so the LLM treats
    the differential as a REGIME indicator, not an intraday signal."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(au10y=_AU10Y, dgs10=_DGS10, china_m1=_CHINA_M1, iron=_IRON, copper=_COPPER),
    )
    session = AsyncMock()
    md, _ = await _section_aud_specific(session, "AUD_USD")
    assert "Frequency mismatch" in md
    assert "DGS10 is DAILY" in md
    assert "AU 10Y is MONTHLY" in md
    assert "REGIME indicator" in md
    assert "BTP r34" in md and "JPY r45" in md


# ──────────────────────────── China M1 TSF caveat ──────────────────────


@pytest.mark.asyncio
async def test_china_m1_tsf_caveat_present(monkeypatch) -> None:
    """ADR-092 §DEFER firmly + r46-round-2 audit swap : TSF direct collector
    deferred ; M1 (narrower than M2) is a PROXY for credit impulse, NOT direct
    TSF. The section MUST surface this caveat inline + acknowledge the swap
    from the original MYAGM2CNM189N (DISCONTINUED Aug 2019)."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(au10y=_AU10Y, dgs10=_DGS10, china_m1=_CHINA_M1, iron=_IRON, copper=_COPPER),
    )
    session = AsyncMock()
    md, _ = await _section_aud_specific(session, "AUD_USD")
    # M1 (post-swap) caveat
    assert "M1 (currency + demand deposits) is a NARROWER aggregate" in md
    assert "PROXY" in md and "credit impulse" in md
    assert "NOT direct TSF" in md
    assert "ADR-092" in md  # cited at the caveat block
    # r46-round-2 audit trail : acknowledge M2 was DISCONTINUED Aug 2019
    assert "MYAGM2CNM189N" in md  # cited as the discontinued series
    assert "DISCONTINUED Aug 2019" in md
    # Barcelona et al. 2022 framework citation for M1 leading-indicator empirics
    assert "Barcelona" in md
    assert "Fed IFDP 1360" in md


# ──────────────────────────── Composite triangle conditional render ────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("dgs10", "china_m1", "iron", "copper"),
    [
        (None, _CHINA_M1, _IRON, _COPPER),  # DGS10 missing
        (_DGS10, None, _IRON, _COPPER),  # China M1 missing
        (_DGS10, _CHINA_M1, None, _COPPER),  # Iron missing
        (_DGS10, _CHINA_M1, _IRON, None),  # Copper missing
    ],
)
async def test_composite_absent_when_any_secondary_missing(
    monkeypatch, dgs10, china_m1, iron, copper
) -> None:
    """Composite triangle requires ALL 4 secondary drivers fresh. Any
    missing → no composite paragraph (other rendered blocks still present
    if their data is available)."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(au10y=_AU10Y, dgs10=dgs10, china_m1=china_m1, iron=iron, copper=copper),
    )
    session = AsyncMock()
    md, _ = await _section_aud_specific(session, "AUD_USD")
    assert "commodity-currency triangle composite" not in md


# ──────────────────────────── Iron-without-copper partial render ───────


@pytest.mark.asyncio
async def test_iron_only_renders_partial_driver3_with_softer_tetlock(monkeypatch) -> None:
    """Iron-ore alone (no copper) → Driver 3 block renders Iron Ore line
    + interpretation + PARTIAL Tetlock invalidation (softer, no copper
    cross-confirmation per ichor-trader r46 M1 review). No composite
    triangle (composite gates on all 4 secondaries)."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(au10y=_AU10Y, dgs10=_DGS10, china_m1=_CHINA_M1, iron=_IRON, copper=None),
    )
    session = AsyncMock()
    md, sources = await _section_aud_specific(session, "AUD_USD")
    assert "Iron Ore (PIORECRUSDM)" in md
    assert "Copper (PCOPPUSDM)" not in md
    assert "commodity-currency triangle composite" not in md
    # Softer PARTIAL Tetlock (no copper cross-confirmation)
    assert "PARTIAL — copper cross-confirmation absent" in md
    assert "Conviction reduced vs the full 3-driver Tetlock" in md
    assert "FRED:PIORECRUSDM@2026-04-01" in sources
    assert all("PCOPPUSDM" not in s for s in sources)


# ──────────────────────────── Copper-without-iron silent skip (M1 fix) ─


@pytest.mark.asyncio
async def test_copper_only_silently_skips_driver3(monkeypatch) -> None:
    """Copper alone (no iron) → Driver 3 silently skips ENTIRELY (M1 fix
    per ichor-trader/code-reviewer r46 review : copper alone is base-
    metals-complex secondary, meaningless without the iron-ore primary
    signal for AUD commodity-currency framing). Iron-ore reasoning would
    otherwise reference an absent observation. Outer gate now requires
    `iron_latest is not None`."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(au10y=_AU10Y, dgs10=_DGS10, china_m1=_CHINA_M1, iron=None, copper=_COPPER),
    )
    session = AsyncMock()
    md, sources = await _section_aud_specific(session, "AUD_USD")
    # Driver 3 block entirely absent
    assert "Iron Ore (PIORECRUSDM)" not in md
    assert "Copper (PCOPPUSDM)" not in md
    assert "Commodity terms-of-trade composite" not in md
    assert "commodity-currency triangle composite" not in md
    # Copper data NOT stamped (silent skip even though copper is available)
    assert all("PIORECRUSDM" not in s for s in sources)
    assert all("PCOPPUSDM" not in s for s in sources)
    # Other drivers (AU 10Y + DGS10 + M2) still rendered
    assert "AU 10Y = 4.45%" in md
    assert "DGS10 = 4.45%" in md
    assert "China M1 = " in md


# ──────────────────────────── Future upgrade path mention ──────────────


@pytest.mark.asyncio
async def test_future_upgrade_path_mentioned_in_composite(monkeypatch) -> None:
    """ADR-093 acceptance criterion 3 : the composite triangle paragraph
    MUST mention the future upgrade path (ADR-096 RBA F1.1 daily +
    AKShare re-vetting)."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(au10y=_AU10Y, dgs10=_DGS10, china_m1=_CHINA_M1, iron=_IRON, copper=_COPPER),
    )
    session = AsyncMock()
    md, _ = await _section_aud_specific(session, "AUD_USD")
    assert "ADR-096" in md
    assert "RBA F1.1" in md
    assert "AKShare" in md or "LME" in md
    assert "AUD anti-skill" in md or "Vovk Sunday" in md


# ──────────────────────────── Framework DOI attribution ────────────────


@pytest.mark.asyncio
async def test_framework_dois_present(monkeypatch) -> None:
    """Citation-quality discipline (r42 R28 + r43 R39 + r45 carry-forward) :
    framework attributions MUST include DOIs for all 3 cited frameworks
    (Engel-West 2005 + Chen-Rogoff 2003 + Ready-Roussanov-Ward 2017)."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(au10y=_AU10Y, dgs10=_DGS10, china_m1=_CHINA_M1, iron=_IRON, copper=_COPPER),
    )
    session = AsyncMock()
    md, _ = await _section_aud_specific(session, "AUD_USD")
    # Engel-West 2005 DOI
    assert "10.1086/429137" in md
    # Chen-Rogoff 2003 DOI
    assert "10.1016/S0022-1996(02)00072-7" in md
    # Ready-Roussanov-Ward 2017 DOI
    assert "10.1111/jofi.12546" in md


# ──────────────────────────── R24 SUBSET-not-SUPERSET ──────────────────


@pytest.mark.asyncio
async def test_r24_subset_not_superset_documented_inline(monkeypatch) -> None:
    """R24 discipline (r40 codified) : the composite triangle MUST
    document the cadence-mismatch reasoning inline, citing 'degraded
    explicit' + ADR-093."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(au10y=_AU10Y, dgs10=_DGS10, china_m1=_CHINA_M1, iron=_IRON, copper=_COPPER),
    )
    session = AsyncMock()
    md, _ = await _section_aud_specific(session, "AUD_USD")
    assert "R24 SUBSET-not-SUPERSET" in md
    assert "DEGRADED EXPLICIT" in md.upper()  # case-insensitive composite reference


# ──────────────────────────── Monthly-cadence Tetlock thresholds ───────


@pytest.mark.asyncio
async def test_tetlock_thresholds_monthly_cadence_not_daily(monkeypatch) -> None:
    """ADR-093 §Decision §4 : Tetlock magnitudes pinned at monthly cadence
    (2-month thresholds, NOT n-day) — consistent with the degraded-explicit
    REGIME-indicator framing."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(au10y=_AU10Y, dgs10=_DGS10, china_m1=_CHINA_M1, iron=_IRON, copper=_COPPER),
    )
    session = AsyncMock()
    md, _ = await _section_aud_specific(session, "AUD_USD")
    # Monthly cadence tokens
    assert "monthly prints" in md or "monthly cadence" in md
    # NOT n-sessions tokens (which would be daily-cadence Tetlock thresholds)
    # JPY r45 uses "within 5 sessions" ; AUD r46 should NOT use that
    # form (or only as a deliberate reference for cross-driver DXY which
    # is daily). The thresholds for the AUD drivers themselves are
    # 2-monthly-prints scale.
    assert "across 2 consecutive monthly prints" in md or "across 2 monthly prints" in md


# ════════════════════════════════════════════════════════════════════════
# STRESS TESTS — round-46 round-2-mandatory empirical validation beyond
# happy-path mock-passing. Eliot directive : "fais en sorte que tout
# fonctionne... pas que ça fonctionne simplement". Each test surfaces a
# pathological FRED return shape that the 17 happy-path tests above don't
# exercise. Goal : confirm no crash, no partial render bleed-through, no
# ADR-017 violation, no f-string overflow under degenerate inputs.
# ════════════════════════════════════════════════════════════════════════


# ──────────────────────────── Stress: NaN values ───────────────────────


@pytest.mark.asyncio
async def test_stress_au10y_nan_does_not_crash(monkeypatch) -> None:
    """STRESS : `_latest_fred` returns (nan, date) for AU 10Y. The
    f-string `f"{nan:.2f}"` renders `"nan"` (Python convention) ; the
    differential math `dgs10 - nan = nan` propagates correctly without
    raising. Rendered text must still pass ADR-017 + must not break the
    section (no exception)."""
    nan = float("nan")
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            au10y=(nan, date(2026, 4, 1)),
            dgs10=_DGS10,
            china_m1=_CHINA_M1,
            iron=_IRON,
            copper=_COPPER,
        ),
    )
    session = AsyncMock()
    # Must not raise
    md, sources = await _section_aud_specific(session, "AUD_USD")
    # NaN renders as literal "nan" in f-string
    assert "AU 10Y = nan%" in md
    # Differential = dgs10 - nan = nan ; f"{nan:+.2f}" renders "+nan"
    assert "nan pp" in md
    # Rendered text still passes ADR-017 boundary
    assert is_adr017_clean(md), "ADR-017 violation on NaN render."
    # 5 source-stamps still emitted (data is "present" even if pathological)
    assert len(sources) == 5


@pytest.mark.asyncio
async def test_stress_all_five_fred_returns_nan_does_not_crash(monkeypatch) -> None:
    """STRESS : ALL 5 FRED returns are (nan, date). Section should render
    every block (data is "present") with `nan` tokens but not crash."""
    nan = float("nan")
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            au10y=(nan, date(2026, 4, 1)),
            dgs10=(nan, date(2026, 5, 13)),
            china_m1=(nan, date(2026, 4, 1)),
            iron=(nan, date(2026, 4, 1)),
            copper=(nan, date(2026, 4, 1)),
        ),
    )
    session = AsyncMock()
    md, sources = await _section_aud_specific(session, "AUD_USD")
    # Composite triangle still emitted (all 4 secondaries non-None)
    assert "commodity-currency triangle composite" in md
    # ADR-017 clean
    assert is_adr017_clean(md), "ADR-017 violation on all-NaN render."
    assert len(sources) == 5


# ──────────────────────────── Stress: Inf values ───────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("inf_field",),
    [
        ("au10y",),
        ("dgs10",),
        ("china_m1",),
        ("iron",),
        ("copper",),
    ],
)
async def test_stress_inf_in_any_fred_return_does_not_crash(monkeypatch, inf_field: str) -> None:
    """STRESS : +inf in any of the 5 FRED returns. Section must not crash
    and rendered text must still pass ADR-017."""
    pos_inf = float("inf")
    fields = {
        "au10y": _AU10Y,
        "dgs10": _DGS10,
        "china_m1": _CHINA_M1,
        "iron": _IRON,
        "copper": _COPPER,
    }
    # Replace the chosen field with (+inf, original_date)
    _, original_date = fields[inf_field]
    fields[inf_field] = (pos_inf, original_date)
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(**fields),
    )
    session = AsyncMock()
    md, _ = await _section_aud_specific(session, "AUD_USD")
    # Must contain "inf" token somewhere (the inf-stamped field rendered)
    assert "inf" in md
    # ADR-017 clean
    assert is_adr017_clean(md), f"ADR-017 violation on +inf {inf_field} render."


@pytest.mark.asyncio
async def test_stress_negative_inf_does_not_crash(monkeypatch) -> None:
    """STRESS : -inf for au10y. Section must render `-inf%` and the
    differential `DGS10 - (-inf) = +inf` without raising."""
    neg_inf = float("-inf")
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            au10y=(neg_inf, date(2026, 4, 1)),
            dgs10=_DGS10,
            china_m1=_CHINA_M1,
            iron=_IRON,
            copper=_COPPER,
        ),
    )
    session = AsyncMock()
    md, _ = await _section_aud_specific(session, "AUD_USD")
    assert "AU 10Y = -inf%" in md
    # dgs10 - (-inf) = +inf, formatted as "+inf pp"
    assert "+inf pp" in md or "inf pp" in md
    assert is_adr017_clean(md), "ADR-017 violation on -inf render."


# ──────────────────────────── Stress: Very-large values ────────────────


@pytest.mark.asyncio
async def test_stress_china_m1_very_large_value_comma_formatter(monkeypatch) -> None:
    """STRESS : China M1 = 999_999_999 CNY-bn. The `{:,.0f}` formatter
    must render `999,999,999` without overflow or exception. Tests that
    the comma-separator format works on 9-digit values."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            au10y=_AU10Y,
            dgs10=_DGS10,
            china_m1=(999_999_999.0, date(2026, 4, 1)),
            iron=_IRON,
            copper=_COPPER,
        ),
    )
    session = AsyncMock()
    md, _ = await _section_aud_specific(session, "AUD_USD")
    assert "China M1 = 999,999,999 CNY-bn" in md
    assert is_adr017_clean(md)


@pytest.mark.asyncio
async def test_stress_china_m1_extreme_large_value(monkeypatch) -> None:
    """STRESS : China M1 = 1e15 (quadrillion-scale). Stress the comma
    formatter on a value far beyond any realistic empirical range."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            au10y=_AU10Y,
            dgs10=_DGS10,
            china_m1=(1e15, date(2026, 4, 1)),
            iron=_IRON,
            copper=_COPPER,
        ),
    )
    session = AsyncMock()
    md, _ = await _section_aud_specific(session, "AUD_USD")
    # 1e15 = 1,000,000,000,000,000
    assert "1,000,000,000,000,000" in md
    assert is_adr017_clean(md)


# ──────────────────────────── Stress: Negative yields ──────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("au10y_value", "dgs10_value", "expected_diff_str", "expected_au_str"),
    [
        (-0.50, 4.45, "+4.95 pp", "AU 10Y = -0.50%"),  # AU deeply negative
        (-0.10, -0.20, "-0.10 pp", "AU 10Y = -0.10%"),  # both negative, US wider neg
        (-1.50, 0.00, "+1.50 pp", "AU 10Y = -1.50%"),  # AU very negative, US zero
    ],
)
async def test_stress_negative_yields_render_with_correct_signs(
    monkeypatch, au10y_value, dgs10_value, expected_diff_str, expected_au_str
) -> None:
    """STRESS : negative-rate scenarios (theoretical post-2019-ZIRP).
    `{:+.2f}` must render the differential with explicit sign on both
    sides ; the raw AU 10Y print uses `{:.2f}` which preserves `-`
    prefix natively."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            au10y=(au10y_value, date(2026, 4, 1)),
            dgs10=(dgs10_value, date(2026, 5, 13)),
        ),
    )
    session = AsyncMock()
    md, _ = await _section_aud_specific(session, "AUD_USD")
    assert expected_au_str in md
    assert expected_diff_str in md
    assert is_adr017_clean(md)


# ──────────────────────────── Stress: Zero values ──────────────────────


@pytest.mark.asyncio
async def test_stress_zero_iron_and_copper_render_composite(monkeypatch) -> None:
    """STRESS : iron-ore = 0.0 AND copper = 0.0 (degenerate but non-None).
    Composite triangle still gates open (all 4 secondaries not None) and
    renders both `0.00 index` lines without crash."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            au10y=_AU10Y,
            dgs10=_DGS10,
            china_m1=_CHINA_M1,
            iron=(0.0, date(2026, 4, 1)),
            copper=(0.0, date(2026, 4, 1)),
        ),
    )
    session = AsyncMock()
    md, _ = await _section_aud_specific(session, "AUD_USD")
    assert "Iron Ore (PIORECRUSDM) = 0.00 index" in md
    assert "Copper (PCOPPUSDM) = 0.00 index" in md
    # Composite triangle still emitted (0.0 is not None)
    assert "commodity-currency triangle composite" in md
    assert is_adr017_clean(md)


@pytest.mark.asyncio
async def test_stress_zero_china_m1_does_not_crash(monkeypatch) -> None:
    """STRESS : China M1 = 0 CNY-bn (degenerate). Comma formatter must
    render `0` without exception."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            au10y=_AU10Y,
            dgs10=_DGS10,
            china_m1=(0.0, date(2026, 4, 1)),
            iron=_IRON,
            copper=_COPPER,
        ),
    )
    session = AsyncMock()
    md, _ = await _section_aud_specific(session, "AUD_USD")
    assert "China M1 = 0 CNY-bn" in md
    assert is_adr017_clean(md)


# ──────────────────────────── Stress: Future / past dates ──────────────


@pytest.mark.asyncio
async def test_stress_future_date_2099_renders_correctly(monkeypatch) -> None:
    """STRESS : `_latest_fred` returns (value, date(2099, 1, 1)). The
    f-string `{date:%Y-%m-%d}` renders `2099-01-01` without overflow.
    Source-stamp uses identical format."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            au10y=(4.45, date(2099, 1, 1)),
            dgs10=(4.45, date(2099, 1, 1)),
            china_m1=(320000.0, date(2099, 1, 1)),
            iron=(108.5, date(2099, 1, 1)),
            copper=(9420.0, date(2099, 1, 1)),
        ),
    )
    session = AsyncMock()
    md, sources = await _section_aud_specific(session, "AUD_USD")
    assert "2099-01-01" in md
    assert "FRED:IRLTLT01AUM156N@2099-01-01" in sources
    assert "FRED:DGS10@2099-01-01" in sources
    assert is_adr017_clean(md)


@pytest.mark.asyncio
async def test_stress_past_date_1990_renders_correctly(monkeypatch) -> None:
    """STRESS : `_latest_fred` returns (value, date(1990, 1, 1)). Pre-
    Australian-data era. Section just renders the old date without
    interpretation logic crashing."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            au10y=(13.5, date(1990, 1, 1)),  # high-yield era
            dgs10=(8.0, date(1990, 1, 1)),
            china_m1=(1000.0, date(1990, 1, 1)),
            iron=(15.0, date(1990, 1, 1)),
            copper=(2500.0, date(1990, 1, 1)),
        ),
    )
    session = AsyncMock()
    md, sources = await _section_aud_specific(session, "AUD_USD")
    assert "1990-01-01" in md
    assert "AU 10Y = 13.50%" in md
    assert "FRED:IRLTLT01AUM156N@1990-01-01" in sources
    assert is_adr017_clean(md)


# ──────────────────────────── Stress: All 5 None / no partial bleed ────


@pytest.mark.asyncio
async def test_stress_all_five_fred_returns_none_yields_clean_empty(monkeypatch) -> None:
    """STRESS : ALL 5 FRED returns are None. Primary-anchor gate triggers
    silent skip — `("", [])`. Critical : NO partial render bleed-through
    (no header line, no orphan source-stamp, nothing leaks)."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(),  # all defaults = None
    )
    session = AsyncMock()
    md, sources = await _section_aud_specific(session, "AUD_USD")
    assert md == ""
    assert sources == []
    # Strictly empty — no whitespace, no header-only leak
    assert len(md) == 0
    assert len(sources) == 0


# ──────────────────────────── Stress: Asset gate casing ────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "weird_asset",
    [
        "aud_usd",  # lowercase
        "AUD_usd",  # mixed
        "Aud_Usd",  # title case
        "AUDUSD",  # no underscore
        "AUD-USD",  # dash
        " AUD_USD",  # leading whitespace
        "AUD_USD ",  # trailing whitespace
        "",  # empty
    ],
)
async def test_stress_asset_gate_rejects_non_exact_casing(monkeypatch, weird_asset: str) -> None:
    """STRESS : the asset gate uses `if asset != "AUD_USD"` — strict
    exact match. Lowercase, mixed case, no-underscore, dash, padding
    variants all return `("", [])` with ZERO DB I/O. Verifies the gate
    is not silently case-insensitive."""
    # Even if FRED stub would return data, the gate fires first
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(au10y=_AU10Y, dgs10=_DGS10, china_m1=_CHINA_M1, iron=_IRON, copper=_COPPER),
    )
    session = AsyncMock()
    md, sources = await _section_aud_specific(session, weird_asset)
    assert md == ""
    assert sources == []
    # Critical : zero DB I/O on gate fail
    assert session.execute.await_count == 0


# ──────────────────────────── Stress: Mixed pathological combos ────────


@pytest.mark.asyncio
async def test_stress_mixed_pathological_nan_inf_zero_negative_combo(monkeypatch) -> None:
    """STRESS : worst-case combo — au10y=nan, dgs10=-inf, china_m1=0,
    iron=very-large, copper=negative. Section must render every block
    without crash and pass ADR-017."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(
            au10y=(float("nan"), date(2026, 4, 1)),
            dgs10=(float("-inf"), date(2026, 5, 13)),
            china_m1=(0.0, date(2026, 4, 1)),
            iron=(1e10, date(2026, 4, 1)),
            copper=(-500.0, date(2026, 4, 1)),  # negative copper price (impossible but defensive)
        ),
    )
    session = AsyncMock()
    md, sources = await _section_aud_specific(session, "AUD_USD")
    # Section did not crash
    assert "AUD-specific signals" in md
    # All 5 source-stamps emitted
    assert len(sources) == 5
    # Composite triangle still gates open
    assert "commodity-currency triangle composite" in md
    # ADR-017 holds even under degenerate inputs
    assert is_adr017_clean(md), "ADR-017 violation on mixed pathological combo."
