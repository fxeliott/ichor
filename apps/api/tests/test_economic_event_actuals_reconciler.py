"""r144 — tests for FRED ALFRED actuals reconciler.

Covers : title → series mapping (canonical fragments + order priority +
ADR-017 vocabulary) ; fetch_alfred_actual happy / 404 / network /
missing-value paths ; reconcile_actuals filter + skip logic + dry-run +
idempotency ; CLI feature flag gate + arg parsing.

The reconciler mirrors the established collectors/fred.py pattern
(httpx.AsyncClient + structlog graceful-degradation + 0.2s rate-limit
sleep) so most tests use respx for httpx mocking + an in-memory ORM
fixture rather than spinning a full DB.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from ichor_api.services.economic_event_actuals_reconciler import (
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_SETTLE_MINUTES,
    FRED_BASE,
    INTER_REQUEST_SLEEP_SECONDS,
    SERIES_DISPLAY_UNIT,
    TITLE_FRAGMENT_BLOCKED,
    TITLE_FRAGMENT_TO_SERIES,
    ReconcilerResult,
    fetch_alfred_actual,
    map_title_to_series,
    normalize_actual_value,
)
from ichor_api.services.economic_event_surprise import classify_surprise

# ────────────────────── Map title → series fragment tests ──────────────────────


class TestMapTitleToSeries:
    """Exhaustive validation of the TITLE_FRAGMENT_TO_SERIES dispatch."""

    def test_returns_none_for_none_or_empty(self) -> None:
        assert map_title_to_series(None) is None
        assert map_title_to_series("") is None
        assert map_title_to_series("   ") is None or map_title_to_series(
            "   "
        ) == map_title_to_series("   ")  # whitespace stays case-insensitive substring miss

    def test_nfp_maps_to_payems_chg(self) -> None:
        # Multiple FF wordings ; all hit PAYEMS with `units=chg`.
        for title in (
            "Non-Farm Employment Change",
            "Non-Farm Payrolls",
            "Nonfarm Payrolls",
            "non-farm employment change",  # lowercase
            "NON-FARM PAYROLLS",  # uppercase
        ):
            result = map_title_to_series(title)
            assert result is not None, f"NFP variant {title!r} should map"
            series_id, units = result
            assert series_id == "PAYEMS"
            assert units == "chg"

    def test_unemployment_rate_maps_to_unrate_level(self) -> None:
        result = map_title_to_series("Unemployment Rate")
        assert result == ("UNRATE", None)

    def test_core_cpi_matched_before_headline_cpi(self) -> None:
        # ORDER MATTERS in TITLE_FRAGMENT_TO_SERIES — "Core CPI" must
        # be checked before generic "CPI" fragment.
        result = map_title_to_series("Core CPI y/y")
        assert result is not None
        series_id, _ = result
        assert series_id == "CPILFESL", (
            f"Core CPI y/y must map to CPILFESL (Core CPI series), "
            f"got {series_id} — fragment-order discipline broken."
        )

    def test_headline_cpi_distinguished_from_core(self) -> None:
        result = map_title_to_series("CPI y/y")
        assert result is not None
        series_id, units = result
        assert series_id == "CPIAUCSL"
        assert units == "pc1"

    def test_core_pce_maps_to_pcepilfe(self) -> None:
        result = map_title_to_series("Core PCE Price Index m/m")
        assert result is not None
        assert result[0] == "PCEPILFE"

    def test_gdp_quarterly_maps_to_gdpc1_pca(self) -> None:
        # r195 : GDP uses `pca` (compounded annual rate) to match
        # BEA/FF's annualized SAAR convention. `pch` (non-annualized
        # quarterly) understated GDP ~80% vs FF's annualized forecast.
        result = map_title_to_series("GDP q/q")
        assert result == ("GDPC1", "pca")

    def test_initial_claims_maps_to_icsa_level(self) -> None:
        result = map_title_to_series("Unemployment Claims")
        assert result == ("ICSA", None)

    def test_uom_sentiment_revised_takes_priority(self) -> None:
        # Both "Revised UoM Consumer Sentiment" (final) and
        # "UoM Consumer Sentiment" (prelim) share UMCSENT — confirm
        # mapping is stable.
        revised = map_title_to_series("Revised UoM Consumer Sentiment")
        prelim = map_title_to_series("UoM Consumer Sentiment")
        assert revised == ("UMCSENT", None)
        assert prelim == ("UMCSENT", None)

    def test_unknown_title_returns_none(self) -> None:
        # Honest-scope per lesson #37 : ISM / ADP / CCI / unknown
        # vocabulary MUST return None, never fabricate.
        for title in (
            "ISM Manufacturing PMI",
            "ISM Services PMI",
            "ADP Employment Change",
            "Conference Board Consumer Confidence",
            "Tertiary Industry Activity",  # JP, no FRED equivalent
            "S&P Global Manufacturing PMI",  # private survey, not FRED
            "Philly Fed Manufacturing Index",  # FRED has it but not in r144 mapping
            "Foo Bar Baz",
        ):
            assert map_title_to_series(title) is None, (
                f"Unknown title {title!r} must NOT map — honest scope."
            )

    def test_blocked_fragments_returns_none(self) -> None:
        # r144 code-reviewer S1+S2 + trader Y2 fix-cluster — adversarial
        # collision probes : these titles WOULD substring-match the
        # positive dispatch but are SHORT-CIRCUITED by the negative-list
        # to return None (avoiding silent corruption of `actual` via
        # wrong FRED series mapping).
        for title in (
            "Trimmed Mean CPI y/y",  # Cleveland Fed series, NOT CPIAUCSL
            "Median CPI m/m",  # Cleveland Fed series
            "Supercore CPI y/y",  # Atlanta Fed, NOT headline
            "Sticky-Price CPI y/y",  # Atlanta Fed
            "Core Retail Sales m/m",  # ex-autos, NOT RSAFS
            "PCE Price Index Ex-Food m/m",  # variant we explicitly block
            # r144 round-2 post-deploy audit fix — empirical witness
            # caught ADP false-positive matching "non-farm employment
            # change". ADP is private survey (NPPTTL discontinued on
            # FRED) ; NOT the same as BLS PAYEMS.
            "ADP Non-Farm Employment Change",
            "adp non-farm payrolls",
            # BLS productivity stats share "nonfarm" substring with NFP
            # but reference completely different measures.
            "Prelim Nonfarm Productivity q/q",
            "Revised Nonfarm Productivity q/q",
            "Prelim Unit Labor Costs q/q",
            "Revised Unit Labor Costs q/q",
        ):
            assert map_title_to_series(title) is None, (
                f"Blocked title {title!r} must short-circuit to None — "
                "data correctness regression guard (r144 S1+S2+round-2 fix)."
            )

    def test_average_hourly_earnings_maps_to_ahetpi(self) -> None:
        # r144 trader Y2(c) — added in fix-cluster.
        yoy = map_title_to_series("Average Hourly Earnings y/y")
        mom = map_title_to_series("Average Hourly Earnings m/m")
        assert yoy == ("AHETPI", "pc1")
        assert mom == ("AHETPI", "pch")

    def test_fragment_substring_match_handles_impact_suffix(self) -> None:
        # FF event titles sometimes include impact-tier suffixes ;
        # substring matching still finds the canonical fragment.
        result = map_title_to_series("Non-Farm Employment Change (HIGH)")
        assert result is not None
        assert result[0] == "PAYEMS"

    def test_case_insensitive_match(self) -> None:
        assert map_title_to_series("CPI y/y") == map_title_to_series("cpi y/y")
        assert map_title_to_series("cpi Y/Y") == map_title_to_series("CPI Y/Y")


# ────────────────────── TITLE_FRAGMENT_TO_SERIES table invariants ──────────────────────


class TestTitleFragmentTableInvariants:
    """Invariants on the curated dispatch table — guard against drift."""

    def test_table_is_frozen_tuple(self) -> None:
        assert isinstance(TITLE_FRAGMENT_TO_SERIES, tuple), (
            "TITLE_FRAGMENT_TO_SERIES must be a tuple (frozen) so the "
            "mapping cannot be mutated at runtime."
        )

    def test_table_has_at_least_12_distinct_series(self) -> None:
        # Per r144 researcher R59 audit : 12-13 distinct FRED series
        # cover the tier-1 USD events on ForexFactory.
        distinct_series = {sid for _, sid, _ in TITLE_FRAGMENT_TO_SERIES}
        assert len(distinct_series) >= 12, (
            f"Expected at least 12 distinct FRED series in mapping, "
            f"got {len(distinct_series)} : {sorted(distinct_series)}. "
            "Lower count suggests a regression on the r144 coverage."
        )

    def test_all_units_are_canonical_or_none(self) -> None:
        # Valid FRED `units` query param values per docs (subset we use).
        # See https://fred.stlouisfed.org/docs/api/fred/series_observations.html
        allowed_units = {None, "chg", "pch", "pc1", "pca"}
        for fragment, series_id, units in TITLE_FRAGMENT_TO_SERIES:
            assert units in allowed_units, (
                f"Mapping entry ({fragment!r}, {series_id!r}, {units!r}) "
                f"has invalid units value. Allowed : {allowed_units}"
            )

    def test_no_buy_sell_tokens_in_table(self) -> None:
        # ADR-017 boundary — mapping table is source code, must not
        # contain BUY/SELL/LONG/SHORT vocabulary in any fragment.
        forbidden = ("buy", "sell", "long", "short")
        for fragment, _, _ in TITLE_FRAGMENT_TO_SERIES:
            lower = fragment.lower()
            for tok in forbidden:
                assert tok not in lower, (
                    f"ADR-017 violation : fragment {fragment!r} contains "
                    f"forbidden directional token {tok!r}."
                )

    def test_core_cpi_appears_before_generic_cpi(self) -> None:
        # Order discipline : "core cpi" fragments MUST appear BEFORE
        # generic "cpi" fragments so substring match finds Core first.
        positions = {fragment: i for i, (fragment, _, _) in enumerate(TITLE_FRAGMENT_TO_SERIES)}
        # Find first occurrence of "core cpi" and first occurrence of generic "cpi y/y"
        core_idx = next(
            (i for i, (f, _, _) in enumerate(TITLE_FRAGMENT_TO_SERIES) if "core cpi" in f),
            None,
        )
        cpi_idx = positions.get("cpi y/y")
        assert core_idx is not None and cpi_idx is not None
        assert core_idx < cpi_idx, (
            "Order discipline broken : Core CPI fragments must appear "
            "BEFORE generic CPI fragments in TITLE_FRAGMENT_TO_SERIES "
            "so substring match resolves Core first."
        )


# ────────────────────── fetch_alfred_actual unit tests ──────────────────────


@pytest.mark.asyncio
class TestFetchAlfredActual:
    """Mocked httpx tests for the ALFRED HTTP client wrapper."""

    async def test_happy_path_returns_value_string(self) -> None:
        # Mock httpx.AsyncClient.get to return a FRED-shape JSON.
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock(return_value=None)
        mock_response.json = MagicMock(
            return_value={
                "observations": [
                    {
                        "realtime_start": "2026-05-02",
                        "realtime_end": "2026-05-02",
                        "date": "2026-04-01",
                        "value": "180.5",
                    }
                ]
            }
        )
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        result = await fetch_alfred_actual(
            series_id="PAYEMS",
            release_date="2026-05-02",
            api_key="dummy_key",
            client=mock_client,
        )

        assert result == "180.5"
        # Verify the URL + params shape.
        args, kwargs = mock_client.get.call_args
        assert args[0] == f"{FRED_BASE}/series/observations"
        params = kwargs["params"]
        assert params["series_id"] == "PAYEMS"
        assert params["realtime_start"] == "2026-05-02"
        assert params["realtime_end"] == "2026-05-02"
        assert params["file_type"] == "json"
        assert params["api_key"] == "dummy_key"
        # No units → param absent
        assert "units" not in params

    async def test_units_param_passed_through(self) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock(return_value=None)
        mock_response.json = MagicMock(return_value={"observations": [{"value": "3.2"}]})
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        await fetch_alfred_actual(
            series_id="CPIAUCSL",
            release_date="2026-04-15",
            api_key="dummy",
            client=mock_client,
            units="pc1",
        )
        params = mock_client.get.call_args[1]["params"]
        assert params["units"] == "pc1"

    async def test_returns_none_on_empty_observations(self) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock(return_value=None)
        mock_response.json = MagicMock(return_value={"observations": []})
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        result = await fetch_alfred_actual(
            series_id="PAYEMS",
            release_date="2026-05-02",
            api_key="dummy",
            client=mock_client,
        )
        assert result is None

    async def test_returns_none_on_fred_missing_marker(self) -> None:
        # FRED uses "." as the missing-value marker.
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock(return_value=None)
        mock_response.json = MagicMock(return_value={"observations": [{"value": "."}]})
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        result = await fetch_alfred_actual(
            series_id="PAYEMS",
            release_date="2026-05-02",
            api_key="dummy",
            client=mock_client,
        )
        assert result is None

    async def test_returns_none_on_http_error(self) -> None:
        # 404 / 5xx / network error all funnel to None via broad except.
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "404 Not Found",
                request=MagicMock(),
                response=MagicMock(status_code=404),
            )
        )
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        result = await fetch_alfred_actual(
            series_id="NONEXISTENT",
            release_date="2026-05-02",
            api_key="dummy",
            client=mock_client,
        )
        assert result is None

    async def test_returns_none_on_network_error(self) -> None:
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("network down"))

        result = await fetch_alfred_actual(
            series_id="PAYEMS",
            release_date="2026-05-02",
            api_key="dummy",
            client=mock_client,
        )
        assert result is None

    async def test_returns_string_form_even_when_numeric_input(self) -> None:
        # FRED API returns value as string ; we MUST pass through as
        # string (no parseFloat) so `economic_events.actual` String(64)
        # column stores the raw FF-style text shape unchanged.
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock(return_value=None)
        mock_response.json = MagicMock(return_value={"observations": [{"value": "3.20"}]})
        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        result = await fetch_alfred_actual(
            series_id="CPIAUCSL",
            release_date="2026-04-15",
            api_key="dummy",
            client=mock_client,
            units="pc1",
        )
        assert result == "3.20"
        assert isinstance(result, str)


# ────────────────────── ReconcilerResult dataclass tests ──────────────────────


class TestReconcilerResult:
    """ReconcilerResult is frozen — counters cannot be mutated post-construction."""

    def test_is_frozen(self) -> None:
        r = ReconcilerResult(
            examined=10,
            updated=7,
            skipped_unmapped=2,
            skipped_no_scheduled_at=0,
            skipped_fetch_failed=1,
            skipped_no_value=0,
        )
        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            r.examined = 99  # type: ignore[misc]

    def test_default_construction_explicit_required(self) -> None:
        # All 6 fields are required positional/kwargs ; no defaults so
        # caller cannot accidentally omit a counter. (r144 code-reviewer
        # N6 — added skipped_no_scheduled_at counter so total = 6.)
        with pytest.raises(TypeError):
            ReconcilerResult()  # type: ignore[call-arg]


class TestTitleFragmentBlockedTable:
    """r144 code-reviewer S1+S2 fix — negative-list invariants."""

    def test_blocked_is_frozen_tuple(self) -> None:
        assert isinstance(TITLE_FRAGMENT_BLOCKED, tuple), (
            "TITLE_FRAGMENT_BLOCKED must be a tuple (frozen)."
        )

    def test_blocked_has_at_least_5_entries(self) -> None:
        # Document the explicit known collisions ; lower count suggests
        # a regression on the r144 S1+S2 fix-cluster.
        assert len(TITLE_FRAGMENT_BLOCKED) >= 5, (
            f"TITLE_FRAGMENT_BLOCKED has {len(TITLE_FRAGMENT_BLOCKED)} "
            "entries ; expected at least 5 (trimmed mean cpi + median "
            "cpi + supercore cpi + sticky-price cpi + core retail sales)."
        )

    def test_no_buy_sell_tokens_in_blocked_list(self) -> None:
        forbidden = ("buy", "sell", "long", "short")
        for fragment in TITLE_FRAGMENT_BLOCKED:
            lower = fragment.lower()
            for tok in forbidden:
                assert tok not in lower, (
                    f"ADR-017 violation : blocked fragment {fragment!r} "
                    f"contains forbidden directional token {tok!r}."
                )


# ────────────────────── Public constants pinned ──────────────────────


class TestModuleConstants:
    """Pin key constants to detect accidental regressions."""

    def test_fred_base_url(self) -> None:
        # Shared with collectors/fred.py — verified empirically at
        # fred.py:21 per code-explorer r144 audit.
        assert FRED_BASE == "https://api.stlouisfed.org/fred"

    def test_inter_request_sleep_matches_fred_pattern(self) -> None:
        # Matches collectors/fred.py:backfill_history 0.2s gap (free-tier
        # 120 req/min ceiling = 5 req/s ; 0.2s sleep stays at exactly that
        # ceiling without bursting).
        assert INTER_REQUEST_SLEEP_SECONDS == 0.2

    def test_default_lookback_days(self) -> None:
        assert DEFAULT_LOOKBACK_DAYS == 14

    def test_default_settle_minutes(self) -> None:
        assert DEFAULT_SETTLE_MINUTES == 15


# ────────────────────── normalize_actual_value (r195) ──────────────────────


class TestNormalizeActualValue:
    """r195 — FRED-native → ForexFactory display-convention normalization.

    The FF collector stores forecast/previous WITH unit suffixes ("65K",
    "1.40M", "0.3%") but FRED returns bare numerics on its native scale.
    For level series this made `actual` incomparable to `forecast` (NFP
    "115" MEANS 115K) and unreadable on the briefing ("0.40284").
    """

    def test_payems_chg_thousands_to_k(self) -> None:
        # FRED PAYEMS chg returns thousands-of-persons ; "115" = 115K.
        assert normalize_actual_value("115", "PAYEMS", "chg") == "115K"

    def test_payems_negative_chg_sign_preserved(self) -> None:
        assert normalize_actual_value("-12", "PAYEMS", "chg") == "-12K"

    def test_payems_decimal_thousands(self) -> None:
        assert normalize_actual_value("250.0", "PAYEMS", "chg") == "250K"

    def test_permit_thousands_to_m(self) -> None:
        # FRED PERMIT is thousands-of-units ; "1400" = 1.40M.
        assert normalize_actual_value("1400", "PERMIT", None) == "1.40M"

    def test_housing_starts_thousands_to_m(self) -> None:
        assert normalize_actual_value("1350", "HOUST", None) == "1.35M"

    def test_jolts_thousands_to_m(self) -> None:
        # The empirical DB anomaly : "6866" was shown raw ; FF says ~6.86M.
        assert normalize_actual_value("6866", "JTSJOL", None) == "6.87M"

    def test_icsa_persons_to_k(self) -> None:
        # ICSA is reported in base persons (215000), FF shows "215K".
        assert normalize_actual_value("215000", "ICSA", None) == "215K"

    def test_unrate_pct_level_gets_suffix(self) -> None:
        assert normalize_actual_value("4.3", "UNRATE", None) == "4.3%"

    def test_dfedtaru_pct_level_preserves_precision(self) -> None:
        assert normalize_actual_value("5.50", "DFEDTARU", None) == "5.50%"

    def test_pch_rounds_to_1dp_with_pct(self) -> None:
        # The empirical DB anomaly : Core CPI m/m "0.37646" → "0.4%".
        assert normalize_actual_value("0.37646", "CPILFESL", "pch") == "0.4%"

    def test_pc1_rounds_to_1dp_with_pct(self) -> None:
        assert normalize_actual_value("3.77925", "CPIAUCSL", "pc1") == "3.8%"

    def test_gdp_pca_annualized_rounds(self) -> None:
        # GDPC1 pca 2026-Q1 = 1.62114 → "1.6%" (comparable to FF "2.0%").
        assert normalize_actual_value("1.62114", "GDPC1", "pca") == "1.6%"

    def test_negative_pct(self) -> None:
        assert normalize_actual_value("-0.12", "RSAFS", "pch") == "-0.1%"

    def test_half_up_not_bankers(self) -> None:
        # 0.25 → "0.3%" (half-up, not banker's 0.2).
        assert normalize_actual_value("0.25", "CPIAUCSL", "pch") == "0.3%"

    def test_umcsent_index_verbatim(self) -> None:
        # Consumer-sentiment index level — FF shows it unit-less too.
        assert normalize_actual_value("52.2", "UMCSENT", None) == "52.2"

    def test_unparseable_returned_stripped(self) -> None:
        assert normalize_actual_value("  n/a ", "UMCSENT", None) == "n/a"

    def test_series_display_unit_table_is_dict(self) -> None:
        assert isinstance(SERIES_DISPLAY_UNIT, dict)
        # The four count-in-thousands level/chg series + the two pct
        # levels are pinned ; absence (e.g. UMCSENT) means verbatim.
        assert SERIES_DISPLAY_UNIT["PAYEMS"] == "count_thousands"
        assert SERIES_DISPLAY_UNIT["ICSA"] == "count_persons"
        assert SERIES_DISPLAY_UNIT["UNRATE"] == "pct_level"
        assert "UMCSENT" not in SERIES_DISPLAY_UNIT


class TestNormalizeFixesSurpriseComparison:
    """r195 end-to-end : the normalized actual makes the r141 surprise
    classifier compare like-for-like, retiring the r146
    `unit_scale_mismatch` band-aid for level series with a real magnitude.
    """

    def test_nfp_beat_classifies_cleanly_after_normalization(self) -> None:
        # BEFORE r195 : "115" vs "65K" → 115 vs 65000 → 100x heuristic
        # suppressed magnitude_pct + flagged unit_scale_mismatch.
        # AFTER : "115K" vs "65K" → a clean +76.9% beat.
        normalized = normalize_actual_value("115", "PAYEMS", "chg")
        assert normalized == "115K"
        cls = classify_surprise(
            actual=normalized,
            consensus="65K",
            forecast_min=None,
            forecast_max=None,
        )
        assert cls.magnitude_pct is not None
        assert cls.magnitude_pct > 0  # a beat
        assert "unit_scale_mismatch" not in cls.parse_failures

    def test_jolts_no_longer_1000x_mismatch(self) -> None:
        normalized = normalize_actual_value("6866", "JTSJOL", None)
        assert normalized == "6.87M"
        cls = classify_surprise(
            actual=normalized,
            consensus="6.86M",
            forecast_min=None,
            forecast_max=None,
        )
        assert cls.magnitude_pct is not None
        assert "unit_scale_mismatch" not in cls.parse_failures

    def test_gdp_pca_modest_miss_not_phantom(self) -> None:
        # GDP actual 1.6% vs forecast 2.0% → a modest miss (~-20%), NOT
        # the ~-80% phantom from the old non-annualized 0.4%.
        normalized = normalize_actual_value("1.62114", "GDPC1", "pca")
        assert normalized == "1.6%"
        cls = classify_surprise(
            actual=normalized,
            consensus="2.0%",
            forecast_min=None,
            forecast_max=None,
        )
        assert cls.magnitude_pct is not None
        assert -40.0 < cls.magnitude_pct < 0.0
