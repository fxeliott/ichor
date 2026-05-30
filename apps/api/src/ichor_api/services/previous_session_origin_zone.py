"""r174 FOUNDATION + r179 EXECUTION — previous-session origin zone classifier (Eliot Fathom §V).

Pure-compute service materialising Eliot's Fathom 2026-05-25 §V verbatim
methodology : « savoir d'où vient le mouvement de la session précédente,
son zone d'origine, son sens, ses hauts et bas ». The trader's read of
which session zone (Asian / London / NY) DROVE the dominant move of the
immediately preceding session, with high/low/direction stamped, is a
context input to the NY position-taking decision.

## FOUNDATION-only scope at r174 (mirror r160 Dukascopy pattern)

r174 shipped ONLY the schema + skeleton fn returning None. ZERO behavior
change at r174 deploy time. r179 EXECUTION (this commit) ships the
actual classifier logic. The FOUNDATION pattern is identical to r160
Dukascopy MVP : ship the shell, prove the contract (Pydantic + tests
+ ADR cite), then ship EXECUTION (compute logic + persistence) in a
subsequent atomic round once trader-leverage is empirically validated.

## Citation provenance (Pattern #15 R59 verified 2026-05-28)

**R59 pre-flight subagent ac56d1c644ce45309 VERDICT** : « previous-session
origin zone » with Asian/London/NY breakdown is a **RETAIL/PRACTITIONER
(ICT — Inner Circle Trader style) concept**, NOT academic. NO peer-
reviewed paper directly supports this framing.

**Primary provenance** : Eliot Fathom recording 2026-05-25 §V verbatim
practitioner methodology — Eliot describes reading the previous
session's high/low + dominant direction as a context input to the
position-taking decision. This is a Mark-Douglas-class « 5 truths »
discipline (each session is unique, but the recent context informs
the probability read).

**Stamp** : `provenance = "practitioner_stamp"` (NOT `"peer_reviewed"`)
+ practitioner_source pointer to Eliot Fathom 2026-05-25 §V transcript.

### Honest scope acknowledgement (r174 R59 META 10ème catch preserved)

Pattern #15 R59 cumulative META self-catches in 6-round span :
- r168b : Kaul-Sapp 2008 *JBF* « intraday momentum » HALLU → corrected to Elaut-Frömmel-Lampaert 2018 *JFM*
- r173 RED-1 : Rogers-Satchell journal wrong (*Math Finance* → *Annals of Applied Probability*)
- r173 RED-2 : Bauer 2024 jump-test cite HALLUCINATED
- **r174 10ème META** : Baltussen 2021 topic mismatch (gamma hedging ≠ session zones)

Closest legitimate academic neighbors (NONE a direct fit) :
- Heston-Korajczyk-Sadka 2010 *J Finance* 65(4):1369-1407 DOI 10.1111/j.1540-6261.2010.01573.x (cross-section half-hour periodicity, NOT 3-session-zone framing)
- Lou-Polk-Skouras 2019 *JFE* 134(1):192-213 DOI 10.1016/j.jfineco.2019.03.011 (overnight vs intraday 2-component decomposition, NOT 3-zone)
- Parkinson 1980 *J Business* 53(1):61-65 (high-low range estimator — VARIANCE only, NOT directional zone semantics)

These can be cited for ARITHMETIC components (e.g., Parkinson for high-low
range) but NOT for the « session origin zone » semantic framing itself,
which remains practitioner-stamp.

## ADR-017 boundary

Pure factual snapshot (high price + low price + directional sign).
NEVER a directional bias output for the CURRENT session — the snapshot
is INPUT to Pass-2 narrative + trader decision, NOT an output.

## Session zone definitions (non-overlapping by UTC hour)

Per Eliot Fathom §V + standard FX desk convention, ATTRIBUTING each
1-min bar to ONE zone via its ``bar_ts.hour`` (UTC) :

- **Asian session** : ``[0, 7)`` UTC — Tokyo + Sydney + Hong Kong
- **London session** : ``[7, 13)`` UTC — London cash open through NY pre-open
- **NY session** : ``[13, 21)`` UTC — NYSE RTH 13:30-20:00 UTC + extended FX

Off-hours bars (``[21, 24)`` UTC) are attributed to the NY zone (late-NY
rollover) so the previous-session zone is the most recent.

Asset class adjustments :
- **FX / XAU** : 24/5 trading → all 3 zones apply, weekend gap → empty bars
- **NAS100 / SPX500** : NYSE RTH only → only NY zone has meaningful bars,
  Asian/London → empty bars → graceful skip (still returns NY-dominant
  snapshot when bar_count >= 30)

## r179 EXECUTION-phase algorithm (5 steps, this commit)

1. **Window resolution** : ``[now_utc - 24h, now_utc)`` rolling window over
   the previous 24 hours of ``polygon_intraday`` 1-min bars. Weekend
   handling is implicit — empty bars on Sat/Sun trigger
   ``bar_count < 30`` honest-absence return None.

2. **Polygon intraday query** : async ``SELECT ... FROM polygon_intraday
   WHERE asset = :asset AND bar_ts >= :start AND bar_ts < :end ORDER BY
   bar_ts ASC``. Bars sorted ascending so ``[0].open`` is the session
   open and ``[-1].close`` is the session close.

3. **Zone decomposition** : per ``_classify_zone(bar_ts)``, map each bar
   to one of {asian, london, ny}. Build per-zone bar lists.

4. **Dominant zone selection** : compute per-zone ``(high, low, open,
   close, bar_count)`` metrics ; rank by ``abs(close - open)`` descending,
   tie-breaker ``NY > London > Asian`` per FX desk convention (NY is the
   price-discovery zone). Skip empty zones.

5. **Direction classification** : body / range ratio threshold :
   - ``body = abs(close - open)`` ; ``range = high - low``
   - If ``range <= 0`` OR ``body / range < 0.3`` : ``range`` (range-bound)
   - Else if ``close > open`` : ``up`` (directional)
   - Else : ``down``

   The ``0.3`` threshold is practitioner-grade (Eliot Fathom §V « bodies
   > 30% of range = directional ») ; r180+ calibration via Phase D Brier
   feedback can refine if empirically warranted.

Returns ``OriginZoneSnapshot`` when (a) bars exist in window AND (b) the
dominant zone has ``bar_count >= 30`` (Cohen 1988 n=30 small-sample
threshold, mirror of ``rolling_corr_low_n`` HONEST_SENTINEL). Otherwise
returns ``None`` (honest absence per doctrine #11 calibrated honesty).

## Doctrine alignment

- ADR-017 boundary : pure factual snapshot, never directional bias output
- Doctrine #2 strict scope : r179 ships EXECUTION-phase compute logic
  ONLY ; consumer wiring (Pass-2 data-pool injection + frontend
  ``<OriginZoneSnapshot>`` panel) lands r180+ once empirical validation
  against historical sessions passes
- Doctrine #4 SSOT : session-zone boundaries inline-defined as module
  constants ; if a future ADR introduces a 4th zone (e.g., Mideast or
  Sydney sub-decomposition), the constants update here once and the
  ``_classify_zone()`` helper picks up the change automatically
- Doctrine #5 pure-module discipline : ``_classify_zone`` +
  ``_compute_zone_metrics`` + ``_pick_dominant_zone`` +
  ``_classify_direction`` are pure functions, fully unit-testable
  without DB/network
- Doctrine #11 calibrated honesty : returns ``None`` on (a) no bars
  (weekend/holiday) OR (b) ``bar_count < 30`` in dominant zone ;
  NEVER fabricates a snapshot to fill the void
- Doctrine #12 anti-recidive : R59 pre-flight obligatoire HONORED at
  r174 ship for Baltussen 2021 cargo-cult catch ; this r179 EXECUTION
  commit re-anchors to same practitioner-stamp provenance
- Mirror r160 Dukascopy FOUNDATION → EXECUTION pattern (ADR-099
  §Impl(r160) + §Impl(r161) for the EXECUTION ship)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ─────────────────────────────────── DOMAIN ─────────────────────────────

SessionZoneLabel = Literal["asian", "london", "ny"]
"""Canonical 3-zone enum for the 24-hour FX trading day. Boundaries
defined in module docstring. Per Eliot Fathom §V + standard FX desk
convention. NEW zones MUST land via ADR amendment (e.g., « Mideast »
or « Sydney » sub-decomposition if empirically needed)."""


OriginDirection = Literal["up", "down", "range"]
"""Direction of the previous-session dominant move :
- ``up`` : close > open + body / range >= 0.3
- ``down`` : close < open + body / range >= 0.3
- ``range`` : neither (consolidation / chop) — body / range < 0.3 OR
  range == 0 (all bars identical)

