"""Technical-analysis read applying the owner's codified methodology (ADR-113, S05).

SSOT of the encoded rules : ``docs/METHODOLOGIE_TECHNIQUE_ELIOT.md`` — nothing
in this module may encode a technical rule that is absent from that document.
The owner's methodology in one line (METHODOLOGIE §2) : « dans quel élan est
mon marché, et s'approche-t-il d'origines acheteuses ou vendeuses ».

Architecture mirrors ``london_session.py`` (the SSOT pattern) : a pure core
(stdlib only, zero I/O, synthetic-bar testable) + a thin async DB wrapper
shared by the data_pool Pass-2 section and any future router, so the two can
never drift on which bars feed the read.

Slice-1 scope (METHODOLOGIE §12) :
  - H1 aggregation from 1-min bars (closed candles only — « une mèche n'est
    pas une cassure », decisions at candle close)
  - candle grammar : bougie pleine (corps > somme des mèches) vs incertitude
  - poussée / correction segmentation + anomaly-of-role retournement read
  - origin zones N1/N2 from the most recent completed NY session (Paris
    13h-20h window ; N1 origin inside 13h-16h) + 3-tier retest band +
    proximity ranking
  - golden zone 0,5-0,618 of the latest significant H1 poussée
  - « mèche du plongeur » day-open status (Asie/Londres vs sens final NY)

Deliberately NOT here (deferred, METHODOLOGIE §12-§13) : 15m/5m execution
triggers, origin level 3 (source truncated — [TBD owner]), DimensionVote
(post-Chantier C). Thresholds the owner never quantified are PROVISIONAL,
named constants below, listed in METHODOLOGIE §13.7.

ADR-017 : descriptive reading only — structure states, zones, probabilities of
behaviour. Never a trade instruction. Rendered prose uses the owner's French
nominal vocabulary (« origine acheteuse/vendeuse », « poussée », « mèche du
plongeur ») and no order tokens in any language.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Final, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .daily_candle_classifier import DailyCandleClassification, classify_daily_candle
from .london_session import Bar

_PARIS_TZ = ZoneInfo("Europe/Paris")

# NY-session window, Paris local (METHODOLOGIE §1, EXPLICITE) : the « carrés
# bleus » 13h-20h ; the origin-quality window (volume of the US open) is
# 13h-16h. DST handled by ZoneInfo (the owner's hours are Paris-local).
_NY_SESSION_OPEN: Final = time(13, 0)
_NY_SESSION_CLOSE: Final = time(20, 0)
_NY_ORIGIN_WINDOW_END: Final = time(16, 0)

# Golden zone : the ONLY Fibonacci levels the owner keeps (METHODOLOGIE §8,
# EXPLICITE « entre les 0,5 et le chiffre d'or 0,618 »).
_GOLDEN_LOW_RATIO: Final = 0.5
_GOLDEN_HIGH_RATIO: Final = 0.618

# Body/range directional threshold — reused from the origin-zone module
# doctrine (Eliot Fathom §V « bodies > 30% of range », already CI-anchored).
_DIRECTIONAL_THRESHOLD_RATIO: Final = 0.3

# ---- PROVISIONAL thresholds (owner gave qualitative rules only ;
# METHODOLOGIE §13.7 — to calibrate with the owner, do not silently change).
_MIN_BARS_PER_HOUR: Final = 20
"""An H1 candle aggregated from fewer 1-min bars is dropped (gappy hour)."""
_MIN_H1_CANDLES: Final = 24
"""Below ~one trading day of closed H1 candles → honest absence (None)."""
_NETTE_FULL_SHARE: Final = 0.5
"""A poussée is « nette » when ≥ this share of its candles are pleines in its
direction (owner : « quasi uniquement des bougies dans le sens »)."""
_TREND_WINDOW_PUSHES: Final = 6
"""Pushes considered for the continuation/retournement read."""
_N2_REVERSAL_MIN_RATIO: Final = 0.5
"""A stopped momentum counts as an N2 origin only if the reversal push
retraces ≥ this share of it (« se stoppe et repart en sens inverse »)."""
_N3_REVERSAL_MIN_RATIO: Final = 0.5
"""An out-of-NY structure reversal is an N3 origin only if the reversal push
retraces ≥ this share of the stopped momentum (mirror of N2)."""
_N3_MIN_PUSH_CANDLES: Final = 2
"""N3 requires a multi-bougie momentum on BOTH legs (not a 1-bar blip) so minor
oscillations don't flood the read — PROVISIONAL (§13.7)."""
_MAX_ORIGIN_ZONES: Final = 4
"""Render cap : the closest origins prime (METHODOLOGIE §7 « le plus proche
prime ») once N3 widens the candidate set beyond the NY session."""
_DAILY_CLOSE_PARIS: Final = time(22, 0)
"""Daily candle close faisant foi = clôture NY/FX ~22h Paris (METHODOLOGIE
§5.3/§13.15, owner-confirmé verbatim « il est exactement 22h… la clôture
journalière en daily »). PROVISIONAL sur le bord 22h vs 23h DST / No-Gap (§13.10)."""
_MIN_BARS_PER_DAY: Final = 60
"""En-dessous, une fenêtre daily a trop peu de couverture intraday (proxy RTH /
week-end / férié) → absence honnête sur la Lecture Daily (§5.3)."""
_REJECTION_DOMINANCE: Final = 1.2
"""Un « fort rejet » daily (§5.3) exige une mèche CLAIREMENT dominante : la
mèche rejetante doit dépasser le corps ET valoir ≥ ce facteur × l'autre mèche —
sinon un quasi-doji symétrique basculerait en rejet sur un écart pip-level
(S05 verifier nice-to-have). PROVISIONAL (§13.7)."""

