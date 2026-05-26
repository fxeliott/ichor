"""r164 Strand D — Scenario Invalidation Monitor.

ADR-106 §175 Stride 1 continuation : poll-and-compare service that consumes
``session_card_audit.scenarios[].invalidations[]`` JSONB (populated by r163
Strand C Pass-6 system prompt) and evaluates each ``InvalidationCondition``
against current data from the appropriate Ichor data source.

Architecture
============

This module is the second-half of the Strand 1 invalidation engine :

  - **Strand A (shipped r161 ``8c94d4b``)** : ``Scenario.invalidations`` Pydantic
    schema + ``INVALIDATION_METRIC_NAMES`` 33-entry whitelist.
  - **Strand H (shipped r161 ``649db43``)** : ``SessionVerdict`` Pydantic
    contract + ``ScenarioInvalidationState`` aggregation shape +
    NEW ADR-106.
  - **Strand G (shipped r161 ``29d4c40``)** : ``<SessionVerdictPanel>`` apex
    LIVE on /briefing/[asset] (consumer surface).
  - **Strand C (shipped r163 ``2b9e565``)** : Pass-6 ``_SYSTEM`` prompt
    populated with invalidation generation instructions + schema example +
    33-metric whitelist verbatim + ADR-017 boundary extend.
  - **Strand D (THIS MODULE, r164)** : monitor service evaluating each
    ``InvalidationCondition`` against current data.
  - **Strand E (r165)** : alerts catalog 33 evaluators + alerts_runner
    integration for hard-invalidation alerting via canonical Ichor alert pipeline.
  - **Strand F (r165)** : ``cli/run_scenario_invalidation_check.py`` +
    ``register-cron-scenario-invalidation-check.sh`` (6×/jour Paris cadence
    00/04/08/12/16/20) for automatic invalidation polling.
  - **Strand activation (r166)** : R-DEPLOY-6 the full stack + Settings
    flag flip ``enable_scenarios=True`` after empirical Pass-6 validation
    ≥3 production sessions.

The 6-source dispatcher
========================

The 33-metric ``INVALIDATION_METRIC_NAMES`` whitelist maps to 5 evaluable
data source types + 1 honest-gap class. Coverage : 28/33 evaluable (84.8 %),
5/33 honest gap (15.2 %, documented per doctrine #11 calibrated honesty).

  1. **FRED** (12 metrics) : ``fred_observations`` table queried by
     ``series_id``. Pattern : strip ``FRED_`` prefix to get series_id ; VIX
     is a special case (no FRED\\_ prefix in whitelist but stored under
     ``series_id="VIXCLS"`` per ``collectors/fred.py:30``).
  2. **Polygon** (11 metrics) : ``polygon_intraday`` table queried by
     ``asset`` (e.g., ``"DXY"``, ``"EURUSD"``, ``"SPX500"``, ``"NAS100"``).
     The polygon collector uses asset codes directly matching the
     ``INVALIDATION_METRIC_NAMES`` constant.
  3. **CBOE SKEW** (1 metric) : ``cboe_skew_observations`` table — daily
     SKEW reading, latest row by observation_date.
  4. **CBOE VVIX** (1 metric) : ``cboe_vvix_observations`` table — daily
     VVIX reading, latest row by observation_date.
  5. **Polymarket** (3 metrics) : ``polymarket_snapshots`` table queried
     by ``slug`` (derived from the ``POLY_*`` metric name by lowercase +
     underscore-to-dash + strip ``poly-`` prefix : ``POLY_FED_CUTS_2026
     → fed-cuts-2026``).
  6. **HONEST GAP** (5 metrics) : returns ``"not_evaluable"`` (doctrine #11
     calibrated honesty — never fabricate a status the system cannot truly
     measure).
       - ``MOVE`` : no dedicated FRED series or table ; ``fred_extended.py``
         notes ``BAMLC0A0CM`` as an IG-OAS proxy but that's credit, not
         MOVE-index. r167+ candidate : dedicated MOVE collector OR replace
         ``MOVE`` in whitelist with a measurable substitute.
       - ``EVENT_HORMUZ_VOLUME_PCT`` / ``EVENT_IRAN_CEASEFIRE_STATUS`` /
         ``EVENT_TRUMP_TARIFF_STATUS`` : no clean polled source. The
         eventual source is the ``news_items`` / ``gdelt_events`` tables
         filtered by keyword, but the mapping requires an NLP scoring
         layer (Couche-2 ``news_nlp`` agent extension r167+). r164 honest
         gap : evaluator returns ``"not_evaluable"`` + a sentinel.

The 4 direction operators
=========================

The Pass-6 LLM emits one of 4 direction operators per invalidation :

  - ``above`` : current_value > threshold (single-row query)
  - ``below`` : current_value < threshold (single-row query)
  - ``crosses_above`` : previous_value < threshold AND current_value >
    threshold (two-row query — state transition detection)
  - ``crosses_below`` : previous_value > threshold AND current_value <
    threshold (two-row query — state transition detection)

Each evaluator function below implements all 4 operators uniformly for its
source type. The two-row query for ``crosses_*`` orders by the source's
natural time index (``bar_ts`` for polygon, ``observation_date`` for FRED/
CBOE, ``fetched_at`` for polymarket) DESC LIMIT 2.

Aggregation : ``ScenarioInvalidationState``
============================================

The top-level ``evaluate_scenario_invalidations()`` aggregator walks each
of the 7 Pass-6 buckets, evaluates each bucket's ``invalidations[]`` list,
and aggregates by severity into 3 lists :

  - ``scenarios_invalidated_hard`` : at least one ``severity=hard`` fired
  - ``scenarios_invalidated_soft`` : at least one ``severity=soft`` fired
    (and no hard fired)
  - ``scenarios_with_notes`` : at least one ``severity=note`` fired (and
    no hard/soft fired)

A bucket can appear in only ONE list (strict hierarchy hard > soft > note)
to keep the consumer-side display unambiguous.

Doctrine alignment
===================

  - **ADR-017 boundary** : zero ``BUY/SELL/TP/SL`` interaction. The
    monitor reads data, evaluates threshold breaches, returns status
    enums. Never produces a trade signal.
  - **ADR-022 cap-95** : irrelevant here (no probability emission).
  - **ADR-023 Couche-2 Haiku** : irrelevant here (no LLM call).
  - **Voie D** : ZERO Anthropic SDK import. Pure async SQL + Python
    comparisons. Voie D streak +1 = 82 rounds.
  - **Doctrine #2 strict scope** : single module, single responsibility
    (poll-and-compare) ; alerts_runner integration deferred Strand E.
  - **Doctrine #4 SSOT** : ``InvalidationCondition`` + ``Scenario`` +
    ``ScenarioInvalidationState`` + ``BUCKET_LABELS`` imported from
    ``ichor_brain.scenarios`` and ``ichor_brain.session_verdict``
    canonical sources.
  - **Doctrine #9 anti-accumulation** : the dispatcher routes by
    metric_name prefix, no duplication of source-type literal sets.
  - **Doctrine #11 calibrated honesty** : 5 metrics return
    ``"not_evaluable"`` rather than fabricate ; aggregator gracefully
    handles all-not-evaluable buckets by NOT adding them to any
    invalidated list (the verdict consumer sees no false-positive).
  - **Doctrine #12 anti-recidive** : Pattern #15 R59 pre-flight verified
    each source-type table schema first-hand at r164 Phase 0 (not
    inferring from sub-agent reports).

Build gate target post-r164 ship
=================================

  - pytest test_invariants_ichor + test_scenarios + test_coach_macro_context_router
    + NEW test_scenario_invalidation_monitor → maintain baseline 90+/90+ + new tests
  - ruff lint + format clean
  - NEW W90 invariant : ``test_invalidation_metric_lockstep_coverage`` —
    every entry in INVALIDATION_METRIC_NAMES MUST have a routing branch
    in this module's dispatcher (CI guard against future drift)
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from ichor_brain.scenarios import (
    INVALIDATION_METRIC_NAMES,
    InvalidationCondition,
)
from ichor_brain.session_verdict import (
    BUCKET_LABELS,
    BucketLabel,
    ScenarioInvalidationState,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    CboeSkewObservation,
    CboeVvixObservation,
    FredObservation,
    PolygonIntradayBar,
    PolymarketSnapshot,
    SessionCardAudit,
)

# ── Status enum (returned by evaluators) ────────────────────────────────


InvalidationStatus = Literal[
    "fired_hard",  # condition breached AND severity=hard
    "fired_soft",  # condition breached AND severity=soft
    "fired_note",  # condition breached AND severity=note
    "not_fired",  # condition NOT breached (current data within bound)
    "not_evaluable",  # honest gap : no data source OR insufficient data
]


# ── Source-type classification ──────────────────────────────────────────


_FRED_PREFIXED = {
    "FRED_DGS10",
    "FRED_DGS2",
    "FRED_DGS30",
    "FRED_DFII10",
    "FRED_T10Y2Y",
    "FRED_T10YIE",
    "FRED_BAMLH0A0HYM2",
    "FRED_NFCI",
    "FRED_DTWEXBGS",
    "FRED_CPIAUCSL",
    "FRED_PCEPI",
    "FRED_PAYEMS",
}
"""r164 Strand D — the 12 FRED-sourced metrics. The series_id used to
query ``fred_observations`` is derived by stripping the ``FRED_`` prefix.
"""


_POLYGON_DIRECT = {
    "DXY",
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "USDCAD",
    "AUDUSD",
    "SPX500",
    "NAS100",
    "XAUUSD",
    "BRENT",
    "WTI",
}
"""r164 Strand D — the 11 metrics queried by ``polygon_intraday.asset``.
Note : the polygon collector translates asset names to ticker codes
internally (e.g., ``DXY → I:DXY``, ``XAUUSD → C:XAUUSD``,
``SPX500 → SPY``) per ``collectors/polygon.py``. The ``asset`` column in
``polygon_intraday`` table stores the Ichor canonical name (``"DXY"``,
``"EURUSD"``, etc.), not the polygon ticker. This evaluator queries by
asset name directly.