Threshold ``0.3`` is practitioner-grade (Eliot Fathom §V « bodies > 30%
of range = directional »). r180+ Phase D Brier calibration may refine."""


@dataclass(frozen=True)
class OriginZoneSnapshot:
    """Previous-session origin zone snapshot.

    Eliot Fathom §V verbatim practitioner methodology — the trader's
    read of which session zone DROVE the dominant move of the
    immediately preceding session, with high/low/direction stamped.

    Doctrine #11 calibrated honesty fields :
    - ``bar_count`` : honest sample-size disclosure (1-min bars from
      ``polygon_intraday`` over the session window). When < 30 bars,
      the snapshot is unreliable ; classifier returns None in that case
      (HONEST_SENTINEL ``rolling_corr_low_n`` analog).
    - ``start_utc`` / ``end_utc`` : exact session window stamps
      (timezone-aware, UTC). r179 EXECUTION : these stamp the
      first and last bar's ``bar_ts`` within the dominant zone.

    Frozen for cache safety + structural-immutability discipline
    (mirror ``CorrelationMatrix`` r171a pattern).
    """

    session_zone: SessionZoneLabel
    """Which of the 3 session zones drove the dominant previous-session
    move. For multi-zone sessions (e.g., London → NY trend continuation),
    classifier picks the zone with the LARGEST absolute return ; tie-
    breaker NY > London > Asian per FX desk convention."""

    high_price: float
    """Maximum bar.high observed during the dominant session zone window."""

    low_price: float
    """Minimum bar.low observed during the dominant session zone window."""

    direction: OriginDirection
    """Net direction of the dominant move : up / down / range."""

    bar_count: int
    """Number of 1-min ``polygon_intraday`` bars in the dominant
    session zone window. Used for sample-size sanity check per
    Cohen 1988 n=30 threshold (mirror ``rolling_corr_low_n`` sentinel).
    Snapshots with ``bar_count < 30`` cannot be emitted — classifier
    returns ``None`` at that threshold."""

    start_utc: datetime
    """Inclusive UTC start of the dominant session zone window
    (timestamp of the first bar in the zone)."""

    end_utc: datetime
    """Exclusive UTC end of the dominant session zone window
    (timestamp of the last bar in the zone)."""


# ─────────────────────────────────── r179 EXECUTION CONSTANTS ─────────

_PREVIOUS_SESSION_LOOKBACK: Final[timedelta] = timedelta(hours=24)
"""Rolling window length for the « previous session » query. 24h covers
the full Asian + London + NY day cycle including overlap zones. Weekend
gaps are handled implicitly by empty-bar honest-absence return None."""

_MIN_BAR_COUNT: Final[int] = 30
"""Cohen 1988 §3.3 small-sample threshold. Dominant zone must have at
least 30 bars (~30 minutes of 1-min data) for the snapshot to be
reliable. Below this, classifier returns None per HONEST_SENTINEL
``rolling_corr_low_n`` analog discipline."""

_DIRECTIONAL_THRESHOLD_RATIO: Final[float] = 0.3
"""Body / range ratio threshold for directional vs range classification.
Practitioner-grade (Eliot Fathom §V « bodies > 30% of range »).
r180+ Phase D Brier calibration may refine."""

_ZONE_PRIORITY: Final[tuple[SessionZoneLabel, ...]] = ("ny", "london", "asian")
"""Tie-breaker priority for ``_pick_dominant_zone()``. NY > London >
Asian per FX desk convention (NY is the price-discovery zone). When
two zones have identical ``abs(close - open)``, NY wins, then London."""


# ─────────────────────────────────── r179 EXECUTION HELPERS (PURE) ────


def _classify_zone(bar_ts: datetime) -> SessionZoneLabel:
    """Pure : map a UTC bar timestamp to its session zone label.

    Non-overlapping decomposition by ``bar_ts.hour`` (UTC) :
    - Asian : ``[0, 7)``
    - London : ``[7, 13)``
    - NY : ``[13, 24)``  (includes 21-24 late-NY rollover)

    The classification is timezone-safe : ``bar_ts`` MUST be a UTC-aware
    datetime ; naive datetimes are accepted but their ``.hour`` attribute
    is read verbatim (caller's responsibility to pass UTC-aware values
    via the ORM ``DateTime(timezone=True)`` discipline).
    """
    h = bar_ts.hour
    if 0 <= h < 7:
        return "asian"
    if 7 <= h < 13:
        return "london"
    return "ny"  # 13 <= h < 24 (NY + late-NY rollover)


@dataclass(frozen=True)
class _ZoneMetrics:
    """Internal : per-zone aggregated metrics used by the dominant-zone
    selector. Frozen + immutable per Doctrine #5 pure-module discipline.
    Not exported — consumers read the public ``OriginZoneSnapshot`` only.
    """

    zone: SessionZoneLabel
    high: float
    low: float
    open: float
    close: float
    bar_count: int
    start_utc: datetime
    end_utc: datetime

    @property
    def abs_return(self) -> float:
        """``|close - open|`` — magnitude of the zone's directional move."""
        return abs(self.close - self.open)