CandleKind = Literal["pleine_haussiere", "pleine_baissiere", "incertitude"]
PushDirection = Literal["haussiere", "baissiere"]
PushQuality = Literal["nette", "structuree"]
TrendState = Literal[
    "continuation_haussiere",
    "continuation_baissiere",
    "retournement_potentiel_haussier",
    "retournement_potentiel_baissier",
    "indecis",
]
ZoneSide = Literal["acheteuse", "vendeuse"]
ZoneLevel = Literal["N1", "N2", "N3"]

# FR accents for rendered prose (the Literal values stay accent-free as code
# identifiers ; review PR #234 m1 — never leak `haussiere` into Pass-2 text).
_DIR_FR: Final = {"haussiere": "haussière", "baissiere": "baissière"}


@dataclass(frozen=True)
class H1Candle:
    """A closed H1 candle aggregated from 1-min bars (UTC hour-aligned)."""

    ts_open: datetime
    open: float
    high: float
    low: float
    close: float
    bar_count: int


@dataclass(frozen=True)
class Push:
    """A directional poussée (or its corrective counterpart) on H1.

    quality « nette » = momentum (bougies pleines, mouvement linéaire) ;
    « structuree » = correction-like (mèches, combat) — METHODOLOGIE §3/§5.1.
    """

    direction: PushDirection
    start_ts: datetime
    end_ts: datetime
    start_price: float
    end_price: float
    high: float
    low: float
    n_candles: int
    n_full_in_direction: int
    quality: PushQuality

    @property
    def magnitude(self) -> float:
        return abs(self.end_price - self.start_price)


@dataclass(frozen=True)
class TrendRead:
    """Continuation / retournement read over the recent H1 pushes.

    ``indices_retournement`` = les indices de retournement accumulés (§5.0/§5.1 :
    « un indice précède le mouvement, ne confirme pas seul, s'accumule ») ;
    ``confirmed_retournement`` = la bascule est confirmée (état
    retournement_potentiel) vs simple accumulation d'indices."""

    state: TrendState
    dominant_direction: PushDirection | None
    rationale_fr: str
    indices_retournement: tuple[str, ...] = ()
    confirmed_retournement: bool = False


@dataclass(frozen=True)
class OriginZone:
    """An origine acheteuse/vendeuse traced on H1 (METHODOLOGIE §7).

    Bounds : body extreme → wick extreme of the origin candle (the exact
    tracing convention is [TBD owner] — METHODOLOGIE §13.5 ; this is the
    conservative body-to-wick band ; T-B practice : borne à la clôture,
    extension possible jusqu'à la mèche, préférence zone précise).

    ``retest_low/high`` = the valid-retest band after the 3-tier division :
    the half of the zone on the price-approach side. T-B demonstrates it on
    an origine ACHETEUSE (price falls INTO the zone from above → valid retest
    « entre le haut et le milieu », EXPLICITE) ; the mirror for a zone
    vendeuse (price rises into it from below → entre le bas et le milieu) is
    INFÉRÉE — METHODOLOGIE §7/§13.
    """

    side: ZoneSide
    level: ZoneLevel
    top: float
    bottom: float
    origin_ts: datetime
    session_date: date
    source_push_magnitude: float

    @property
    def retest_low(self) -> float:
        mid = (self.top + self.bottom) / 2.0
        return mid if self.side == "acheteuse" else self.bottom

    @property
    def retest_high(self) -> float:
        mid = (self.top + self.bottom) / 2.0
        return self.top if self.side == "acheteuse" else mid

    @property
    def sub_zone_dividers(self) -> tuple[float, float]:
        """Les 2 paliers internes (1/3 et 2/3) divisant la zone en 3 sous-zones
        S/R (METHODOLOGIE §7, transcript COMPLET S05 : « ma zone est divisée en
        trois zones… chaque zone fait office de support et de résistance »).
        Au-dessus d'un palier → rebond haussier probable ; en-dessous → baissier.
        Le retest « moitié côté approche » (retest_low/high) reste un cas
        particulier centré sur le milieu."""
        third = (self.top - self.bottom) / 3.0
        return (self.bottom + third, self.bottom + 2.0 * third)


@dataclass(frozen=True)
class GoldenZoneRead:
    """Golden-zone (0,5-0,618) retracement of the latest significant poussée."""

    push_direction: PushDirection
    zone_low: float
    zone_high: float
    price_position: Literal["dans", "au_dessus", "en_dessous"]


@dataclass(frozen=True)
class DayOpenRead:
    """« Mèche du plongeur » : excursions de la fenêtre Asie+Londres
    (00h-12h Paris) avant le sens final NY (METHODOLOGIE §5.2 « minuit-midi »).
    Descriptive pour les DEUX directions hypothétiques — le biais directionnel
    vient du fondamental (§9 : ~80% fondamental), cette lecture ne choisit
    jamais de camp.

    ``window_complete`` : la fenêtre minuit-midi est close (now ≥ 12h Paris) →
    la mèche contraire est figée, jamais étendue par la session NY (S05 M4).
    """

    open_price: float
    last_price: float
    high: float
    low: float
    window_complete: bool

    @property
    def upside_excursion(self) -> float:
        return self.high - self.open_price

    @property
    def downside_excursion(self) -> float:
        return self.open_price - self.low


@dataclass(frozen=True)
class DailyRead:
    """Lecture Daily (METHODOLOGIE §5.3) : la DERNIÈRE bougie daily clôturée
    (à 22h Paris, §13.15 owner-confirmé). On lit UNIQUEMENT COMMENT elle s'est
    clôturée (mèches/rejet), jamais la direction globale (§5.3). Classification
    via le SSOT existant ``classify_daily_candle``. Pilote l'attente de la mèche
    du plongeur (§5.2/§5.3) : clôture en rejet → mèche attendue ; clôture en
    forte poussée → non requise. Descriptive (ADR-017) — ne choisit pas de camp.
    """

    classification: DailyCandleClassification
    open: float
    high: float
    low: float
    close: float
    rejection_side: Literal["haut", "bas", "aucun"]
    plongeur_wick_expected: bool
    session_date: date


