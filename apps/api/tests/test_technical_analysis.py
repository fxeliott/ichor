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
    candle_intention,
    classify_candle,
    compute_daily_read,
    compute_day_open_read,
    compute_technical_reading,
    detect_ny_origin_zones,
    detect_structure_reversals_n3,
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

    def test_min_bars_per_hour_boundary(self) -> None:
        """Pin the exact _MIN_BARS_PER_HOUR=20 threshold : n=20 kept, n=19
        dropped (the prior test used n=5, far from the edge — S05 M7)."""
        hour = datetime(2026, 6, 10, 5, 0, tzinfo=UTC)
        assert len(aggregate_hourly(_hour_bars(hour, 1.1, 1.2, 1.0, 1.15, n=20), now_utc=_NOW)) == 1
        assert aggregate_hourly(_hour_bars(hour, 1.1, 1.2, 1.0, 1.15, n=19), now_utc=_NOW) == []


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

    def test_continuation_haussiere(self) -> None:
        """Miroir haussier de la continuation (S05 re-fire M7)."""
        pushes = [
            self._push("haussiere", 0.0050, "nette", 0),
            self._push("baissiere", 0.0010, "structuree", 1),
            self._push("haussiere", 0.0080, "nette", 2),
        ]
        t = read_trend(pushes)
        assert t.state == "continuation_haussiere"
        assert t.dominant_direction == "haussiere"

    def test_retournement_potentiel_baissier(self) -> None:
        """Miroir baissier de l'anomalie de rôle (S05 re-fire M7)."""
        pushes = [
            self._push("haussiere", 0.0060, "nette", 0),
            self._push("baissiere", 0.0070, "structuree", 1),
            self._push("haussiere", 0.0080, "nette", 2),  # dom growing
            self._push("baissiere", 0.0060, "nette", 3),  # counter NETTE = anomalie
        ]
        t = read_trend(pushes)
        assert t.dominant_direction == "haussiere"
        assert t.state == "retournement_potentiel_baissier"

    def test_indecis_on_balanced_magnitudes(self) -> None:
        """total_up == total_down → indécis, dominant_direction None (S05 M7)."""
        pushes = [
            self._push("haussiere", 0.0050, "structuree", 0),
            self._push("baissiere", 0.0050, "structuree", 1),
        ]
        t = read_trend(pushes)
        assert t.state == "indecis"
        assert t.dominant_direction is None
        assert "équilibr" in t.rationale_fr

    def test_indecis_dominant_but_last_contrary_structuree(self) -> None:
        """Dominant existe mais dernière poussée contraire structurée, sans
        bascule → indécis AVEC dominant_direction non-None (distinct du vide,
        S05 re-fire M7)."""
        pushes = [
            self._push("haussiere", 0.0090, "nette", 0),
            self._push("baissiere", 0.0020, "structuree", 1),
        ]
        t = read_trend(pushes)
        assert t.state == "indecis"
        assert t.dominant_direction == "haussiere"

    def test_indices_retournement_accumulated_and_confirmed(self) -> None:
        """§5.1 : anomalie de rôle → indice listé + retournement CONFIRMÉ."""
        pushes = [
            self._push("baissiere", 0.0060, "nette", 0),
            self._push("haussiere", 0.0070, "structuree", 1),
            self._push("baissiere", 0.0080, "nette", 2),
            self._push("haussiere", 0.0060, "nette", 3),  # counter nette = anomalie
        ]
        t = read_trend(pushes)
        assert t.confirmed_retournement is True
        assert any("anomalie de rôle" in i for i in t.indices_retournement)

    def test_indices_accumulated_without_confirmation(self) -> None:
        """§5.0 : indices accumulés (dominante décroissante) SANS bascule
        confirmée (pas d'anomalie ni weakening+counter-growth)."""
        pushes = [
            self._push("haussiere", 0.0090, "nette", 0),
            self._push("baissiere", 0.0010, "structuree", 1),
            self._push("haussiere", 0.0060, "nette", 2),
            self._push("baissiere", 0.0010, "structuree", 3),
            self._push("haussiere", 0.0030, "nette", 4),
        ]
        t = read_trend(pushes)
        assert t.state == "continuation_haussiere"
        assert t.confirmed_retournement is False
        assert len(t.indices_retournement) >= 1