def _compute_zone_metrics(
    bars: list[Any],
    zone: SessionZoneLabel,
) -> _ZoneMetrics | None:
    """Pure : aggregate ascending-sorted ``PolygonIntradayBar`` list
    into single zone-level metrics. Returns ``None`` if ``bars`` empty.

    Caller responsibility : ``bars`` MUST be sorted ascending by
    ``bar_ts`` so ``bars[0].open`` is the zone open and ``bars[-1].close``
    is the zone close. Empty-list is the canonical « zone absent for
    this asset class » signal (e.g., NAS100/SPX500 outside NYSE RTH).
    """
    if not bars:
        return None
    return _ZoneMetrics(
        zone=zone,
        high=max(b.high for b in bars),
        low=min(b.low for b in bars),
        open=bars[0].open,
        close=bars[-1].close,
        bar_count=len(bars),
        start_utc=bars[0].bar_ts,
        end_utc=bars[-1].bar_ts,
    )


def _pick_dominant_zone(metrics: list[_ZoneMetrics]) -> _ZoneMetrics | None:
    """Pure : ``argmax(abs_return)`` with NY > London > Asian tie-break.

    Returns ``None`` if ``metrics`` empty. Otherwise returns the zone with
    the largest ``abs(close - open)``. On ties, the zone with the
    smaller ``_ZONE_PRIORITY`` index wins (NY index 0, London index 1,
    Asian index 2).
    """
    if not metrics:
        return None
    priority_index = {zone: i for i, zone in enumerate(_ZONE_PRIORITY)}
    # Sort descending by abs_return ; tie-break ascending by priority index.
    sorted_metrics = sorted(
        metrics,
        key=lambda m: (-m.abs_return, priority_index[m.zone]),
    )
    return sorted_metrics[0]