@dataclass(frozen=True)
class TechnicalReading:
    """Full technical read for one asset (descriptive, ADR-017)."""

    asset: str
    computed_at: datetime
    last_bar_ts: datetime
    current_price: float
    h1_candle_count: int
    trend: TrendRead
    recent_pushes: tuple[Push, ...]
    origin_zones: tuple[OriginZone, ...]
    golden_zone: GoldenZoneRead | None
    day_open: DayOpenRead | None
    ny_session_date: date | None
    daily: DailyRead | None = None


# --------------------------------------------------------------------------
# Pure core
# --------------------------------------------------------------------------


def aggregate_hourly(bars: list[Bar], *, now_utc: datetime) -> list[H1Candle]:
    """Aggregate 1-min bars into CLOSED H1 candles (UTC hour-aligned).

    The current, still-open hour is excluded : every owner rule reads candles
    at their close (« une mèche n'est pas une cassure »). Hours with fewer
    than ``_MIN_BARS_PER_HOUR`` bars are dropped (gappy/holiday hours).
    """
    if not bars:
        return []
    current_hour = now_utc.replace(minute=0, second=0, microsecond=0)
    buckets: dict[datetime, list[Bar]] = {}
    for b in bars:
        hour = b.ts.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
        if hour >= current_hour:
            continue
        buckets.setdefault(hour, []).append(b)
    candles: list[H1Candle] = []
    for hour in sorted(buckets):
        win = sorted(buckets[hour], key=lambda b: b.ts)
        if len(win) < _MIN_BARS_PER_HOUR:
            continue
        candles.append(
            H1Candle(
                ts_open=hour,
                open=win[0].open,
                high=max(b.high for b in win),
                low=min(b.low for b in win),
                close=win[-1].close,
                bar_count=len(win),
            )
        )
    return candles


def classify_candle(c: H1Candle) -> CandleKind:
    """Bougie pleine vs bougie d'incertitude (METHODOLOGIE §3, EXPLICITE).

    « corps plus grand que l'addition des deux mèches » → pleine, signed by
    close vs open ; anything else (wick-dominant, zero-range) → incertitude.
    """
    body = abs(c.close - c.open)
    wick_sum = (c.high - c.low) - body
    if body > wick_sum and c.close != c.open:
        return "pleine_haussiere" if c.close > c.open else "pleine_baissiere"
    return "incertitude"


_INTENTION_FR: Final = {
    "pleine_haussiere": "affirmation (conviction acheteuse, momentum)",
    "pleine_baissiere": "affirmation (conviction vendeuse, momentum)",
    "incertitude": "hésitation / doute (transition ; une grande mèche = tentative ratée / rejet)",
}


def candle_intention(kind: CandleKind) -> str:
    """Intention sémantique d'une bougie (METHODOLOGIE §5.0 `[CM]`) : pleine =
    affirmation/conviction (momentum) ; incertitude = hésitation/doute — une
    grande mèche se lit comme une tentative ratée / un rejet (côté lu via le
    statut de rejet, §5.3). Lecture descriptive (ADR-017)."""
    return _INTENTION_FR[kind]


def segment_pushes(candles: list[H1Candle]) -> list[Push]:
    """Segment closed H1 candles into alternating directional pushes.

    Faithful to the owner's grammar (METHODOLOGIE §5.1) : a poussée extends
    while candles agree with its direction ; bougies d'incertitude attach to
    the current segment (tolerated at start/end of a poussée) ; a pleine
    candle of the OPPOSITE direction closes the segment and opens the next.
    """
    if not candles:
        return []
    segments: list[list[H1Candle]] = []
    seg_dir: PushDirection | None = None
    current: list[H1Candle] = []
    for c in candles:
        kind = classify_candle(c)
        if kind == "incertitude":
            current.append(c)
            continue
        cand_dir: PushDirection = "haussiere" if kind == "pleine_haussiere" else "baissiere"
        if seg_dir is None:
            seg_dir = cand_dir
            current.append(c)
        elif cand_dir == seg_dir:
            current.append(c)
        else:
            segments.append(current)
            current = [c]
            seg_dir = cand_dir
    if current and seg_dir is not None:
        segments.append(current)

    pushes: list[Push] = []
    for seg in segments:
        net = seg[-1].close - seg[0].open
        if net == 0:
            continue
        direction: PushDirection = "haussiere" if net > 0 else "baissiere"
        full_kind = "pleine_haussiere" if direction == "haussiere" else "pleine_baissiere"
        n_full = sum(1 for c in seg if classify_candle(c) == full_kind)
        seg_high = max(c.high for c in seg)
        seg_low = min(c.low for c in seg)
        seg_range = seg_high - seg_low
        nette = (
            n_full / len(seg) >= _NETTE_FULL_SHARE
            and seg_range > 0
            and abs(net) / seg_range >= _DIRECTIONAL_THRESHOLD_RATIO
        )
        pushes.append(
            Push(
                direction=direction,
                start_ts=seg[0].ts_open,
                end_ts=seg[-1].ts_open,
                start_price=seg[0].open,
                end_price=seg[-1].close,
                high=seg_high,
                low=seg_low,
                n_candles=len(seg),
                n_full_in_direction=n_full,
                quality="nette" if nette else "structuree",
            )
        )
    return pushes