Note BRENT/WTI : if the polygon collector doesn't yet ingest these, the
``not_evaluable`` fallback kicks in honestly (no row found in the lookback
window).
"""


_VIX_SPECIAL = "VIX"
"""r164 Strand D — VIX is in the whitelist without ``FRED_`` prefix but is
stored in ``fred_observations.series_id="VIXCLS"`` per
``collectors/fred.py:30``. Special-case routing."""


_CBOE_SKEW = "SKEW"
_CBOE_VVIX = "VVIX"


_POLYMARKET_PREFIXED = {
    "POLY_FED_CUTS_2026",
    "POLY_FED_HIKE_2026",
    "POLY_RECESSION_2026",
}
"""r164 Strand D — the 3 Polymarket-sourced metrics. Slug derivation rule
(see ``_polymarket_slug_from_metric``) : ``POLY_FED_CUTS_2026 →
fed-cuts-2026``."""


_HONEST_GAPS_R164 = {
    "MOVE",
    "EVENT_HORMUZ_VOLUME_PCT",
    "EVENT_IRAN_CEASEFIRE_STATUS",
    "EVENT_TRUMP_TARIFF_STATUS",
}
"""r164 Strand D — 4 metrics for which Ichor has NO clean polled source
yet. Returns ``"not_evaluable"`` per doctrine #11 calibrated honesty —
the verdict consumer sees the bucket as NOT invalidated rather than a
fabricated status.