def _classify_direction(
    open_p: float,
    close_p: float,
    high: float,
    low: float,
) -> OriginDirection:
    """Pure : body / range ratio classification (Eliot Fathom §V).

    - ``range <= 0`` (all bars identical OR malformed) : ``range``
    - ``body / range < 0.3`` : ``range`` (range-bound session)
    - ``close > open`` AND threshold-met : ``up``
    - ``close < open`` AND threshold-met : ``down``
    - ``close == open`` AND threshold-met : ``range`` (zero-body edge)

    Symmetric : the function is invariant under (open ↔ close, up ↔ down)
    swap, which mirrors the practitioner mental model.
    """
    session_range = high - low
    if session_range <= 0:
        return "range"
    body = abs(close_p - open_p)
    if body / session_range < _DIRECTIONAL_THRESHOLD_RATIO:
        return "range"
    if close_p > open_p:
        return "up"
    if close_p < open_p:
        return "down"
    return "range"  # close_p == open_p but threshold met (defensive)


# ─────────────────────────────────── r179 EXECUTION MAIN ───────────────


async def compute_previous_session_origin_zone(
    session: AsyncSession,
    asset: str,
    *,
    now_utc: datetime,
) -> OriginZoneSnapshot | None:
    """r179 EXECUTION-phase — 5-step classifier per module docstring.

    Returns an ``OriginZoneSnapshot`` when (a) ``polygon_intraday`` has
    bars in the previous-24h window for ``asset`` AND (b) the dominant
    zone has ``bar_count >= 30``. Otherwise returns ``None`` (honest
    absence per doctrine #11).

    Args:
        session : SQLAlchemy async session — used for the
            ``polygon_intraday`` query.
        asset : Asset code (e.g. ``"EUR_USD"``, ``"NAS100_USD"``).
            Strings outside the priority-5 universe are accepted but
            will typically return ``None`` (no bars persisted for them).
        now_utc : UTC wall-clock datetime — anchors the previous-session
            window. MUST be timezone-aware UTC for correct ORM compare.

    Returns:
        ``OriginZoneSnapshot`` with the dominant zone's metrics, OR
        ``None`` if no bars OR dominant zone too small.

    Doctrine #11 calibrated honesty : when in doubt, return ``None``.
    The consumer (Pass-2 data-pool injection, r180+) interprets ``None``
    as « previous-session context unavailable » and surfaces honestly
    to the trader rather than fabricating a read.
    """
    # Lazy import to avoid circular dep with apps/api models package
    # and to keep the helper functions importable without ORM at
    # test-collection time.
    from ..models import PolygonIntradayBar

    # Step 1 : resolve window — previous 24h rolling window.
    window_end = now_utc
    window_start = now_utc - _PREVIOUS_SESSION_LOOKBACK

    # Step 2 : query polygon_intraday — ascending order ensures
    # bars[0] is the session open and bars[-1] is the session close.
    result = await session.execute(
        select(PolygonIntradayBar)
        .where(PolygonIntradayBar.asset == asset)
        .where(PolygonIntradayBar.bar_ts >= window_start)
        .where(PolygonIntradayBar.bar_ts < window_end)
        .order_by(PolygonIntradayBar.bar_ts.asc())
    )
    bars: list[Any] = list(result.scalars().all())
    if not bars:
        return None  # honest absence : no data in window (weekend/holiday)

    # Step 3 : zone decomposition — non-overlapping UTC hour buckets.
    zone_bars: dict[SessionZoneLabel, list[Any]] = {
        "asian": [],
        "london": [],
        "ny": [],
    }
    for bar in bars:
        zone_bars[_classify_zone(bar.bar_ts)].append(bar)

    # Compute per-zone metrics, skip empty zones (e.g., NAS100/SPX500
    # outside NYSE RTH ; weekend gap for FX/XAU).
    metrics: list[_ZoneMetrics] = []
    for zone in _ZONE_PRIORITY:  # iterate in priority order for determinism
        m = _compute_zone_metrics(zone_bars[zone], zone)
        if m is not None:
            metrics.append(m)

    # Step 4 : pick dominant zone — argmax(abs_return), tie-break NY > London > Asian.
    dominant = _pick_dominant_zone(metrics)
    if dominant is None:
        return None  # defensive : metrics list is empty (all zones absent)
    if dominant.bar_count < _MIN_BAR_COUNT:
        return None  # honest absence per Cohen 1988 n=30 small-sample threshold

    # Step 5 : classify direction — body / range ratio.
    direction = _classify_direction(
        open_p=dominant.open,
        close_p=dominant.close,
        high=dominant.high,
        low=dominant.low,
    )

    return OriginZoneSnapshot(
        session_zone=dominant.zone,
        high_price=dominant.high,
        low_price=dominant.low,
        direction=direction,
        bar_count=dominant.bar_count,
        start_utc=dominant.start_utc,
        end_utc=dominant.end_utc,
    )