def read_trend(pushes: list[Push]) -> TrendRead:
    """Continuation vs retournement potentiel (METHODOLOGIE §5.1, EXPLICITE).

    Signals encoded :
      - poussées dominantes de moins en moins grandes + poussées contraires
        de plus en plus grandes → retournement potentiel ;
      - anomalie de rôle : une « correction » (poussée contraire) NETTE alors
        qu'elle devrait être structurée → bascule du camp dominant ;
      - sinon : continuation dans le sens dominant si la dernière poussée le
        confirme ; « indecis » à défaut (honest read, jamais de forçage).
    """
    window = pushes[-_TREND_WINDOW_PUSHES:]
    if not window:
        return TrendRead(
            state="indecis",
            dominant_direction=None,
            rationale_fr="Pas assez de poussées lisibles en H1.",
        )
    total_up = sum(p.magnitude for p in window if p.direction == "haussiere")
    total_down = sum(p.magnitude for p in window if p.direction == "baissiere")
    if total_up == total_down:
        return TrendRead(
            state="indecis",
            dominant_direction=None,
            rationale_fr="Poussées haussières et baissières équilibrées : pas d'élan dominant lisible.",
        )
    dominant: PushDirection = "haussiere" if total_up > total_down else "baissiere"
    dom = [p for p in window if p.direction == dominant]
    counter = [p for p in window if p.direction != dominant]

    # METHODOLOGIE §5.0/§5.1 : indices de retournement ACCUMULABLES (« un indice
    # précède le mouvement, ne confirme pas seul »). L'anomalie de rôle (une
    # « correction » devenue NETTE) est le détecteur AUTONOME (review PR #234
    # M1) ; les autres s'accumulent comme indices.
    role_anomaly = bool(counter) and counter[-1].quality == "nette"
    weakening = len(dom) >= 2 and dom[-1].magnitude < dom[-2].magnitude
    counter_growing = len(counter) >= 2 and counter[-1].magnitude > counter[-2].magnitude
    dom_decreasing = len(dom) >= 3 and dom[-1].magnitude < dom[-2].magnitude < dom[-3].magnitude
    indices: list[str] = []
    if role_anomaly:
        indices.append("anomalie de rôle (correction devenue nette : le camp opposé prend la main)")
    # dom_decreasing (3 amplitudes décroissantes) est le sur-ensemble fort de
    # weakening (2) → un seul libellé pour ne pas gonfler le compteur d'indices.
    if dom_decreasing:
        indices.append("amplitudes dominantes successives décroissantes")
    elif weakening:
        indices.append(f"poussées {_DIR_FR[dominant]}s de moins en moins grandes")
    if counter_growing:
        indices.append("poussées contraires de plus en plus grandes")
    indices_t = tuple(indices)

    if role_anomaly or (weakening and counter_growing):
        state: TrendState = (
            "retournement_potentiel_haussier"
            if dominant == "baissiere"
            else "retournement_potentiel_baissier"
        )
        return TrendRead(
            state=state,
            dominant_direction=dominant,
            rationale_fr=" ; ".join(indices) + ".",
            indices_retournement=indices_t,
            confirmed_retournement=True,
        )

    if window[-1].direction == dominant:
        qual = window[-1].quality
        return TrendRead(
            state=f"continuation_{dominant}",  # type: ignore[arg-type]
            dominant_direction=dominant,
            rationale_fr=f"Élan {_DIR_FR[dominant]} dominant, dernière poussée {qual} dans le sens.",
            indices_retournement=indices_t,
            confirmed_retournement=False,
        )
    return TrendRead(
        state="indecis",
        dominant_direction=dominant,
        rationale_fr=(
            f"Élan {_DIR_FR[dominant]} dominant mais dernière poussée contraire structurée, "
            "sans bascule de camp confirmée : lecture en attente de la prochaine clôture."
        ),
        indices_retournement=indices_t,
        confirmed_retournement=False,
    )


def ny_window_utc(d: date) -> tuple[datetime, datetime, datetime]:
    """(open, origin-window end 16h, close 20h) UTC bounds for Paris date d."""
    open_l = datetime.combine(d, _NY_SESSION_OPEN, tzinfo=_PARIS_TZ)
    origin_end_l = datetime.combine(d, _NY_ORIGIN_WINDOW_END, tzinfo=_PARIS_TZ)
    close_l = datetime.combine(d, _NY_SESSION_CLOSE, tzinfo=_PARIS_TZ)
    return open_l.astimezone(UTC), origin_end_l.astimezone(UTC), close_l.astimezone(UTC)


def _zone_from_candle(c: H1Candle, side: ZoneSide) -> tuple[float, float]:
    """(bottom, top) of an origin zone : body extreme → wick extreme.

    Tracing convention provisional ([TBD owner], METHODOLOGIE §13.5) : for a
    zone vendeuse (at a top) the band runs from the candle body top up to the
    wick high ; mirror for an acheteuse. Degenerate (wickless) candles fall
    back to a body band so the zone never has zero width on real data.
    """
    body_top = max(c.open, c.close)
    body_bottom = min(c.open, c.close)
    if side == "vendeuse":
        top, bottom = c.high, body_top
        if top <= bottom:
            top, bottom = body_top, body_bottom
    else:
        top, bottom = body_bottom, c.low
        top, bottom = (top, bottom) if top > bottom else (body_top, body_bottom)
        # normalize ordering (top must be the greater bound)
        if top < bottom:
            top, bottom = bottom, top
    return bottom, top


def _first_momentum_candle(session_candles: list[H1Candle], push: Push) -> H1Candle:
    """La bougie où le volume est réellement ENTRÉ pour ``push`` — sa première
    bougie PLEINE dans le sens de la poussée (METHODOLOGIE §7 : l'origine est
    le niveau où le volume est ENTRÉ, pas la bougie d'incertitude de tête qui
    s'attache à la poussée, §3). ``detect_ny_origin_zones`` re-segmente sur les
    bougies de la session NY seules, donc une incertitude de tête devient la
    tête du segment (seg_dir None → incertitude ``append``) et ``push.start_ts``
    peut la pointer. Repli sur la bougie de départ si le segment ne porte aucune
    pleine (défensif ; une poussée NETTE en a toujours une) — S05 re-fire M1.
    """
    want: CandleKind = "pleine_haussiere" if push.direction == "haussiere" else "pleine_baissiere"
    for c in session_candles:
        if push.start_ts <= c.ts_open <= push.end_ts and classify_candle(c) == want:
            return c
    return next(c for c in session_candles if c.ts_open == push.start_ts)