class TestCandleIntention:
    def test_intention_labels(self) -> None:
        assert "affirmation" in candle_intention("pleine_haussiere")
        assert "affirmation" in candle_intention("pleine_baissiere")
        assert "hésitation" in candle_intention("incertitude")


class TestNyWindow:
    def test_winter_dst_paris(self) -> None:
        """13h-20h Paris in January = 12:00-19:00 UTC (Paris = UTC+1)."""
        open_utc, origin_end_utc, close_utc = ny_window_utc(date(2026, 1, 14))
        assert open_utc == datetime(2026, 1, 14, 12, 0, tzinfo=UTC)
        assert origin_end_utc == datetime(2026, 1, 14, 15, 0, tzinfo=UTC)
        assert close_utc == datetime(2026, 1, 14, 19, 0, tzinfo=UTC)

    def test_summer_dst_paris(self) -> None:
        """13h-20h Paris in June = 11:00-18:00 UTC (Paris = UTC+2) — the other
        half of the DST pair, previously only exercised implicitly (S05 M7)."""
        open_utc, origin_end_utc, close_utc = ny_window_utc(date(2026, 6, 10))
        assert open_utc == datetime(2026, 6, 10, 11, 0, tzinfo=UTC)
        assert origin_end_utc == datetime(2026, 6, 10, 14, 0, tzinfo=UTC)
        assert close_utc == datetime(2026, 6, 10, 18, 0, tzinfo=UTC)


class TestNyOriginZones:
    def test_n1_and_n2_from_previous_completed_session(self) -> None:
        candles = aggregate_hourly(_scenario_bars(), now_utc=_NOW)
        zones, session_date = detect_ny_origin_zones(candles, now_utc=_NOW)
        assert session_date == _SESSION_DAY.date()
        levels = {(z.level, z.side) for z in zones}
        assert ("N1", "vendeuse") in levels
        assert ("N2", "acheteuse") in levels
        n1 = next(z for z in zones if z.level == "N1")
        # Origin candle = the 12:00 UTC pleine baissière where the volume
        # ENTERED (S05 re-fire M1 : the 11:00 incertitude is the segment head
        # but NOT the origin — §7 « le niveau où le volume est ENTRÉ »).
        # Vendeuse zone = body top 1.1002 (clôture) → wick high 1.1004.
        assert abs(n1.bottom - 1.1002) < 1e-9
        assert abs(n1.top - 1.1004) < 1e-9

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

    def test_sub_zone_dividers_are_thirds(self) -> None:
        """3 sous-zones S/R : paliers à 1/3 et 2/3, strictement ordonnés (S05)."""
        candles = aggregate_hourly(_scenario_bars(), now_utc=_NOW)
        zones, _ = detect_ny_origin_zones(candles, now_utc=_NOW)
        z = zones[0]
        t1, t2 = z.sub_zone_dividers
        third = (z.top - z.bottom) / 3.0
        assert abs(t1 - (z.bottom + third)) < 1e-12
        assert abs(t2 - (z.bottom + 2 * third)) < 1e-12
        assert z.bottom < t1 < t2 < z.top

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


