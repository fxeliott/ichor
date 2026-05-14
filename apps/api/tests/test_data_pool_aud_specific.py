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
 13. China M2 TSF caveat (M2 is a PROXY for credit impulse).
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


def _make_fred_stub(au10y=None, dgs10=None, china_m2=None, iron=None, copper=None):
    """Build a _latest_fred replacement that returns canned values per
    series_id. None means "series not available" (returns None)."""

    async def _stub(session, series_id, max_age_days=None):
        if series_id == "IRLTLT01AUM156N":
            return au10y
        if series_id == "DGS10":
            return dgs10
        if series_id == "MYAGM2CNM189N":
            return china_m2
        if series_id == "PIORECRUSDM":
            return iron
        if series_id == "PCOPPUSDM":
            return copper
        return None

    return _stub


# Canonical post-2026 prints used across happy-path tests
_AU10Y = (4.45, date(2026, 4, 1))  # AU 10Y monthly
_DGS10 = (4.45, date(2026, 5, 13))  # US 10Y daily
_CHINA_M2 = (320000.0, date(2026, 4, 1))  # China M2 monthly (CNY-bn)
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
        _make_fred_stub(au10y=None, dgs10=_DGS10, china_m2=_CHINA_M2, iron=_IRON, copper=_COPPER),
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
    assert "China M2" not in md
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
        _make_fred_stub(au10y=_AU10Y, dgs10=_DGS10, china_m2=_CHINA_M2, iron=_IRON, copper=_COPPER),
    )
    session = AsyncMock()
    md, sources = await _section_aud_specific(session, "AUD_USD")
    # Australia anchor block
    assert "AU 10Y = 4.45%" in md
    # Rate-differential block
    assert "DGS10 = 4.45%" in md
    assert "US-AU 10Y differential = " in md
    # China M2 block
    assert "China M2 = " in md
    assert "MYAGM2CNM189N" in md
    # Commodity block
    assert "Iron Ore (PIORECRUSDM)" in md
    assert "Copper (PCOPPUSDM)" in md
    # Composite triangle
    assert "commodity-currency triangle composite" in md
    # 5 source-stamps
    assert "FRED:IRLTLT01AUM156N@2026-04-01" in sources
    assert "FRED:DGS10@2026-05-13" in sources
    assert "FRED:MYAGM2CNM189N@2026-04-01" in sources
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
        _make_fred_stub(au10y=_AU10Y, dgs10=_DGS10, china_m2=_CHINA_M2, iron=_IRON, copper=_COPPER),
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
        _make_fred_stub(au10y=_AU10Y, dgs10=_DGS10, china_m2=_CHINA_M2, iron=_IRON, copper=_COPPER),
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
        _make_fred_stub(au10y=_AU10Y, dgs10=_DGS10, china_m2=_CHINA_M2, iron=_IRON, copper=_COPPER),
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
        _make_fred_stub(au10y=_AU10Y, dgs10=_DGS10, china_m2=_CHINA_M2, iron=_IRON, copper=_COPPER),
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
        _make_fred_stub(au10y=_AU10Y, dgs10=_DGS10, china_m2=_CHINA_M2, iron=_IRON, copper=_COPPER),
    )
    session = AsyncMock()
    md, _ = await _section_aud_specific(session, "AUD_USD")
    assert "Frequency mismatch" in md
    assert "DGS10 is DAILY" in md
    assert "AU 10Y is MONTHLY" in md
    assert "REGIME indicator" in md
    assert "BTP r34" in md and "JPY r45" in md


# ──────────────────────────── China M2 TSF caveat ──────────────────────


@pytest.mark.asyncio
async def test_china_m2_tsf_caveat_present(monkeypatch) -> None:
    """ADR-092 §DEFER firmly : TSF direct collector deferred. M2 is a
    PROXY for credit impulse, NOT direct TSF. The section MUST surface
    this caveat inline."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(au10y=_AU10Y, dgs10=_DGS10, china_m2=_CHINA_M2, iron=_IRON, copper=_COPPER),
    )
    session = AsyncMock()
    md, _ = await _section_aud_specific(session, "AUD_USD")
    assert "M2 is a PROXY for credit impulse" in md
    assert "NOT direct TSF" in md
    assert "ADR-092" in md  # cited at the M2 caveat block


# ──────────────────────────── Composite triangle conditional render ────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("dgs10", "china_m2", "iron", "copper"),
    [
        (None, _CHINA_M2, _IRON, _COPPER),  # DGS10 missing
        (_DGS10, None, _IRON, _COPPER),  # China M2 missing
        (_DGS10, _CHINA_M2, None, _COPPER),  # Iron missing
        (_DGS10, _CHINA_M2, _IRON, None),  # Copper missing
    ],
)
async def test_composite_absent_when_any_secondary_missing(
    monkeypatch, dgs10, china_m2, iron, copper
) -> None:
    """Composite triangle requires ALL 4 secondary drivers fresh. Any
    missing → no composite paragraph (other rendered blocks still present
    if their data is available)."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(au10y=_AU10Y, dgs10=dgs10, china_m2=china_m2, iron=iron, copper=copper),
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
        _make_fred_stub(au10y=_AU10Y, dgs10=_DGS10, china_m2=_CHINA_M2, iron=_IRON, copper=None),
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
        _make_fred_stub(au10y=_AU10Y, dgs10=_DGS10, china_m2=_CHINA_M2, iron=None, copper=_COPPER),
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
    assert "China M2 = " in md


# ──────────────────────────── Future upgrade path mention ──────────────


@pytest.mark.asyncio
async def test_future_upgrade_path_mentioned_in_composite(monkeypatch) -> None:
    """ADR-093 acceptance criterion 3 : the composite triangle paragraph
    MUST mention the future upgrade path (ADR-096 RBA F1.1 daily +
    AKShare re-vetting)."""
    monkeypatch.setattr(
        "ichor_api.services.data_pool._latest_fred",
        _make_fred_stub(au10y=_AU10Y, dgs10=_DGS10, china_m2=_CHINA_M2, iron=_IRON, copper=_COPPER),
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
        _make_fred_stub(au10y=_AU10Y, dgs10=_DGS10, china_m2=_CHINA_M2, iron=_IRON, copper=_COPPER),
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
        _make_fred_stub(au10y=_AU10Y, dgs10=_DGS10, china_m2=_CHINA_M2, iron=_IRON, copper=_COPPER),
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
        _make_fred_stub(au10y=_AU10Y, dgs10=_DGS10, china_m2=_CHINA_M2, iron=_IRON, copper=_COPPER),
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