def detect_ny_origin_zones(
    candles: list[H1Candle], *, now_utc: datetime
) -> tuple[list[OriginZone], date | None]:
    """Origin zones N1/N2 from the most recent COMPLETED NY session.

    METHODOLOGIE §7 (EXPLICITE) :
      - N1 = origin of the largest momentum whose departure sits inside the
        13h-16h Paris origin window of the previous NY session — « l'origine
        du momentum de la session de New York précédente » ;
      - N2 = the stop-point of a strong session momentum that reversed
        (sortie du gros volume), polarity inverted ;
      - une origine valide est l'origine d'un momentum réel.
    Returns ([], None) on honest absence (no completed session with readable
    pushes in the lookback).
    """
    if not candles:
        return [], None
    paris_today = now_utc.astimezone(_PARIS_TZ).date()
    for delta in range(8):
        d = paris_today - timedelta(days=delta)
        open_utc, origin_end_utc, close_utc = ny_window_utc(d)
        if now_utc < close_utc:
            continue  # session not completed yet
        session_candles = [c for c in candles if open_utc <= c.ts_open < close_utc]
        if len(session_candles) < 3:
            continue
        # First COMPLETED readable session decides — METHODOLOGIE §7 « la
        # session de New York précédente » + §3 proximité (review PR #234 m2 :
        # no multi-day fallback presenting a stale zone with fresh authority).
        # No nette push in it → honest absence for the day.
        pushes = segment_pushes(session_candles)
        real = [p for p in pushes if p.quality == "nette"]
        if not real:
            return [], d
        zones: list[OriginZone] = []

        # N1 — largest nette push departing inside the 13h-16h origin window.
        n1_candidates = [p for p in real if open_utc <= p.start_ts < origin_end_utc]
        if n1_candidates:
            n1_push = max(n1_candidates, key=lambda p: p.magnitude)
            # Origine = la bougie de momentum (1re pleine dans le sens), pas
            # l'incertitude de tête que segment_pushes attache au segment
            # (S05 re-fire M1, §7 : « le niveau où le volume est ENTRÉ »).
            origin_candle = _first_momentum_candle(session_candles, n1_push)
            side: ZoneSide = "vendeuse" if n1_push.direction == "baissiere" else "acheteuse"
            bottom, top = _zone_from_candle(origin_candle, side)
            zones.append(
                OriginZone(
                    side=side,
                    level="N1",
                    top=top,
                    bottom=bottom,
                    # Aligned on the momentum candle that sets the bounds, not the
                    # head incertitude (S05 verifier NIT).
                    origin_ts=origin_candle.ts_open,
                    session_date=d,
                    source_push_magnitude=n1_push.magnitude,
                )
            )

        # N2 — first strong momentum of the session that stopped and reversed.
        if len(pushes) >= 2:
            for i, p in enumerate(pushes[:-1]):
                nxt = pushes[i + 1]
                if (
                    p.quality == "nette"
                    and open_utc <= p.start_ts < origin_end_utc
                    and nxt.direction != p.direction
                    and p.magnitude > 0
                    and nxt.magnitude / p.magnitude >= _N2_REVERSAL_MIN_RATIO
                ):
                    stop_candle = next(c for c in session_candles if c.ts_open == p.end_ts)
                    n2_side: ZoneSide = "acheteuse" if p.direction == "baissiere" else "vendeuse"
                    bottom, top = _zone_from_candle(stop_candle, n2_side)
                    zones.append(
                        OriginZone(
                            side=n2_side,
                            level="N2",
                            top=top,
                            bottom=bottom,
                            origin_ts=p.end_ts,
                            session_date=d,
                            source_push_magnitude=p.magnitude,
                        )
                    )
                    break
        return zones, d
    return [], None


def detect_structure_reversals_n3(candles: list[H1Candle]) -> list[OriginZone]:
    """N3 origins (METHODOLOGIE §7, EXPLICITE — source complète S05) : market-
    structure reversals OUTSIDE the NY origin window (Asie/Londres, toute heure
    hors 13h-16h Paris). Eliot trace et nomme ces origines de niveau 3 (« tout
    ce qui est retournement sur le marché » hors session NY, ex. 0h-1h).

    A pivot where a NETTE multi-bougie push is followed by an opposite NETTE
    multi-bougie push retracing ≥ ``_N3_REVERSAL_MIN_RATIO`` = the N3 origin
    (polarity = the new push direction's side ; reversal up → origine
    ACHETEUSE). Final priority is PROXIMITY, applied by the caller (§7 « le
    plus proche prime », §3). Thresholds PROVISIONAL (§13.7).

    Distinct from the « switch de canal » (§13.16) whose formal validation
    criterion stays [TBD owner] — here we detect a structure reversal pivot,
    not a channel switch.
    """
    if len(candles) < 3:
        return []
    pushes = segment_pushes(candles)
    zones: list[OriginZone] = []
    for i, p in enumerate(pushes[:-1]):
        nxt = pushes[i + 1]
        pivot_paris_hour = p.end_ts.astimezone(_PARIS_TZ).hour
        if _NY_SESSION_OPEN.hour <= pivot_paris_hour < _NY_SESSION_CLOSE.hour:
            continue  # inside the NY session 13h-20h Paris → N1/N2 territory,
            # NOT N3 (§7 « hors session NY ») ; avoids the N2/N3 duplicate at
            # a 16h-20h reversal pivot (S05 verifier MAJOR-1).
        if (
            p.quality == "nette"
            and nxt.quality == "nette"
            and p.n_candles >= _N3_MIN_PUSH_CANDLES
            and nxt.n_candles >= _N3_MIN_PUSH_CANDLES
            and nxt.direction != p.direction
            and p.magnitude > 0
            and nxt.magnitude / p.magnitude >= _N3_REVERSAL_MIN_RATIO
        ):
            pivot_candle = next(c for c in candles if c.ts_open == p.end_ts)
            side: ZoneSide = "acheteuse" if p.direction == "baissiere" else "vendeuse"
            bottom, top = _zone_from_candle(pivot_candle, side)
            zones.append(
                OriginZone(
                    side=side,
                    level="N3",
                    top=top,
                    bottom=bottom,
                    origin_ts=p.end_ts,
                    session_date=p.end_ts.astimezone(_PARIS_TZ).date(),
                    source_push_magnitude=p.magnitude,
                )
            )
    return zones