class TestN2Reversal:
    """N2 = sortie de volume : momentum stoppé en début de session NY qui
    repart en sens inverse ≥ _N2_REVERSAL_MIN_RATIO=0.5 (METHODOLOGIE §7).
    Previously only the positive case was hit indirectly (S05 re-fire M7)."""

    _D = datetime(2026, 6, 10, tzinfo=UTC)  # completed NY session before _NOW

    def _down_then_up(self, reversal_close: float) -> list[H1Candle]:
        """Down momentum 11h-12h UTC (mag 0.0150) then an up reversal at 13h ;
        ``reversal_close`` sets nxt.magnitude vs the 0.5 threshold (0.0075)."""
        return [
            _candle(self._D.replace(hour=11), 1.1000, 1.1002, 1.0948, 1.0950),
            _candle(self._D.replace(hour=12), 1.0950, 1.0952, 1.0848, 1.0850),
            _candle(
                self._D.replace(hour=13), 1.0850, reversal_close + 0.0002, 1.0849, reversal_close
            ),
        ]

    def test_n2_accepted_at_threshold(self) -> None:
        # reversal 0.0075 = exactly 0.5 × the 0.0150 stopped momentum.
        zones, _ = detect_ny_origin_zones(self._down_then_up(1.0925), now_utc=_NOW)
        assert ("N2", "acheteuse") in {(z.level, z.side) for z in zones}

    def test_n2_rejected_when_reversal_too_small(self) -> None:
        # reversal 0.0074 < 0.5 × 0.0150 → not a valid sortie de volume.
        zones, _ = detect_ny_origin_zones(self._down_then_up(1.0924), now_utc=_NOW)
        assert "N2" not in {z.level for z in zones}

    def test_n2_polarity_up_momentum_gives_vendeuse(self) -> None:
        """A stopped UP momentum that reverses down → origine VENDEUSE N2
        (polarity inverted, §7) — pinned in isolation."""
        candles = [
            _candle(self._D.replace(hour=11), 1.0850, 1.0952, 1.0849, 1.0950),
            _candle(self._D.replace(hour=12), 1.0950, 1.1052, 1.0949, 1.1050),
            _candle(self._D.replace(hour=13), 1.1050, 1.1051, 1.0948, 1.0950),
        ]
        zones, _ = detect_ny_origin_zones(candles, now_utc=_NOW)
        assert ("N2", "vendeuse") in {(z.level, z.side) for z in zones}


class TestN3StructureReversal:
    """N3 = retournement de structure HORS fenêtre NY 13h-16h Paris (§7, source
    complète S05). Conservateur : 2 poussées nettes multi-bougies + retrace ≥0.5
    + proximité (S05 finalisation §13.1)."""

    _D = datetime(2026, 6, 10, tzinfo=UTC)

    def test_n3_reversal_outside_ny_detected(self) -> None:
        # Retournement Asie 02:00-05:00 UTC = 04h-07h Paris (hors 13h-16h).
        candles = [
            _candle(self._D.replace(hour=2), 1.1000, 1.1002, 1.0948, 1.0950),  # down
            _candle(self._D.replace(hour=3), 1.0950, 1.0952, 1.0898, 1.0900),  # down
            _candle(self._D.replace(hour=4), 1.0900, 1.0975, 1.0899, 1.0970),  # up reversal
            _candle(self._D.replace(hour=5), 1.0970, 1.1000, 1.0969, 1.0998),  # up
        ]
        zones = detect_structure_reversals_n3(candles)
        assert ("N3", "acheteuse") in {(z.level, z.side) for z in zones}

    def test_n3_excludes_reversal_inside_ny_window(self) -> None:
        # Même forme mais 11:00-14:00 UTC = 13h-16h Paris → N1/N2, PAS N3.
        candles = [
            _candle(self._D.replace(hour=11), 1.1000, 1.1002, 1.0948, 1.0950),
            _candle(self._D.replace(hour=12), 1.0950, 1.0952, 1.0898, 1.0900),
            _candle(self._D.replace(hour=13), 1.0900, 1.0975, 1.0899, 1.0970),
            _candle(self._D.replace(hour=14), 1.0970, 1.1000, 1.0969, 1.0998),
        ]
        assert detect_structure_reversals_n3(candles) == []

    def test_n3_excludes_reversal_in_ny_gestion_window(self) -> None:
        """Pivot 16h-20h Paris = TOUJOURS dans la session NY → PAS N3 (sinon
        doublon avec N2 ; S05 verifier MAJOR-1). 15:00-17:00 UTC = 17h-19h Paris."""
        candles = [
            _candle(self._D.replace(hour=15), 1.1000, 1.1002, 1.0948, 1.0950),  # down
            _candle(self._D.replace(hour=16), 1.0950, 1.0952, 1.0898, 1.0900),  # down
            _candle(
                self._D.replace(hour=17), 1.0900, 1.0975, 1.0899, 1.0970
            ),  # up (pivot 16:00=18h Paris)
            _candle(self._D.replace(hour=18), 1.0970, 1.1000, 1.0969, 1.0998),  # up
        ]
        assert detect_structure_reversals_n3(candles) == []

    def test_n3_does_not_duplicate_n2_on_scenario(self) -> None:
        """Sur la fixture canonique, le pivot N2 (17h Paris, dans la session) ne
        doit PAS réapparaître en N3 (S05 verifier MAJOR-1 : doublon corrigé)."""
        r = compute_technical_reading(_scenario_bars(), asset="EUR_USD", now_utc=_NOW)
        assert r is not None
        n3_ts = {z.origin_ts for z in r.origin_zones if z.level == "N3"}
        n2_ts = {z.origin_ts for z in r.origin_zones if z.level == "N2"}
        assert not (n3_ts & n2_ts), "un pivot N2 ne doit pas être re-émis en N3"

    def test_n3_rejects_single_candle_blip(self) -> None:
        # Oscillations 1 bougie (n_candles < 2) → AUCUN N3 (anti-bruit).
        candles = [
            _candle(self._D.replace(hour=2), 1.1000, 1.1002, 1.0989, 1.0990),  # 1-bar down
            _candle(self._D.replace(hour=3), 1.0990, 1.1001, 1.0989, 1.1000),  # 1-bar up
            _candle(self._D.replace(hour=4), 1.1000, 1.1002, 1.0989, 1.0990),  # 1-bar down
        ]
        assert detect_structure_reversals_n3(candles) == []