r165+ enhancement candidates :
  - MOVE : dedicated MOVE-index collector (Bloomberg / ICE proxies) OR
    replace in whitelist with a measurable substitute.
  - EVENT_HORMUZ_VOLUME_PCT : Strait of Hormuz tanker count from Lloyd's
    List or shipping AIS feeds (paid, currently no clean source).
  - EVENT_IRAN_CEASEFIRE_STATUS : Couche-2 ``news_nlp`` agent extension
    to track a curated keyword set against ``news_items`` table with
    NLP confidence scoring.
  - EVENT_TRUMP_TARIFF_STATUS : Same pattern as IRAN_CEASEFIRE — Couche-2
    extension monitoring keywords on news_items / Truth-Social via the
    real-time feed (Stride 2 of ADR-106 roadmap)."""


def _classify_metric_source(
    metric_name: str,
) -> Literal[
    "fred",
    "polygon",
    "cboe_skew",
    "cboe_vvix",
    "polymarket",
    "honest_gap",
]:
    """Pure-fn classifier : route a ``metric_name`` to its data source type.

    Order of checks matters : the VIX special-case must be checked BEFORE
    the polygon prefix-free set (since "VIX" is a 3-letter token that
    could theoretically clash with future polygon asset names — but
    today no clash). Keep the explicit order for defensiveness.
    """
    if metric_name in _FRED_PREFIXED:
        return "fred"
    if metric_name == _VIX_SPECIAL:
        return "fred"
    if metric_name in _POLYGON_DIRECT:
        return "polygon"
    if metric_name == _CBOE_SKEW:
        return "cboe_skew"
    if metric_name == _CBOE_VVIX:
        return "cboe_vvix"
    if metric_name in _POLYMARKET_PREFIXED:
        return "polymarket"
    if metric_name in _HONEST_GAPS_R164:
        return "honest_gap"
    # Defensive : a metric in INVALIDATION_METRIC_NAMES that doesn't match
    # any of the above means the whitelist drifted from this dispatcher.
    # The CI invariant ``test_invalidation_metric_lockstep_coverage``
    # catches this at build time ; runtime treats it as honest_gap.
    return "honest_gap"


def _fred_series_id_for(metric_name: str) -> str:
    """Translate a FRED-sourced metric_name to its ``series_id`` column
    value in ``fred_observations``."""
    if metric_name == _VIX_SPECIAL:
        return "VIXCLS"
    # All FRED_-prefixed metrics : strip the prefix.
    if metric_name.startswith("FRED_"):
        return metric_name[5:]
    # Defensive fallback.
    return metric_name


def _polymarket_slug_from_metric(metric_name: str) -> str:
    """Derive the ``polymarket_snapshots.slug`` value from a ``POLY_*``
    metric name. Convention : lowercase + underscore-to-dash + strip
    ``poly-`` prefix.

    Examples :
      - ``POLY_FED_CUTS_2026 → "fed-cuts-2026"``
      - ``POLY_FED_HIKE_2026 → "fed-hike-2026"``
      - ``POLY_RECESSION_2026 → "recession-2026"``

    The actual slug stored in the table depends on the polymarket
    collector's ingest convention ; this derivation is a best-effort
    that will need empirical verification against prod data on r164
    deploy (r165 carry-forward : write a smoke test that confirms
    these 3 slugs match an actual ``polymarket_snapshots`` row in prod).
    """
    return metric_name.lower().replace("_", "-").removeprefix("poly-")


# ── Direction evaluation primitive ──────────────────────────────────────


def _evaluate_direction(
    *,
    current_value: float,
    previous_value: float | None,
    threshold: float,
    direction: Literal["above", "below", "crosses_above", "crosses_below"],
) -> bool:
    """Pure-fn direction operator evaluator.

    For ``crosses_*`` operators, returns False if ``previous_value`` is None
    (insufficient history to detect transition — caller MUST surface as
    ``"not_evaluable"`` not ``"not_fired"`` to preserve doctrine #11
    honesty ; this primitive is unaware of that distinction and just
    returns False).
    """
    if direction == "above":
        return current_value > threshold
    if direction == "below":
        return current_value < threshold
    if direction == "crosses_above":
        if previous_value is None:
            return False  # caller's responsibility to convert to not_evaluable
        return previous_value < threshold and current_value > threshold
    if direction == "crosses_below":
        if previous_value is None:
            return False
        return previous_value > threshold and current_value < threshold
    # Pydantic Literal validator catches this upstream ; defensive only.
    raise ValueError(f"unknown direction operator : {direction!r}")


def _needs_two_tick_memory(
    direction: Literal["above", "below", "crosses_above", "crosses_below"],
) -> bool:
    """``crosses_*`` operators need previous-tick memory ; ``above``/
    ``below`` are stateless."""
    return direction in ("crosses_above", "crosses_below")


def _resolve_status(
    *,
    fired: bool,
    severity: Literal["hard", "soft", "note"],
) -> InvalidationStatus:
    """Map ``(fired, severity)`` to the canonical 5-state status enum."""
    if not fired:
        return "not_fired"
    if severity == "hard":
        return "fired_hard"
    if severity == "soft":
        return "fired_soft"
    if severity == "note":
        return "fired_note"
    raise ValueError(f"unknown severity : {severity!r}")


# ── Per-source evaluators ───────────────────────────────────────────────
# Each evaluator returns one of the InvalidationStatus values. Pure async
# SQL + Python comparisons ; zero LLM calls (Voie D) ; zero side-effects
# (read-only) ; deterministic for a given (db_snapshot, condition).


async def _evaluate_fred(
    session: AsyncSession,
    *,
    series_id: str,
    threshold: float,
    direction: Literal["above", "below", "crosses_above", "crosses_below"],
    severity: Literal["hard", "soft", "note"],
    lookback_days: int = 30,
) -> InvalidationStatus:
    """Evaluate a FRED-sourced metric. Queries the most-recent N observations
    (N=2 for crosses_*, N=1 for above/below). Returns ``"not_evaluable"``
    when insufficient observations are stored.
    """
    needs_two = _needs_two_tick_memory(direction)
    since = (datetime.now(UTC) - timedelta(days=lookback_days)).date()
    stmt = (
        select(FredObservation.value)
        .where(
            FredObservation.series_id == series_id,
            FredObservation.observation_date >= since,
            FredObservation.value.is_not(None),
        )
        .order_by(FredObservation.observation_date.desc())
        .limit(2 if needs_two else 1)
    )
    rows = (await session.execute(stmt)).scalars().all()
    if not rows:
        return "not_evaluable"
    current = float(rows[0])
    previous = float(rows[1]) if needs_two and len(rows) >= 2 else None
    if needs_two and previous is None:
        return "not_evaluable"
    fired = _evaluate_direction(
        current_value=current,
        previous_value=previous,
        threshold=threshold,
        direction=direction,
    )
    return _resolve_status(fired=fired, severity=severity)


async def _evaluate_polygon(
    session: AsyncSession,
    *,
    asset: str,
    threshold: float,
    direction: Literal["above", "below", "crosses_above", "crosses_below"],
    severity: Literal["hard", "soft", "note"],
    lookback_minutes: int = 120,
) -> InvalidationStatus:
    """Evaluate a polygon_intraday-sourced metric. Queries the most-recent
    N 1-minute bars by ``bar_ts`` for the given asset. Uses ``close`` price
    as the comparison value (consistent with how the Pass-6 LLM would
    interpret "DXY > 108" — close, not open/high/low).
    """
    needs_two = _needs_two_tick_memory(direction)
    since = datetime.now(UTC) - timedelta(minutes=lookback_minutes)
    stmt = (
        select(PolygonIntradayBar.close)
        .where(
            PolygonIntradayBar.asset == asset,
            PolygonIntradayBar.bar_ts >= since,
        )
        .order_by(PolygonIntradayBar.bar_ts.desc())
        .limit(2 if needs_two else 1)
    )
    rows = (await session.execute(stmt)).scalars().all()
    if not rows:
        return "not_evaluable"
    current = float(rows[0])
    previous = float(rows[1]) if needs_two and len(rows) >= 2 else None
    if needs_two and previous is None:
        return "not_evaluable"
    fired = _evaluate_direction(
        current_value=current,
        previous_value=previous,
        threshold=threshold,
        direction=direction,
    )
    return _resolve_status(fired=fired, severity=severity)


async def _evaluate_cboe_skew(
    session: AsyncSession,
    *,
    threshold: float,
    direction: Literal["above", "below", "crosses_above", "crosses_below"],
    severity: Literal["hard", "soft", "note"],
    lookback_days: int = 30,
) -> InvalidationStatus:
    """Evaluate the CBOE SKEW metric from ``cboe_skew_observations``."""
    needs_two = _needs_two_tick_memory(direction)
    since = (datetime.now(UTC) - timedelta(days=lookback_days)).date()
    stmt = (
        select(CboeSkewObservation.skew_value)
        .where(CboeSkewObservation.observation_date >= since)
        .order_by(CboeSkewObservation.observation_date.desc())
        .limit(2 if needs_two else 1)
    )
    rows = (await session.execute(stmt)).scalars().all()
    if not rows:
        return "not_evaluable"
    current = float(rows[0])
    previous = float(rows[1]) if needs_two and len(rows) >= 2 else None
    if needs_two and previous is None:
        return "not_evaluable"
    fired = _evaluate_direction(
        current_value=current,
        previous_value=previous,
        threshold=threshold,
        direction=direction,
    )
    return _resolve_status(fired=fired, severity=severity)


async def _evaluate_cboe_vvix(
    session: AsyncSession,
    *,
    threshold: float,
    direction: Literal["above", "below", "crosses_above", "crosses_below"],
    severity: Literal["hard", "soft", "note"],
    lookback_days: int = 30,
) -> InvalidationStatus:
    """Evaluate the CBOE VVIX metric from ``cboe_vvix_observations``."""
    needs_two = _needs_two_tick_memory(direction)
    since = (datetime.now(UTC) - timedelta(days=lookback_days)).date()
    stmt = (
        select(CboeVvixObservation.vvix_value)
        .where(CboeVvixObservation.observation_date >= since)
        .order_by(CboeVvixObservation.observation_date.desc())
        .limit(2 if needs_two else 1)
    )
    rows = (await session.execute(stmt)).scalars().all()
    if not rows:
        return "not_evaluable"
    current = float(rows[0])
    previous = float(rows[1]) if needs_two and len(rows) >= 2 else None
    if needs_two and previous is None:
        return "not_evaluable"
    fired = _evaluate_direction(
        current_value=current,
        previous_value=previous,
        threshold=threshold,
        direction=direction,
    )
    return _resolve_status(fired=fired, severity=severity)


async def _evaluate_polymarket(
    session: AsyncSession,
    *,
    slug: str,
    threshold: float,
    direction: Literal["above", "below", "crosses_above", "crosses_below"],
    severity: Literal["hard", "soft", "note"],
    lookback_hours: int = 48,
) -> InvalidationStatus:
    """Evaluate a Polymarket-sourced metric from ``polymarket_snapshots``.

    Uses the first element of ``last_prices`` JSONB list as the canonical
    probability ([0, 1]). Binary Polymarket markets emit
    ``["yes_prob", "no_prob"]`` with no_prob = 1 - yes_prob ; multi-outcome
    markets emit longer lists. The Pass-6 LLM is instructed to set
    threshold in [0, 1] probability units (per ``passes/scenarios.py``
    THRESHOLD UNIT CONVENTION section shipped r163).
    """
    needs_two = _needs_two_tick_memory(direction)
    since = datetime.now(UTC) - timedelta(hours=lookback_hours)
    stmt = (
        select(PolymarketSnapshot.last_prices)
        .where(
            PolymarketSnapshot.slug == slug,
            PolymarketSnapshot.fetched_at >= since,
        )
        .order_by(PolymarketSnapshot.fetched_at.desc())
        .limit(2 if needs_two else 1)
    )
    rows = (await session.execute(stmt)).scalars().all()
    if not rows:
        return "not_evaluable"

    def _first_price(prices: object) -> float | None:
        """Defensive : the JSONB column may return a Python list (typical)
        or, in pathological cases, something else. Return None on any
        mismatch so the evaluator falls back to ``not_evaluable``."""
        if not isinstance(prices, list) or not prices:
            return None
        try:
            return float(prices[0])
        except (TypeError, ValueError):
            return None

    current = _first_price(rows[0])
    if current is None:
        return "not_evaluable"
    previous: float | None = None
    if needs_two:
        if len(rows) < 2:
            return "not_evaluable"
        previous = _first_price(rows[1])
        if previous is None:
            return "not_evaluable"
    fired = _evaluate_direction(
        current_value=current,
        previous_value=previous,
        threshold=threshold,
        direction=direction,
    )
    return _resolve_status(fired=fired, severity=severity)


# ── Public dispatcher : one condition ────────────────────────────────────


async def evaluate_invalidation(
    session: AsyncSession,
    *,
    condition: InvalidationCondition,
) -> InvalidationStatus:
    """Evaluate one ``InvalidationCondition`` against current data.

    Dispatches to the appropriate source-type evaluator per
    ``_classify_metric_source(condition.metric_name)``. Returns one of the
    5 canonical ``InvalidationStatus`` values.

    This is the single public entry point per condition — the aggregator
    ``evaluate_scenario_invalidations()`` calls this in a loop over each
    bucket's invalidations list.
    """
    source = _classify_metric_source(condition.metric_name)

    if source == "fred":
        return await _evaluate_fred(
            session,
            series_id=_fred_series_id_for(condition.metric_name),
            threshold=condition.threshold,
            direction=condition.direction,
            severity=condition.severity,
        )
    if source == "polygon":
        return await _evaluate_polygon(
            session,
            asset=condition.metric_name,
            threshold=condition.threshold,
            direction=condition.direction,
            severity=condition.severity,
        )
    if source == "cboe_skew":
        return await _evaluate_cboe_skew(
            session,
            threshold=condition.threshold,
            direction=condition.direction,
            severity=condition.severity,
        )
    if source == "cboe_vvix":
        return await _evaluate_cboe_vvix(
            session,
            threshold=condition.threshold,
            direction=condition.direction,
            severity=condition.severity,
        )
    if source == "polymarket":
        return await _evaluate_polymarket(
            session,
            slug=_polymarket_slug_from_metric(condition.metric_name),
            threshold=condition.threshold,
            direction=condition.direction,
            severity=condition.severity,
        )
    # source == "honest_gap" : doctrine #11 calibrated honesty.
    return "not_evaluable"


# ── Aggregator : whole 7-bucket scenario card ────────────────────────────


async def evaluate_scenario_invalidations(
    session: AsyncSession,
    *,
    session_card_id: str,
    now_utc: datetime | None = None,
) -> ScenarioInvalidationState | None:
    """Aggregate invalidation status across the 7 buckets of a session card.

    Reads ``session_card_audit.scenarios`` JSONB for the given card ID,
    walks each bucket's ``invalidations[]`` list, evaluates each
    ``InvalidationCondition`` via the dispatcher, and aggregates by
    severity into the 3 lists of ``ScenarioInvalidationState``.

    A bucket is classified by the HIGHEST severity that fired (strict
    hierarchy hard > soft > note) — appearing in only ONE of the 3 lists
    to keep the consumer-side display unambiguous. Buckets where all
    conditions are ``"not_fired"`` OR ``"not_evaluable"`` are absent from
    all 3 lists (the consumer interprets absence as "this bucket's
    mechanism remains plausible").

    Returns ``None`` if :
      - the session card ID doesn't exist (caller's responsibility to
        handle ; typically means the verdict builder was passed a stale ID)
      - the card has ``scenarios=[]`` (Pass-6 didn't run yet ; pre-r163
        emissions OR ``enable_scenarios=False`` orchestrator default)
      - the card has scenarios but with empty ``invalidations`` arrays
        across all buckets (legitimate pre-r163 emissions where the LLM
        hadn't been prompted to populate the field)

    Doctrine #11 calibrated honesty : returning ``None`` is a LEGITIMATE
    output. The verdict consumer (``session_verdict_builder.py``) treats
    ``None`` as "no invalidation state available" — different from
    "invalidations evaluated, none fired" (which is a non-None
    ``ScenarioInvalidationState`` with 3 empty lists).
    """
    now = now_utc or datetime.now(UTC)

    # Read the card's scenarios JSONB.
    stmt = select(SessionCardAudit.scenarios).where(SessionCardAudit.id == session_card_id).limit(1)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    if not isinstance(row, list) or not row:
        return None

    # Walk the 7 buckets ; collect per-bucket highest-severity fired status.
    invalidated_hard: list[BucketLabel] = []
    invalidated_soft: list[BucketLabel] = []
    with_notes: list[BucketLabel] = []
    any_invalidation_seen = False

    for bucket_raw in row:
        if not isinstance(bucket_raw, dict):
            continue
        label_raw = bucket_raw.get("label")
        if label_raw not in BUCKET_LABELS:
            continue
        label: BucketLabel = label_raw  # type: ignore[assignment]

        bucket_invalidations_raw = bucket_raw.get("invalidations", [])
        if not isinstance(bucket_invalidations_raw, list) or not bucket_invalidations_raw:
            continue

        # Track the highest severity fired for this bucket.
        bucket_hard_fired = False
        bucket_soft_fired = False
        bucket_note_fired = False

        for cond_raw in bucket_invalidations_raw:
            if not isinstance(cond_raw, dict):
                continue
            try:
                condition = InvalidationCondition.model_validate(cond_raw)
            except (TypeError, ValueError):
                # ADR-017 regex OR whitelist validator rejected this entry.
                # Doctrine #11 : skip silently, do NOT treat as fired.
                continue
            any_invalidation_seen = True

            status = await evaluate_invalidation(session, condition=condition)
            if status == "fired_hard":
                bucket_hard_fired = True
            elif status == "fired_soft":
                bucket_soft_fired = True
            elif status == "fired_note":
                bucket_note_fired = True
            # "not_fired" and "not_evaluable" → do nothing (doctrine #11)

        # Strict hierarchy : a bucket is in AT MOST one of the 3 lists.
        if bucket_hard_fired:
            invalidated_hard.append(label)
        elif bucket_soft_fired:
            invalidated_soft.append(label)
        elif bucket_note_fired:
            with_notes.append(label)

    if not any_invalidation_seen:
        # No invalidations were even attempted (all buckets had empty lists
        # OR malformed entries). Return None per docstring contract — the
        # verdict consumer interprets this as "monitor has no data to
        # report yet" rather than "all clear".
        return None

    return ScenarioInvalidationState(
        scenarios_invalidated_hard=invalidated_hard,
        scenarios_invalidated_soft=invalidated_soft,
        scenarios_with_notes=with_notes,
        last_check_utc=now,
    )


# ── Public exports ──────────────────────────────────────────────────────


__all__ = [
    "InvalidationStatus",
    "evaluate_invalidation",
    "evaluate_scenario_invalidations",
]


# ── Lockstep validation helper (used by CI invariant test) ──────────────


def all_whitelist_metrics_have_router_branch() -> tuple[bool, Sequence[str]]:
    """CI invariant helper. Returns ``(True, [])`` if every metric in
    ``INVALIDATION_METRIC_NAMES`` is routed by ``_classify_metric_source``
    to a NON-honest-gap source (i.e., the system has a real evaluator
    for it), OR is explicitly listed in ``_HONEST_GAPS_R164``. Returns
    ``(False, missing)`` if any metric is uncovered.

    This is the symmetric pin to the W90 invariant ``test_pass6_system_
    prompt_lists_metric_name_whitelist`` (r163) : that test ensures the
    LLM prompt enumerates the whitelist verbatim ; THIS function ensures
    the runtime dispatcher has a route for each entry. Together they
    close the loop : prompt → emission → schema → monitor → status.
    """
    missing: list[str] = []
    covered_classes = (
        _FRED_PREFIXED
        | {_VIX_SPECIAL}
        | _POLYGON_DIRECT
        | {_CBOE_SKEW, _CBOE_VVIX}
        | _POLYMARKET_PREFIXED
        | _HONEST_GAPS_R164
    )
    for metric in INVALIDATION_METRIC_NAMES:
        if metric not in covered_classes:
            missing.append(metric)
    return (not missing, sorted(missing))


# Defensive : silence unused-import warning for `date` if it appears
# elsewhere ; presently the evaluators use `datetime.now(UTC).date()`
# which is `date`-typed via `timedelta` arithmetic. Keep the import.
_ = date