def golden_zone_of_latest_push(pushes: list[Push], current_price: float) -> GoldenZoneRead | None:
    """Golden zone 0,5-0,618 of the most recent NETTE push (METHODOLOGIE §8).

    Anchor (owner-decided 2026-06-13, §13.6) : retracement on the push WICK
    EXTREMES — « du plus haut au plus bas du mouvement » (§8 literal). For a
    haussière push the zone retraces DOWN from the high ; for a baissière push
    it retraces UP from the low. This matches the Pine companion, which anchors
    on the previous-NY-session directional swing high↔low (§13.6b) — both now
    use extremes/wicks, consistent on direction. Object axis : this server read
    uses the latest nette H1 push ; the Pine uses the whole previous NY session
    swing — they coincide on a single-push session and may differ on a
    multi-push one (the server read is the faithful one).
    """
    nettes = [p for p in pushes if p.quality == "nette"]
    if not nettes:
        return None
    push = nettes[-1]
    rng = push.high - push.low
    if push.direction == "haussiere":
        a = push.high - rng * _GOLDEN_LOW_RATIO
        b = push.high - rng * _GOLDEN_HIGH_RATIO
    else:
        a = push.low + rng * _GOLDEN_LOW_RATIO
        b = push.low + rng * _GOLDEN_HIGH_RATIO
    zone_low, zone_high = min(a, b), max(a, b)
    if current_price > zone_high:
        pos: Literal["dans", "au_dessus", "en_dessous"] = "au_dessus"
    elif current_price < zone_low:
        pos = "en_dessous"
    else:
        pos = "dans"
    return GoldenZoneRead(
        push_direction=push.direction, zone_low=zone_low, zone_high=zone_high, price_position=pos
    )


def compute_day_open_read(bars: list[Bar], *, now_utc: datetime) -> DayOpenRead | None:
    """Excursions de la mèche du plongeur sur la fenêtre Asie+Londres
    (00h-12h Paris), figée à midi — jamais étendue dans la session NY qui fait
    le « sens final » (METHODOLOGIE §5.2 « minuit-midi », S05 re-fire M4).
    """
    paris_day = now_utc.astimezone(_PARIS_TZ).date()
    day_open_utc = datetime.combine(paris_day, time(0, 0), tzinfo=_PARIS_TZ).astimezone(UTC)
    noon_utc = datetime.combine(paris_day, time(12, 0), tzinfo=_PARIS_TZ).astimezone(UTC)
    window_end = min(now_utc, noon_utc)
    todays = [b for b in bars if day_open_utc <= b.ts < window_end]
    if not todays:
        return None
    todays.sort(key=lambda b: b.ts)
    return DayOpenRead(
        open_price=todays[0].open,
        last_price=todays[-1].close,
        high=max(b.high for b in todays),
        low=min(b.low for b in todays),
        window_complete=now_utc >= noon_utc,
    )


def _aggregate_daily_candle(
    bars: list[Bar], start_utc: datetime, end_utc: datetime
) -> tuple[float, float, float, float] | None:
    """(open, high, low, close) des barres dans [start, end), ou None sous le
    minimum de couverture intraday (jour gappy/férié/proxy RTH)."""
    win = sorted((b for b in bars if start_utc <= b.ts < end_utc), key=lambda b: b.ts)
    if len(win) < _MIN_BARS_PER_DAY:
        return None
    return win[0].open, max(b.high for b in win), min(b.low for b in win), win[-1].close


def compute_daily_read(bars: list[Bar], *, now_utc: datetime) -> DailyRead | None:
    """Lecture Daily §5.3 : classifie la DERNIÈRE bougie daily clôturée (à 22h
    Paris, §13.15) via le SSOT ``classify_daily_candle`` (avec la bougie daily
    précédente pour la détection d'avalement), lit le côté de rejet et l'attente
    de la mèche du plongeur (§5.2/§5.3). Absence honnête si la bougie close n'a
    pas assez de couverture intraday."""
    paris_now = now_utc.astimezone(_PARIS_TZ)
    today_close = datetime.combine(paris_now.date(), _DAILY_CLOSE_PARIS, tzinfo=_PARIS_TZ)
    last_close = today_close if paris_now >= today_close else today_close - timedelta(days=1)
    d1_end = last_close.astimezone(UTC)
    d1_start = (last_close - timedelta(days=1)).astimezone(UTC)
    d2_start = (last_close - timedelta(days=2)).astimezone(UTC)
    curr = _aggregate_daily_candle(bars, d1_start, d1_end)
    if curr is None:
        return None
    prev = _aggregate_daily_candle(bars, d2_start, d1_start)
    classification = classify_daily_candle(prev_ohlc=prev, curr_ohlc=curr)
    o, h, low_, c = curr
    body = abs(c - o)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - low_
    # « Fort rejet » = mèche clairement dominante (> corps ET ≥ dominance ×
    # l'autre mèche) — un quasi-doji symétrique reste « aucun » (S05 verifier).
    if lower_wick > body and lower_wick >= upper_wick * _REJECTION_DOMINANCE:
        rejection: Literal["haut", "bas", "aucun"] = "bas"
    elif upper_wick > body and upper_wick >= lower_wick * _REJECTION_DOMINANCE:
        rejection = "haut"
    else:
        rejection = "aucun"
    # §5.3 : forte poussée directionnelle (momentum/avalement) → mèche non
    # requise ; clôture en rejet (grande mèche) → mèche du plongeur attendue.
    strong = classification.kind in (
        "momentum_bull",
        "momentum_bear",
        "engulfing_bull",
        "engulfing_bear",
    )
    plongeur_expected = (not strong) and rejection != "aucun"
    return DailyRead(
        classification=classification,
        open=o,
        high=h,
        low=low_,
        close=c,
        rejection_side=rejection,
        plongeur_wick_expected=plongeur_expected,
        session_date=last_close.date(),
    )