class TestGoldenZone:
    def test_levels_of_latest_nette_push(self) -> None:
        h = datetime(2026, 6, 10, 0, 0, tzinfo=UTC)
        candles = [
            _candle(h, 1.0000, 1.0105, 0.9999, 1.0100),
            _candle(h + timedelta(hours=1), 1.0100, 1.0205, 1.0099, 1.0200),
        ]
        g = golden_zone_of_latest_push(segment_pushes(candles), current_price=1.0150)
        assert g is not None
        # Ancrage MÈCHES (§13.6, owner 2026-06-13) : push high=1.0205 / low=0.9999,
        # range 0.0206 → 0,5 = 1.0102, 0,618 = 1.0077692.
        assert abs(g.zone_high - 1.0102) < 1e-9
        assert abs(g.zone_low - 1.0077692) < 1e-9
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
        # Ancrage MÈCHES (§13.6) : push high=1.0201 / low=0.9995, range 0.0206
        # → baissière retrace depuis le bas : 0,5 = 1.0098, 0,618 = 1.0122308.
        assert abs(g.zone_low - 1.0098) < 1e-9
        assert abs(g.zone_high - 1.0122308) < 1e-9
        assert g.price_position == "en_dessous"

    def test_price_inside_golden_zone(self) -> None:
        """price_position == 'dans' : le scénario central §8 (« confluence
        golden zone + origine = zone de haute qualité ») jamais testé (S05 M7)."""
        h = datetime(2026, 6, 10, 0, 0, tzinfo=UTC)
        candles = [
            _candle(h, 1.0000, 1.0105, 0.9999, 1.0100),
            _candle(h + timedelta(hours=1), 1.0100, 1.0205, 1.0099, 1.0200),
        ]
        # Push 1.0000 → 1.0200 : zone 1.00764 (0,618) → 1.0100 (0,5).
        g = golden_zone_of_latest_push(segment_pushes(candles), current_price=1.0090)
        assert g is not None
        assert g.price_position == "dans"


