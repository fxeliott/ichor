"""Unit tests for `_FRED_SERIES_MAX_AGE_DAYS` registry + `_max_age_days_for`
helper (round-37 r35-audit-gap closure).

The registry replaces the r34/r35 explicit `max_age_days=N` overrides
scattered throughout `_section_eur_specific` with a single canonical
source of truth. Tests verify :
  1. Daily series (DGS10) fall back to default 14d.
  2. Monthly series (IRLTLT01ITM156N + Germany/Italy/Japan/UK 10y)
     all resolve to 120d.
  3. Explicit kwarg `override` wins over registry.
  4. Unknown series ID falls back to default 14d (NOT a crash).
  5. The 4 ADR-090 step-4 monthly series are present in registry.
  6. `_FRED_DEFAULT_MAX_AGE_DAYS` is 14 (calibrated for DAILY series).
"""

from __future__ import annotations

from ichor_api.services.data_pool import (
    _FRED_DEFAULT_MAX_AGE_DAYS,
    _FRED_SERIES_MAX_AGE_DAYS,
    _max_age_days_for,
)

# ──────────────────────── default vs registry ────────────────────────


def test_default_is_14_days_for_daily_series() -> None:
    """_FRED_DEFAULT_MAX_AGE_DAYS pin = 14 (catches refactor)."""
    assert _FRED_DEFAULT_MAX_AGE_DAYS == 14


def test_unknown_series_falls_back_to_default() -> None:
    """Series ID not in registry → 14 days (DAILY-calibrated)."""
    assert _max_age_days_for("UNKNOWN_SERIES_XYZ") == 14


def test_daily_series_dgs10_not_in_registry() -> None:
    """DGS10 (daily Treasury 10Y) does NOT need a registry entry —
    its 14d default suits its daily refresh."""
    assert "DGS10" not in _FRED_SERIES_MAX_AGE_DAYS
    assert _max_age_days_for("DGS10") == 14


# ──────────────────────── monthly OECD series ────────────────────────


def test_italy_10y_monthly_resolves_to_120_days() -> None:
    """ADR-090 step-4 r34+r35 : Italy 10Y monthly (BTP-Bund spread)
    needs 120-day max-age to survive OECD 1-month publication lag +
    occasional revisions."""
    assert _FRED_SERIES_MAX_AGE_DAYS["IRLTLT01ITM156N"] == 120
    assert _max_age_days_for("IRLTLT01ITM156N") == 120


def test_germany_japan_uk_australia_10y_monthly_all_120_days() -> None:
    """The 4 other OECD foreign-10y series mirror Italy 10Y.
    Australia added round-46 ADR-092 §T1.AUD-3 (AUD-USD GAP-A 5/5)."""
    for series_id in (
        "IRLTLT01DEM156N",
        "IRLTLT01JPM156N",
        "IRLTLT01GBM156N",
        "IRLTLT01AUM156N",
    ):
        assert _FRED_SERIES_MAX_AGE_DAYS[series_id] == 120
        assert _max_age_days_for(series_id) == 120


def test_imf_pinkbook_composite_monthly_series_60_days() -> None:
    """Round-46 ADR-092 §T1.AUD-1 + §T1.AUD-2 ship : 3 IMF World Bank
    PinkBook composite series at 60d max-age (acceptable since PinkBook
    publishes early-month, vs OECD MEI mid-month at 120d). Empirical
    cadence validated post-deploy ; if silent-skip emerges, bump to 90d
    or 120d in a follow-up hygiene round (code-reviewer r46 M2 caveat)."""
    for series_id in (
        "MYAGM2CNM189N",  # China M2 broad-money
        "PIORECRUSDM",  # Global Iron Ore Price Index
        "PCOPPUSDM",  # Global Copper Price Index
    ):
        assert _FRED_SERIES_MAX_AGE_DAYS[series_id] == 60
        assert _max_age_days_for(series_id) == 60


def test_oecd_cli_series_all_120_days() -> None:
    """OECD Composite Leading Indicators are monthly with same lag."""
    for series_id in (
        "USALOLITOAASTSAM",
        "G7LOLITOAASTSAM",
        "DEULOLITOAASTSAM",
        "EA19LOLITOAASTSAM",
    ):
        assert _max_age_days_for(series_id) == 120


def test_recession_indicator_usrec_365_days() -> None:
    """NBER Recession Indicator (USREC) updates only at recession
    turning points — months between updates. 365d ceiling."""
    assert _max_age_days_for("USREC") == 365


# ──────────────────────── explicit override precedence ────────────────


def test_explicit_override_wins_over_registry() -> None:
    """Caller passing explicit max_age_days=N bypasses registry.
    Useful for cold-start backfill diagnostics or one-off audits."""
    # Italy 10Y is normally 120d in registry, but caller forces 30d
    assert _max_age_days_for("IRLTLT01ITM156N", override=30) == 30


def test_explicit_override_works_for_unknown_series() -> None:
    """Override works regardless of registry membership."""
    assert _max_age_days_for("UNKNOWN_XYZ", override=60) == 60


def test_explicit_override_zero_returns_zero_not_default() -> None:
    """Edge case : override=0 is a valid (if useless) value. Don't
    let it fall through to the default — that would surprise the
    caller. Note : override=None falls through, override=0 does not."""
    assert _max_age_days_for("DGS10", override=0) == 0


# ──────────────────────── registry sanity ────────────────────────


def test_registry_has_no_negative_values() -> None:
    """All registry entries must be positive integers — negative
    max-age would always return empty results."""
    for series_id, days in _FRED_SERIES_MAX_AGE_DAYS.items():
        assert days > 0, f"Series {series_id!r} has non-positive max_age_days={days}"


def test_registry_monthly_series_are_at_least_30_days() -> None:
    """OECD/FRED monthly series have at minimum 30-day publication
    lag. Registry entries below 30 indicate a misclassification."""
    monthly_series = (
        "IRLTLT01DEM156N",
        "IRLTLT01ITM156N",
        "IRLTLT01JPM156N",
        "IRLTLT01GBM156N",
        "IRLTLT01AUM156N",  # round-46 ADR-092 §T1.AUD-3
        "MYAGM2CNM189N",  # round-46 ADR-092 §T1.AUD-1 (IMF PinkBook)
        "PIORECRUSDM",  # round-46 ADR-092 §T1.AUD-2 (IMF PinkBook)
        "PCOPPUSDM",  # round-46 ADR-092 §T1.AUD-2 (IMF PinkBook)
        "UMCSENT",
        "CIVPART",
        "AHETPI",
        "M2SL",
        "INDPRO",
        "CFNAI",
    )
    for series_id in monthly_series:
        assert _FRED_SERIES_MAX_AGE_DAYS[series_id] >= 30, (
            f"Series {series_id!r} is monthly but registry max_age_days="
            f"{_FRED_SERIES_MAX_AGE_DAYS[series_id]} is too tight."
        )


def test_registry_size_lower_bound() -> None:
    """Round-37 r35-audit-gap closure : 4 ADR-090 step-4 foreign 10Y
    + 7 OECD CLI + 5+ macro monthlies + 3 Fed H.4.1 weeklies +
    nowcasts + Fed funds = at minimum 20 entries. Bumping the
    minimum guards against an accidental empty-dict regression."""
    assert len(_FRED_SERIES_MAX_AGE_DAYS) >= 20, (
        f"Registry size {len(_FRED_SERIES_MAX_AGE_DAYS)} is suspiciously "
        "small. Did the dict get accidentally reset to {} ?"
    )