def compute_technical_reading(
    bars: list[Bar], *, asset: str, now_utc: datetime
) -> TechnicalReading | None:
    """Full pure slice-1 read. None = honest absence (doctrine #11).

    NB : the two data_pool call sites (build_data_pool + build_asset_data_only)
    each run their own fetch with their own ``now`` — within one card the two
    reads can differ only if an H1 candle closes between the two calls
    (review PR #234 m4, accepted : the read changes only on hour close).
    """
    bars = sorted(bars, key=lambda b: b.ts)  # defensive : pure core contract
    candles = aggregate_hourly(bars, now_utc=now_utc)
    if len(candles) < _MIN_H1_CANDLES:
        return None
    pushes = segment_pushes(candles)
    current_price = bars[-1].close if bars else candles[-1].close
    zones, session_date = detect_ny_origin_zones(candles, now_utc=now_utc)
    n3_zones = detect_structure_reversals_n3(candles)

    def _proximity(z: OriginZone) -> float:
        return min(abs(current_price - z.top), abs(current_price - z.bottom))

    # METHODOLOGIE §7 : la proximité prime POUR L'ORDRE d'affichage, mais les
    # origines N1/N2 (tradables de la session NY) sont TOUJOURS conservées ; les
    # N3 (contexte, hors session) ne complètent que les slots restants, par
    # proximité — le cap pur évincerait sinon N1/N2 (S05 verifier MAJOR-2).
    n1n2 = sorted(zones, key=_proximity)
    n3_fill = sorted(n3_zones, key=_proximity)[: max(0, _MAX_ORIGIN_ZONES - len(n1n2))]
    zones_sorted = sorted(n1n2 + n3_fill, key=_proximity)
    return TechnicalReading(
        asset=asset,
        computed_at=now_utc,
        last_bar_ts=bars[-1].ts,
        current_price=current_price,
        h1_candle_count=len(candles),
        trend=read_trend(pushes),
        recent_pushes=tuple(pushes[-_TREND_WINDOW_PUSHES:]),
        origin_zones=tuple(zones_sorted),
        golden_zone=golden_zone_of_latest_push(pushes, current_price),
        day_open=compute_day_open_read(bars, now_utc=now_utc),
        ny_session_date=session_date,
        daily=compute_daily_read(bars, now_utc=now_utc),
    )


# --------------------------------------------------------------------------
# Async DB wrapper (SSOT shared by the data_pool section and future routers)
# --------------------------------------------------------------------------

_LOOKBACK_DAYS: Final = 10
"""Covers the previous completed NY session + enough H1 history for the
poussée/retournement window across weekends/holidays."""


async def assess_technical_reading(
    session: AsyncSession, asset: str, *, now_utc: datetime | None = None
) -> TechnicalReading | None:
    """Fetch 1-min bars and run the pure read (london_session pattern)."""
    from ..models import PolygonIntradayBar

    now = now_utc or datetime.now(UTC)
    rows = (
        await session.execute(
            select(
                PolygonIntradayBar.bar_ts,
                PolygonIntradayBar.open,
                PolygonIntradayBar.high,
                PolygonIntradayBar.low,
                PolygonIntradayBar.close,
            )
            .where(PolygonIntradayBar.asset == asset)
            .where(PolygonIntradayBar.bar_ts >= now - timedelta(days=_LOOKBACK_DAYS))
            .order_by(PolygonIntradayBar.bar_ts.asc())
        )
    ).all()
    bars = [
        Bar(ts=r[0], open=float(r[1]), high=float(r[2]), low=float(r[3]), close=float(r[4]))
        for r in rows
        if r[1] is not None and r[4] is not None
    ]
    return compute_technical_reading(bars, asset=asset, now_utc=now)


# --------------------------------------------------------------------------
# Render (FR, owner vocabulary, ADR-017-clean)
# --------------------------------------------------------------------------

_PROXY_CAVEATS: Final = {
    "SPX500_USD": "niveaux calculés sur le proxy ETF SPY (ADR-089), pas le cash S&P",
    "DXY": "niveaux calculés sur le proxy ETF UUP (ADR-089)",
    "NAS100_USD": (
        "données I:NDX en heures de cotation US uniquement (RTH) — fenêtres "
        "pré-marché partielles, l'open du jour lu est l'open RTH"
    ),
}

_STATE_FR: Final = {
    "continuation_haussiere": "continuation haussière",
    "continuation_baissiere": "continuation baissière",
    "retournement_potentiel_haussier": "retournement potentiel haussier",
    "retournement_potentiel_baissier": "retournement potentiel baissier",
    "indecis": "indécis",
}

_DAILY_KIND_FR: Final = {
    "momentum_bull": "poussée haussière nette",
    "momentum_bear": "poussée baissière nette",
    "uncertainty": "incertitude (doji)",
    "engulfing_bull": "avalement haussier",
    "engulfing_bear": "avalement baissier",
    "neutral": "corps moyen (neutre)",
}

_DAILY_REJET_FR: Final = {
    "bas": "rejet acheteur (grande mèche basse)",
    "haut": "rejet vendeur (grande mèche haute)",
    "aucun": "pas de rejet marqué",
}


def _fmt(p: float) -> str:
    return f"{p:.5f}".rstrip("0").rstrip(".") if abs(p) < 100 else f"{p:.2f}"