class TestDayOpenRead:
    def test_excursions_since_paris_midnight(self) -> None:
        d = compute_day_open_read(_scenario_bars(), now_utc=_NOW)
        assert d is not None
        assert d.open_price == 1.0980
        assert d.upside_excursion > 0
        assert d.last_price == 1.0995
        assert d.window_complete is False  # _NOW = 11h Paris, avant midi

    def test_excursion_window_capped_at_noon(self) -> None:
        """La mèche du plongeur est Asie+Londres (minuit-midi) — une barre NY
        de l'après-midi ne doit PAS l'étendre (S05 re-fire M4, §5.2)."""
        bars = [
            # 07:00 UTC = 09h Paris (Londres) : dans la fenêtre.
            Bar(
                ts=datetime(2026, 6, 11, 7, 0, tzinfo=UTC),
                open=1.10,
                high=1.105,
                low=1.099,
                close=1.104,
            ),
            # 13:00 UTC = 15h Paris (NY) : un pic violent qui doit être ignoré.
            Bar(
                ts=datetime(2026, 6, 11, 13, 0, tzinfo=UTC),
                open=1.104,
                high=1.200,
                low=1.000,
                close=1.150,
            ),
        ]
        now = datetime(2026, 6, 11, 14, 0, tzinfo=UTC)  # 16h Paris, après midi
        d = compute_day_open_read(bars, now_utc=now)
        assert d is not None
        assert d.window_complete is True
        assert d.high == 1.105 and d.low == 1.099  # pic NY exclu
        assert d.last_price == 1.104  # dernière barre avant midi


def _day_window_bars(
    start_utc: datetime, o: float, h: float, lo: float, c: float, n: int = 80
) -> list[Bar]:
    """n 1-min bars in a daily window [start, ...) aggregating to OHLC (o,h,lo,c)."""
    bars: list[Bar] = []
    for i in range(n):
        ts = start_utc + timedelta(minutes=i)
        if i == 0:
            bars.append(Bar(ts=ts, open=o, high=max(o, c), low=min(o, c), close=o))
        elif i == 1:
            bars.append(Bar(ts=ts, open=o, high=h, low=o, close=o))
        elif i == 2:
            bars.append(Bar(ts=ts, open=o, high=o, low=lo, close=o))
        elif i == n - 1:
            bars.append(Bar(ts=ts, open=o, high=max(o, c), low=min(o, c), close=c))
        else:
            bars.append(Bar(ts=ts, open=o, high=o, low=o, close=o))
    return bars


