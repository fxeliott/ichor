"""S05 / Chantier E slice-1 tests — ``services/technical_analysis.py`` (ADR-113).

Pins the pure-core contract against the codified methodology
(docs/METHODOLOGIE_TECHNIQUE_ELIOT.md) :
- H1 aggregation : closed candles only, gappy hours dropped
- candle grammar : bougie pleine (corps > somme des mèches) vs incertitude
- poussée segmentation : incertitude attaches, opposite pleine splits
- trend read : continuation vs retournement potentiel (poussées décroissantes
  + contraires croissantes / anomalie de rôle)
- NY origin zones N1/N2 (previous completed session, Paris window) + 3-tier
  retest band orientation
- golden zone 0,5-0,618 of the latest nette push
- honest absence (None) below the H1 minimum
- rendered prose : FR vocabulary, ADR-017 boundary (no order tokens)

Doctrine #5 pure-module discipline : synthetic bars only, no DB.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

# ADR-017 boundary checked against the CANONICAL filter — never a local copy
# (adr017_filter.py:50-54 : "any other module that ships its own copy is a P0
# doctrinal regression" ; review PR #234 M2).
from ichor_api.services.adr017_filter import is_adr017_clean
from ichor_api.services.london_session import Bar
from ichor_api.services.technical_analysis import (
    H1Candle,
    Push,
    aggregate_hourly,
    classify_candle,
    compute_day_open_read,
    compute_technical_reading,
    detect_ny_origin_zones,
    golden_zone_of_latest_push,
    ny_window_utc,
    read_trend,
    render_technical_reading_block,
    segment_pushes,
)

# Fixed anchor : Wednesday 2026-06-10 (Paris = UTC+2, summer). NY window
# 13h-20h Paris = 11:00-18:00 UTC ; origin window ends 16h Paris = 14:00 UTC.
_SESSION_DAY = datetime(2026, 6, 10, tzinfo=UTC)
_NOW = datetime(2026, 6, 11, 9, 0, tzinfo=UTC)  # Thursday 11h Paris


def _hour_bars(
    hour_utc: datetime, o: float, h: float, lo: float, c: float, n: int = 60
) -> list[Bar]:
    """n 1-min bars aggregating to an H1 candle with the given OHLC."""
    bars: list[Bar] = []
    for i in range(n):
        ts = hour_utc + timedelta(minutes=i)
        if i == 0:
            bars.append(Bar(ts=ts, open=o, high=max(o, c), low=min(o, c), close=c))
        elif i == 1:
            bars.append(Bar(ts=ts, open=c, high=h, low=c, close=c))
        elif i == 2:
            bars.append(Bar(ts=ts, open=c, high=c, low=lo, close=c))
        else:
            bars.append(Bar(ts=ts, open=c, high=c, low=c, close=c))
    return bars


def _candle(hour_utc: datetime, o: float, h: float, lo: float, c: float) -> H1Candle:
    return H1Candle(ts_open=hour_utc, open=o, high=h, low=lo, close=c, bar_count=60)


def _scenario_bars() -> list[Bar]:
    """Filler day (06-09) + controlled NY session (06-10) + 06-11 morning."""
    bars: list[Bar] = []
    # Filler 06-09 : 24 alternating mild pleine candles around 1.1000 so the
    # H1 minimum (24) is met without polluting the 06-10 session pushes.
    base = datetime(2026, 6, 9, 0, 0, tzinfo=UTC)
    px = 1.1000
    for i in range(24):
        hour = base + timedelta(hours=i)
        if i % 2 == 0:
            bars += _hour_bars(hour, px, px + 0.0011, px - 0.0001, px + 0.0010)
            px += 0.0010
        else:
            bars += _hour_bars(hour, px, px + 0.0001, px - 0.0011, px - 0.0010)
            px -= 0.0010
    # 06-10 pre-session : a clean pleine haussière at 10:00 UTC so the session
    # down-push opens a NEW segment at 12:00 UTC (14h Paris, inside 13h-16h).
    d = _SESSION_DAY
    bars += _hour_bars(d.replace(hour=10), 1.0990, 1.1002, 1.0989, 1.1000)
    bars += _hour_bars(d.replace(hour=11), 1.1000, 1.1010, 1.0995, 1.1002)  # incertitude
    bars += _hour_bars(d.replace(hour=12), 1.1002, 1.1004, 1.0978, 1.0980)  # pleine baissière
    bars += _hour_bars(d.replace(hour=13), 1.0980, 1.0982, 1.0948, 1.0950)  # pleine baissière
    bars += _hour_bars(d.replace(hour=14), 1.0950, 1.0952, 1.0928, 1.0930)  # pleine baissière
    bars += _hour_bars(d.replace(hour=15), 1.0930, 1.0940, 1.0920, 1.0932)  # incertitude (stop)
    bars += _hour_bars(d.replace(hour=16), 1.0932, 1.0962, 1.0930, 1.0960)  # pleine haussière
    bars += _hour_bars(d.replace(hour=17), 1.0960, 1.0982, 1.0958, 1.0980)  # pleine haussière
    # 06-11 morning (day-open read ; Paris day opens 22:00 UTC on 06-10).
    bars += _hour_bars(datetime(2026, 6, 11, 7, 0, tzinfo=UTC), 1.0980, 1.0992, 1.0975, 1.0990)
    bars += _hour_bars(datetime(2026, 6, 11, 8, 0, tzinfo=UTC), 1.0990, 1.1000, 1.0988, 1.0995)
    return bars


class TestAggregateHourly:
    def test_excludes_current_open_hour(self) -> None:
        hour = _NOW.replace(minute=0)
        bars = _hour_bars(hour, 1.1, 1.2, 1.0, 1.15)
        assert aggregate_hourly(bars, now_utc=_NOW) == []

    def test_drops_gappy_hours(self) -> None:
        hour = datetime(2026, 6, 10, 5, 0, tzinfo=UTC)
        bars = _hour_bars(hour, 1.1, 1.2, 1.0, 1.15, n=5)  # < _MIN_BARS_PER_HOUR
        assert aggregate_hourly(bars, now_utc=_NOW) == []

    def test_aggregates_ohlc(self) -> None:
        hour = datetime(2026, 6, 10, 5, 0, tzinfo=UTC)
        bars = _hour_bars(hour, 1.1000, 1.1050, 1.0950, 1.1020)
        [c] = aggregate_hourly(bars, now_utc=_NOW)
        assert (c.open, c.high, c.low, c.close) == (1.1000, 1.1050, 1.0950, 1.1020)


class TestCandleGrammar:
    def test_pleine_haussiere(self) -> None:
        c = _candle(_SESSION_DAY, 1.0, 1.0105, 0.9995, 1.01)  # body .01 > wicks .001
        assert classify_candle(c) == "pleine_haussiere"

    def test_pleine_baissiere(self) -> None:
        c = _candle(_SESSION_DAY, 1.01, 1.0105, 0.9995, 1.0)
        assert classify_candle(c) == "pleine_baissiere"

    def test_incertitude_wick_dominant(self) -> None:
        c = _candle(_SESSION_DAY, 1.0, 1.02, 0.98, 1.001)  # wicks >> body
        assert classify_candle(c) == "incertitude"

    def test_incertitude_zero_range(self) -> None:
        c = _candle(_SESSION_DAY, 1.0, 1.0, 1.0, 1.0)
        assert classify_candle(c) == "incertitude"


class TestSegmentPushes:
    def test_opposite_pleine_splits_segments(self) -> None:
        h = datetime(2026, 6, 10, 0, 0, tzinfo=UTC)
        candles = [
            _candle(h, 1.0000, 1.0105, 0.9999, 1.0100),
            _candle(h + timedelta(hours=1), 1.0100, 1.0205, 1.0099, 1.0200),
            _candle(h + timedelta(hours=2), 1.0200, 1.0201, 1.0095, 1.0100),
        ]
        pushes = segment_pushes(candles)
        assert [p.direction for p in pushes] == ["haussiere", "baissiere"]

    def test_incertitude_attaches_to_current_push(self) -> None:
        h = datetime(2026, 6, 10, 0, 0, tzinfo=UTC)
        candles = [
            _candle(h, 1.0000, 1.0105, 0.9999, 1.0100),
            _candle(h + timedelta(hours=1), 1.0100, 1.0140, 1.0080, 1.0105),  # incertitude
            _candle(h + timedelta(hours=2), 1.0105, 1.0215, 1.0104, 1.0210),
        ]
        pushes = segment_pushes(candles)
        assert len(pushes) == 1
        assert pushes[0].n_candles == 3
        assert pushes[0].quality == "nette"  # 2/3 pleines dans le sens


class TestReadTrend:
    def _push(self, d: str, mag: float, q: str, i: int) -> Push:
        start = datetime(2026, 6, 10, i, 0, tzinfo=UTC)
        sp = 1.1
        ep = sp + mag if d == "haussiere" else sp - mag
        return Push(
            direction=d,  # type: ignore[arg-type]
            start_ts=start,
            end_ts=start,
            start_price=sp,
            end_price=ep,
            high=max(sp, ep),
            low=min(sp, ep),
            n_candles=3,
            n_full_in_direction=2,
            quality=q,  # type: ignore[arg-type]
        )

    def test_retournement_on_weakening_and_counter_growth(self) -> None:
        pushes = [
            self._push("baissiere", 0.0100, "nette", 0),
            self._push("haussiere", 0.0020, "structuree", 1),
            self._push("baissiere", 0.0050, "nette", 2),
            self._push("haussiere", 0.0060, "nette", 3),
        ]
        t = read_trend(pushes)
        assert t.state == "retournement_potentiel_haussier"
        assert t.dominant_direction == "baissiere"

    def test_continuation_when_last_push_dominant(self) -> None:
        pushes = [
            self._push("baissiere", 0.0050, "nette", 0),
            self._push("haussiere", 0.0010, "structuree", 1),
            self._push("baissiere", 0.0080, "nette", 2),
        ]
        t = read_trend(pushes)
        assert t.state == "continuation_baissiere"

    def test_indecis_on_empty(self) -> None:
        assert read_trend([]).state == "indecis"

    def test_role_anomaly_alone_triggers_retournement(self) -> None:
        """METHODOLOGIE §5.1 : l'anomalie de rôle est le détecteur PRINCIPAL,
        autonome — sans essoufflement ni croissance des contraires (PR #234 M1)."""
        pushes = [
            self._push("baissiere", 0.0060, "nette", 0),
            self._push("haussiere", 0.0070, "structuree", 1),
            self._push("baissiere", 0.0080, "nette", 2),  # dom growing (no weakening)
            self._push("haussiere", 0.0060, "nette", 3),  # counter NOT growing, but NETTE
        ]
        t = read_trend(pushes)
        assert t.dominant_direction == "baissiere"
        assert t.state == "retournement_potentiel_haussier"
        assert "anomalie de rôle" in t.rationale_fr


class TestNyWindow:
    def test_winter_dst_paris(self) -> None:
        """13h-20h Paris in January = 12:00-19:00 UTC (Paris = UTC+1)."""
        open_utc, origin_end_utc, close_utc = ny_window_utc(date(2026, 1, 14))
        assert open_utc == datetime(2026, 1, 14, 12, 0, tzinfo=UTC)
        assert origin_end_utc == datetime(2026, 1, 14, 15, 0, tzinfo=UTC)
        assert close_utc == datetime(2026, 1, 14, 19, 0, tzinfo=UTC)


class TestNyOriginZones:
    def test_n1_and_n2_from_previous_completed_session(self) -> None:
        candles = aggregate_hourly(_scenario_bars(), now_utc=_NOW)
        zones, session_date = detect_ny_origin_zones(candles, now_utc=_NOW)
        assert session_date == _SESSION_DAY.date()
        levels = {(z.level, z.side) for z in zones}
        assert ("N1", "vendeuse") in levels
        assert ("N2", "acheteuse") in levels
        n1 = next(z for z in zones if z.level == "N1")
        # Origin candle = the 11:00 UTC incertitude at the top of the move
        # (leading incertitude attaches to the push — tolerated at push start,
        # METHODOLOGIE §3) : zone from its body top 1.1002 (clôture) up to its
        # wick high 1.1010 (« extensible jusqu'au haut de la mèche », [T-B]).
        assert abs(n1.bottom - 1.1002) < 1e-9
        assert abs(n1.top - 1.1010) < 1e-9

    def test_retest_band_orientation(self) -> None:
        """Valid retest = the half of the zone on the price-approach side.

        T-B demonstrates it on an origine ACHETEUSE (price falls into the
        zone from above → « entre le haut et le milieu », EXPLICITE) ; the
        vendeuse mirror (price rises from below → bas/milieu) is INFÉRÉE.
        """
        candles = aggregate_hourly(_scenario_bars(), now_utc=_NOW)
        zones, _ = detect_ny_origin_zones(candles, now_utc=_NOW)
        for z in zones:
            mid = (z.top + z.bottom) / 2
            if z.side == "acheteuse":
                assert (z.retest_low, z.retest_high) == (mid, z.top)
            else:
                assert (z.retest_low, z.retest_high) == (z.bottom, mid)

    def test_honest_absence_without_completed_session(self) -> None:
        zones, session_date = detect_ny_origin_zones([], now_utc=_NOW)
        assert zones == [] and session_date is None

    def test_in_progress_session_excluded(self) -> None:
        """now inside the 06-10 session → the read must come from 06-09
        (PR #234 m6 : the in-progress session is never read)."""
        now = datetime(2026, 6, 10, 15, 0, tzinfo=UTC)  # 17h Paris, session live
        candles = aggregate_hourly(_scenario_bars(), now_utc=now)
        zones, session_date = detect_ny_origin_zones(candles, now_utc=now)
        assert session_date == date(2026, 6, 9)
        assert all(z.session_date == date(2026, 6, 9) for z in zones)


class TestGoldenZone:
    def test_levels_of_latest_nette_push(self) -> None:
        h = datetime(2026, 6, 10, 0, 0, tzinfo=UTC)
        candles = [
            _candle(h, 1.0000, 1.0105, 0.9999, 1.0100),
            _candle(h + timedelta(hours=1), 1.0100, 1.0205, 1.0099, 1.0200),
        ]
        g = golden_zone_of_latest_push(segment_pushes(candles), current_price=1.0150)
        assert g is not None
        # Push 1.0000 → 1.0200 : 0.5 = 1.0100, 0.618 = 1.00764.
        assert abs(g.zone_high - 1.0100) < 1e-9
        assert abs(g.zone_low - 1.00764) < 1e-9
        assert g.price_position == "au_dessus"

    def test_none_without_nette_push(self) -> None:
        assert golden_zone_of_latest_push([], current_price=1.0) is None

    def test_levels_of_bearish_push(self) -> None:
        """Retracement of a DOWN push sits ABOVE its end (PR #234 m6 : pin the
        sign so a regression cannot pass CI silently)."""
        h = datetime(2026, 6, 10, 0, 0, tzinfo=UTC)
        candles = [
            _candle(h, 1.0200, 1.0201, 1.0095, 1.0100),
            _candle(h + timedelta(hours=1), 1.0100, 1.0101, 0.9995, 1.0000),
        ]
        g = golden_zone_of_latest_push(segment_pushes(candles), current_price=1.0050)
        assert g is not None
        assert g.push_direction == "baissiere"
        # Push 1.0200 → 1.0000 : 0.5 = 1.0100, 0.618 = 1.01236.
        assert abs(g.zone_low - 1.0100) < 1e-9
        assert abs(g.zone_high - 1.01236) < 1e-9
        assert g.price_position == "en_dessous"


class TestDayOpenRead:
    def test_excursions_since_paris_midnight(self) -> None:
        d = compute_day_open_read(_scenario_bars(), now_utc=_NOW)
        assert d is not None
        assert d.open_price == 1.0980
        assert d.upside_excursion > 0
        assert d.last_price == 1.0995


class TestFullReading:
    def test_reading_populated_on_scenario(self) -> None:
        r = compute_technical_reading(_scenario_bars(), asset="EUR_USD", now_utc=_NOW)
        assert r is not None
        assert r.h1_candle_count >= 24
        assert r.origin_zones, "expected N1/N2 zones from the 06-10 NY session"
        assert r.golden_zone is not None
        assert r.day_open is not None
        # Deterministic pin (PR #234 M1) : the 06-10 session ends on a NETTE
        # counter-push (16h-17h bulls) against a baissière-dominant window →
        # anomalie de rôle → retournement potentiel haussier.
        assert r.trend.state == "retournement_potentiel_haussier"

    def test_honest_absence_below_minimum(self) -> None:
        hour = datetime(2026, 6, 10, 5, 0, tzinfo=UTC)
        bars = _hour_bars(hour, 1.1, 1.2, 1.0, 1.15)
        assert compute_technical_reading(bars, asset="EUR_USD", now_utc=_NOW) is None


class TestRender:
    def test_populated_prose_is_adr017_clean_and_french(self) -> None:
        r = compute_technical_reading(_scenario_bars(), asset="EUR_USD", now_utc=_NOW)
        md, sources = render_technical_reading_block(r, "EUR_USD")
        assert is_adr017_clean(md), "rendered prose must pass the CANONICAL ADR-017 filter"
        assert "Lecture technique" in md
        assert "Élan H1" in md
        assert "Origine" in md
        assert "ADR-017" in md
        # PR #234 m1 : accent-free Literal identifiers must never leak.
        assert "haussiere" not in md and "baissiere" not in md
        assert any(s.startswith("polygon_intraday:EUR_USD@") for s in sources)
        assert "methodologie:ADR-113" in sources

    def test_absence_prose_is_adr017_clean(self) -> None:
        md, sources = render_technical_reading_block(None, "GBP_USD")
        assert is_adr017_clean(md)
        assert "absence honnête" in md
        assert sources == ["technical_reading:GBP_USD:absent"]

    def test_proxy_caveat_for_spx(self) -> None:
        r = compute_technical_reading(_scenario_bars(), asset="SPX500_USD", now_utc=_NOW)
        md, _ = render_technical_reading_block(r, "SPX500_USD")
        assert "SPY" in md