def render_technical_reading_block(
    reading: TechnicalReading | None, asset: str
) -> tuple[str, list[str]]:
    """Markdown block for Pass-2 + source stamps. Always rendered (honest
    absence prose when the read is unavailable — doctrine #11)."""
    header = "## Lecture technique — méthodologie du trader (ADR-113, lecture descriptive)"
    if reading is None:
        md = (
            f"{header}\n"
            f"- Lecture indisponible pour {asset} : pas assez de bougies H1 clôturées "
            f"dans la fenêtre récente (données intraday insuffisantes). Aucune lecture "
            f"technique n'est forcée — absence honnête.\n"
            f"- Frontière ADR-017 : cette section décrit des structures et des zones, "
            f"jamais une instruction d'exécution."
        )
        return md, [f"technical_reading:{asset}:absent"]

    lines = [header]
    caveat = _PROXY_CAVEATS.get(asset)
    if caveat:
        lines.append(f"- ⚠ {caveat}.")

    t = reading.trend
    lines.append(
        f"- **Élan H1** : {_STATE_FR[t.state]} — {t.rationale_fr} "
        f"(lecture sur {reading.h1_candle_count} bougies H1 clôturées)"
    )

    # Ligne dédiée seulement quand le retournement n'est PAS encore confirmé
    # (sur l'état confirmé, l'Élan H1 ci-dessus porte déjà le détail des indices
    # via rationale_fr — pas de doublon, S05 verifier nice-to-have).
    if t.indices_retournement and not t.confirmed_retournement:
        lines.append(
            f"- **Indices de retournement** ({len(t.indices_retournement)} accumulé(s), "
            f"pas encore de confirmation) : "
            + " ; ".join(t.indices_retournement)
            + ". (Un indice ne confirme pas seul — accumulation puis confirmation, §5.0.)"
        )

    if reading.daily is not None:
        dl = reading.daily
        plong = (
            "mèche du plongeur attendue à l'ouverture (continuation du rejet avant le sens final)"
            if dl.plongeur_wick_expected
            else "pas de mèche du plongeur requise (clôture déjà directionnelle)"
        )
        lines.append(
            f"- **Lecture Daily (dernière bougie clôturée ~22h Paris, "
            f"{dl.session_date.isoformat()})** : {_DAILY_KIND_FR.get(dl.classification.kind, dl.classification.kind)} ; "
            f"{_DAILY_REJET_FR[dl.rejection_side]} ; {plong}. "
            f"(Contexte du jour — on lit COMMENT la bougie s'est clôturée, pas la direction globale.)"
        )

    if reading.origin_zones:
        for z in reading.origin_zones:
            dist = min(abs(reading.current_price - z.top), abs(reading.current_price - z.bottom))
            rel = (
                "au-dessus"
                if z.bottom > reading.current_price
                else ("en-dessous" if z.top < reading.current_price else "au contact")
            )
            origine_ctx = (
                f"session NY du {z.session_date.isoformat()}"
                if z.level in ("N1", "N2")
                else f"retournement hors session du {z.session_date.isoformat()}"
            )
            t1, t2 = z.sub_zone_dividers
            lines.append(
                f"- **Origine {z.side} {z.level}** ({origine_ctx}) : "
                f"zone {_fmt(z.bottom)} → {_fmt(z.top)}, {rel} du prix actuel "
                f"(distance ≈ {_fmt(dist)}) ; retest pertinent entre {_fmt(z.retest_low)} et "
                f"{_fmt(z.retest_high)} (moitié côté approche) ; 3 sous-zones S/R aux paliers "
                f"{_fmt(t1)} et {_fmt(t2)}."
            )
    else:
        lines.append(
            "- **Origines NY** : aucune origine lisible sur la dernière session de New York "
            "complète (pas de momentum net dans la fenêtre 13h-16h Paris) — absence honnête."
        )

    if reading.golden_zone is not None:
        g = reading.golden_zone
        pos_fr = {"dans": "dans", "au_dessus": "au-dessus", "en_dessous": "en-dessous"}[
            g.price_position
        ]
        lines.append(
            f"- **Golden zone (0,5-0,618)** de la dernière poussée {_DIR_FR[g.push_direction]} : "
            f"{_fmt(g.zone_low)} → {_fmt(g.zone_high)} ; prix actuellement "
            f"{pos_fr} de la zone."
        )

    if reading.day_open is not None:
        d = reading.day_open
        phase = (
            "mèche Asie/Londres figée à midi"
            if d.window_complete
            else "fenêtre Asie/Londres en cours, avant midi Paris"
        )
        lines.append(
            f"- **Mèche du plongeur ({phase})** : depuis l'open 00h Paris "
            f"({_fmt(d.open_price)}), sur la fenêtre minuit-midi excursion haute "
            f"+{_fmt(d.upside_excursion)} / excursion basse −{_fmt(d.downside_excursion)}, "
            f"dernier prix lu {_fmt(d.last_price)}. "
            f"Pour un sens final baissier en NY, la respiration haussière "
            f"{'est déjà visible' if d.upside_excursion > d.downside_excursion else 'n’est pas encore marquée'} ; "
            f"pour un sens final haussier, la respiration baissière "
            f"{'est déjà visible' if d.downside_excursion > d.upside_excursion else 'n’est pas encore marquée'}. "
            f"(Asie + Londres construisent la mèche contraire minuit-midi ; New York fait le sens final.)"
        )

    lines.append(
        "- _Lecture descriptive selon la méthodologie codifiée du trader "
        "(docs/METHODOLOGIE_TECHNIQUE_ELIOT.md) : élan + position face aux origines. "
        "Jamais de signal d'exécution — la décision reste humaine (ADR-017)._"
    )
    sources = [
        # Same namespace as the london-session section (review PR #234 m5) :
        # `polygon:` carries Polygon tickers elsewhere, `polygon_intraday:`
        # carries our asset codes.
        f"polygon_intraday:{asset}@{reading.last_bar_ts.isoformat()}",
        "methodologie:ADR-113",
    ]
    return "\n".join(lines), sources