class TestDailyRead:
    """Lecture Daily §5.3 (S05 re-fire #3). _NOW = 06-11 11h Paris → dernière
    clôture daily = 06-10 22h Paris = 06-10 20:00 UTC ; D-1 = [06-09 20:00 UTC,
    06-10 20:00 UTC)."""

    _D1_START = datetime(2026, 6, 9, 20, 0, tzinfo=UTC)

    def test_daily_momentum_bull_no_plongeur(self) -> None:
        bars = _day_window_bars(self._D1_START, 1.0900, 1.1010, 1.0890, 1.1000)
        d = compute_daily_read(bars, now_utc=_NOW)
        assert d is not None
        assert d.classification.kind == "momentum_bull"
        assert d.plongeur_wick_expected is False  # forte poussée → pas de mèche
        assert d.session_date == date(2026, 6, 10)

    def test_daily_rejection_expects_plongeur(self) -> None:
        # Petit corps + grande mèche basse = rejet acheteur (incertitude).
        bars = _day_window_bars(self._D1_START, 1.1000, 1.1010, 1.0900, 1.1005)
        d = compute_daily_read(bars, now_utc=_NOW)
        assert d is not None
        assert d.classification.kind == "uncertainty"
        assert d.rejection_side == "bas"
        assert d.plongeur_wick_expected is True

    def test_daily_symmetric_doji_no_rejection(self) -> None:
        """Mèches quasi-symétriques → PAS de rejet marqué (dominance ≥1.2 non
        atteinte) → pas de mèche du plongeur forcée (S05 verifier nice-to-have)."""
        bars = _day_window_bars(self._D1_START, 1.1000, 1.1050, 1.0950, 1.1001)
        d = compute_daily_read(bars, now_utc=_NOW)
        assert d is not None
        assert d.rejection_side == "aucun"
        assert d.plongeur_wick_expected is False

    def test_daily_honest_absence_below_min_bars(self) -> None:
        bars = _day_window_bars(self._D1_START, 1.09, 1.10, 1.089, 1.10, n=30)
        assert compute_daily_read(bars, now_utc=_NOW) is None

    def test_daily_prose_is_adr017_clean(self) -> None:
        from ichor_api.services.daily_candle_classifier import classify_daily_candle
        from ichor_api.services.technical_analysis import (
            DailyRead,
            TechnicalReading,
            TrendRead,
        )

        cls = classify_daily_candle(prev_ohlc=None, curr_ohlc=(1.1000, 1.1010, 1.0900, 1.1005))
        daily = DailyRead(
            classification=cls,
            open=1.1000,
            high=1.1010,
            low=1.0900,
            close=1.1005,
            rejection_side="bas",
            plongeur_wick_expected=True,
            session_date=date(2026, 6, 10),
        )
        reading = TechnicalReading(
            asset="EUR_USD",
            computed_at=_NOW,
            last_bar_ts=_NOW,
            current_price=1.1000,
            h1_candle_count=24,
            trend=TrendRead(state="indecis", dominant_direction=None, rationale_fr="t."),
            recent_pushes=(),
            origin_zones=(),
            golden_zone=None,
            day_open=None,
            ny_session_date=None,
            daily=daily,
        )
        md, _ = render_technical_reading_block(reading, "EUR_USD")
        assert "Lecture Daily" in md
        assert "rejet acheteur" in md
        assert "mèche du plongeur attendue" in md
        assert is_adr017_clean(md)


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

    def test_proxy_caveats_for_dxy_and_nas_are_clean(self) -> None:
        """The DXY (UUP) and NAS100 (RTH) caveats were never rendered nor
        passed through the ADR-017 filter in tests (S05 re-fire M7)."""
        for asset, needle in (("DXY", "UUP"), ("NAS100_USD", "RTH")):
            r = compute_technical_reading(_scenario_bars(), asset=asset, now_utc=_NOW)
            md, _ = render_technical_reading_block(r, asset)
            assert needle in md, f"caveat for {asset} not rendered"
            assert is_adr017_clean(md), f"caveat prose for {asset} must stay ADR-017-clean"

    def test_plongeur_prose_downside_dominant_branch(self) -> None:
        """The downside-dominant plongeur branch (« respiration baissière déjà
        visible ») was never rendered — the scenario fixture is upside-dominant
        (S05 re-fire M7). Pins the signature §5.2 mirror prose."""
        from ichor_api.services.technical_analysis import (
            DayOpenRead,
            TechnicalReading,
            TrendRead,
        )

        reading = TechnicalReading(
            asset="EUR_USD",
            computed_at=_NOW,
            last_bar_ts=_NOW,
            current_price=1.0970,
            h1_candle_count=24,
            trend=TrendRead(state="indecis", dominant_direction=None, rationale_fr="test."),
            recent_pushes=(),
            origin_zones=(),
            golden_zone=None,
            day_open=DayOpenRead(
                open_price=1.1000, last_price=1.0970, high=1.1005, low=1.0950, window_complete=True
            ),
            ny_session_date=None,
        )
        md, _ = render_technical_reading_block(reading, "EUR_USD")
        assert is_adr017_clean(md)
        # downside excursion 0.0050 > upside 0.0005.
        assert "la respiration baissière est déjà visible" in md
        assert "la respiration haussière n’est pas encore marquée" in md

    def test_indices_line_rendered_when_not_confirmed(self) -> None:
        """§5.1 : la ligne dédiée « Indices de retournement » apparaît quand des
        indices sont accumulés SANS confirmation (S05 re-fire #3)."""
        from ichor_api.services.technical_analysis import TechnicalReading, TrendRead

        reading = TechnicalReading(
            asset="EUR_USD",
            computed_at=_NOW,
            last_bar_ts=_NOW,
            current_price=1.1000,
            h1_candle_count=24,
            trend=TrendRead(
                state="continuation_haussiere",
                dominant_direction="haussiere",
                rationale_fr="t.",
                indices_retournement=("amplitudes dominantes successives décroissantes",),
                confirmed_retournement=False,
            ),
            recent_pushes=(),
            origin_zones=(),
            golden_zone=None,
            day_open=None,
            ny_session_date=None,
        )
        md, _ = render_technical_reading_block(reading, "EUR_USD")
        assert "Indices de retournement" in md
        assert "pas encore de confirmation" in md
        assert is_adr017_clean(md)
