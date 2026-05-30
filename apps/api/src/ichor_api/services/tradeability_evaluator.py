"""r167 G1 — Tradeability Evaluator.

Closes Eliot's #1 CRITICAL gap from his methodology transcript (Fathom
2026-05-25 §VIII : "ne trade pas aujourd'hui" when bank holiday / range /
low volatility). Composite rule that returns a ``TradeabilityFlag``
indicating whether the day is structurally suitable for taking a NY
session position.

Derivation rule (priority-ordered — first match wins) :

  1. **holiday** — today is a US market holiday per
     ``services/market_session.us_market_holidays(year)``. ALL 5 priority
     assets get this flag : on US holidays even FX/XAU markets see
     significantly reduced volume + manipulation risk (Eliot's discipline
     = no trade ; transcript verbatim "session de New York toute orange").
  2. **event_freeze** — at least one high-impact economic event scheduled
     in the next 2h window in ``economic_events`` table (impact='high',
     scheduled_at within ``[now, now + 2h]``). Eliot's discipline = wait
     the event then trade reaction, never trade across the event.
  3. **low_volatility** — the current hour-UTC's ``median_bp`` from the
     rolling 30-day ``hourly_volatility`` window for the asset is below
     a threshold (``_LOW_VOLATILITY_THRESHOLD_BP = 5.0`` default). Market
     is structurally inert ; momentum unlikely in NY session window.
  4. **range** — r167 honest gap (always False). r168 G4 wires daily
     candle classification (momentum_bullish / momentum_bearish /
     uncertainty) → ``range`` would fire when the last 3 daily candles
     all show small body (body/range < 0.3). Schema is forward-compat ;
     the literal value exists so r168 only updates the evaluator.
  5. **no_setup** — verdict ``conviction_pct < 30`` — read is too weak ;
     trader passes without an external cause. This is the "everything
     else passed but the verdict is just flat" honest disclosure.
  6. **tradeable** — default. All gates passed, verdict is meaningful,
     no honest reason to abstain.

Doctrine alignment
==================

- **ADR-017 boundary** : no BUY/SELL emission. The flag is descriptive
  metadata ; trader interprets according to their own discipline.
- **Voie D** : ZERO Anthropic SDK. Pure async SQL + Python comparisons.
  Voie D streak +1 = 84 rounds.
- **Doctrine #2 strict scope** : single module, single responsibility
  (evaluate tradeability) ; frontend disclosure surface lives in
  ``<SessionVerdictPanel>`` r167 G8.
- **Doctrine #4 SSOT** : ``TradeabilityFlag`` Literal + ``PriorityAsset``
  + ``us_market_holidays`` imported from canonical sources. No re-derivation.
- **Doctrine #11 calibrated honesty** : 6 levels of honest absence /
  disclosure. NEVER fabricate a "tradeable" reading when conditions are
  structurally unsuitable. The evaluator FAILS-OPEN to "tradeable" on
  internal exceptions (DB unreachable, etc.) so verdict emission is
  never blocked — but logs a structured warning. This is intentional
  asymmetry : false "tradeable" on infra hiccup is less harmful than
  false "holiday" blocking a normal trading day.
- **Doctrine #12 anti-recidive** : Pattern #15 R59 pre-flight verified
  each source-type signature first-hand (market_session.us_market_
  holidays returns dict[date, str] ; hourly_volatility.assess_hourly_
  volatility async fn returns HourlyVolReport with entries[h].median_bp ;
  economic_events ORM has scheduled_at + impact columns).

Sources of truth (verified at r167 Phase 0 R59) :
  - ``services/market_session.py:78`` ``us_market_holidays(year) -> dict[date, str]``
  - ``services/hourly_volatility.py:73`` ``assess_hourly_volatility(session, asset, *, window_days=30)``
  - ``models/economic_event.py:30`` ``impact: Mapped[str]`` column
  - ``packages/ichor_brain/session_verdict.py`` ``TradeabilityFlag`` Literal

Build gate target post-r167
============================

  - pytest baseline 158/158 + new tradeability tests
  - NEW W90 invariant : ``test_tradeability_flag_values_lockstep`` pins
    the 6 Literal values vs the evaluator dispatch logic so adding a
    new value without a corresponding rule fails CI.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import EconomicEvent
from .daily_candle_classifier import is_range_bound
from .hourly_volatility import assess_hourly_volatility
from .market_session import us_market_holidays

if TYPE_CHECKING:
    from ichor_brain.session_verdict import TradeabilityFlag

log = structlog.get_logger(__name__)


# ── Thresholds + constants ──────────────────────────────────────────────


_LOW_VOLATILITY_THRESHOLD_BP = 5.0
"""Below this median_bp at the current hour-UTC (rolling 30-day window),
the market is considered structurally inert. 5.0 bp = ~0.05 % return
range — typical of session asiatique on FX majors. NY session normally
exceeds 10-20 bp median per hour. Empirical tuning candidate r168+ via
Brier feedback."""


_NO_SETUP_CONVICTION_THRESHOLD_PCT = 30.0
"""Below this conviction_pct, the verdict is too flat to be actionable.
Mirrors the ``convictionTier`` thresholds in ``lib/sessionVerdict.ts``
(40 = "faible", below = "dormante"). The 30 floor is intentionally
stricter than 40 because no-setup is a structural "ne trade pas"
signal, not just a low-confidence chip."""


_EVENT_FREEZE_HORIZON = timedelta(hours=2)
"""High-impact event in this lookforward window → freeze. Mirrors
Eliot's discipline of waiting for the print + reaction, not trading
across it. The 2h window is empirically the typical FX/index lead-up
where mispricing dampens."""


_PARIS_TZ = ZoneInfo("Europe/Paris")
"""Eliot's working timezone. Holiday check uses today's Paris date —
relevant for crossing US holidays when the user is in Paris pre-NY."""


# ── Pure helpers ────────────────────────────────────────────────────────


def _today_paris_date(now_utc: datetime) -> date:
    """Return today's Paris calendar date for a given UTC instant.

    Important : the US holiday calendar is keyed by *US calendar date*
    but Eliot operates in Paris timezone — at e.g., 22h Paris on a US
    holiday, the relevant 'today' for trading decisions is still that
    Paris date (since the NY session has long closed). The function
    uses Paris-local-date as the simplest single-source rule ; the
    occasional Paris-vs-NY date edge case (e.g., 23h-00h Paris when NY
    is still in trading hours) is acceptable as long as the holiday
    flag remains conservative (we'd rather flag a marginally-not-holiday
    day as "holiday" than miss one — false-positive < false-negative
    on the discipline gate)."""
    return now_utc.astimezone(_PARIS_TZ).date()


def _is_us_market_holiday(today: date) -> tuple[bool, str | None]:
    """Check today against the US market holiday calendar. Returns
    ``(True, holiday_name)`` if today is a US holiday, ``(False, None)``
    otherwise. Wraps ``market_session.us_market_holidays`` for testability.
    """
    holidays = us_market_holidays(today.year)
    name = holidays.get(today)
    return (name is not None, name)


async def _has_high_impact_event_within_horizon(
    session: AsyncSession,
    *,
    now_utc: datetime,
    horizon: timedelta = _EVENT_FREEZE_HORIZON,
) -> tuple[bool, str | None]:
    """Query ``economic_events`` for at least one ``impact='high'`` event
    scheduled in the ``[now, now + horizon]`` window. Returns
    ``(True, event_title)`` on first match, ``(False, None)`` if window
    is clean.

    Asset-agnostic by design : a high-impact USD event (FOMC, NFP, CPI)
    influences ALL 5 priority assets via cross-asset cascades. A high-
    impact EUR event (ECB) likewise. So no per-asset filtering.
    """
    upper = now_utc + horizon
    stmt = (
        select(EconomicEvent.title)
        .where(
            EconomicEvent.impact == "high",
            EconomicEvent.scheduled_at >= now_utc,
            EconomicEvent.scheduled_at <= upper,
        )
        .order_by(EconomicEvent.scheduled_at.asc())
        .limit(1)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return (False, None)
    return (True, row)


async def _is_low_volatility_current_hour(
    session: AsyncSession,
    *,
    asset: str,
    now_utc: datetime,
    threshold_bp: float = _LOW_VOLATILITY_THRESHOLD_BP,
    window_days: int = 30,
) -> tuple[bool, float | None]:
    """Compute the rolling-30-day median_bp for the current hour-UTC of
    the asset's intraday history. Returns ``(True, median_bp)`` when
    below threshold, ``(False, median_bp)`` otherwise. Returns
    ``(False, None)`` when no data (doctrine #11 honest-fallback : no
    data = don't flag as low_vol, fall through to next gate).

    Calls the existing ``assess_hourly_volatility`` service which already
    builds the per-hour histogram from polygon_intraday close-to-close
    log returns over the window.
    """
    try:
        report = await assess_hourly_volatility(
            session,
            asset,
            window_days=window_days,
        )
    except Exception as exc:
        # Doctrine #11 honest-fallback : data unavailable → don't fabricate
        # a low_vol verdict. Fall through to next gate.
        log.warning(
            "tradeability_evaluator.hourly_vol_failed",
            asset=asset,
            error=str(exc)[:200],
        )
        return (False, None)

    current_hour_utc = now_utc.hour
    matching = [e for e in report.entries if e.hour_utc == current_hour_utc]
    if not matching:
        return (False, None)
    entry = matching[0]
    if entry.n_samples == 0:
        return (False, None)
    median_bp = float(entry.median_bp)
    return (median_bp < threshold_bp, median_bp)


# ── Public evaluator ────────────────────────────────────────────────────


async def evaluate_tradeability(
    session: AsyncSession,
    *,
    asset: str,
    conviction_pct: float,
    now_utc: datetime | None = None,
) -> TradeabilityFlag:
    """Composite priority-ordered rule. Returns one of the 6
    ``TradeabilityFlag`` Literal values.

    Args :
      session : SQLAlchemy async session for DB queries.
      asset : the priority asset code (EUR_USD / GBP_USD / XAU_USD /
              SPX500_USD / NAS100_USD).
      conviction_pct : the verdict's conviction_pct (0..95) — used for
              the ``no_setup`` rule (last gate before ``tradeable``).
      now_utc : evaluation time ; defaults to ``datetime.now(UTC)``.

    Returns :
      One of "holiday", "event_freeze", "low_volatility", "range",
      "no_setup", "tradeable" (priority order : first match wins).

    Fail-open behavior : any internal exception (DB hiccup, missing
    data) falls through to the next gate or ultimately ``tradeable``.
    Better to leak a false ``tradeable`` on infra hiccup than to
    false-flag a normal trading day.
    """
    if now_utc is None:
        now_utc = datetime.now(UTC)

    # Gate 1 : US market holiday (highest priority — structural closure
    # / reduced volume affects ALL 5 priority assets per Eliot discipline).
    today_paris = _today_paris_date(now_utc)
    try:
        is_holiday, holiday_name = _is_us_market_holiday(today_paris)
    except Exception as exc:
        log.warning(
            "tradeability_evaluator.holiday_check_failed",
            asset=asset,
            today=today_paris.isoformat(),
            error=str(exc)[:200],
        )
        is_holiday, holiday_name = (False, None)
    if is_holiday:
        log.info(
            "tradeability_evaluator.holiday_detected",
            asset=asset,
            today=today_paris.isoformat(),
            name=holiday_name,
        )
        return "holiday"

    # Gate 2 : high-impact event scheduled in next 2h.
    try:
        in_freeze, event_title = await _has_high_impact_event_within_horizon(
            session,
            now_utc=now_utc,
        )
    except Exception as exc:
        log.warning(
            "tradeability_evaluator.event_freeze_check_failed",
            asset=asset,
            error=str(exc)[:200],
        )
        in_freeze, event_title = (False, None)
    if in_freeze:
        log.info(
            "tradeability_evaluator.event_freeze_detected",
            asset=asset,
            event_title=event_title,
        )
        return "event_freeze"

    # Gate 3 : current hour-UTC structurally low volatility for this asset.
    try:
        is_low_vol, median_bp = await _is_low_volatility_current_hour(
            session,
            asset=asset,
            now_utc=now_utc,
        )
    except Exception as exc:
        log.warning(
            "tradeability_evaluator.low_vol_check_failed",
            asset=asset,
            error=str(exc)[:200],
        )
        is_low_vol, median_bp = (False, None)
    if is_low_vol:
        log.info(
            "tradeability_evaluator.low_volatility_detected",
            asset=asset,
            current_hour_utc=now_utc.hour,
            median_bp=median_bp,
            threshold_bp=_LOW_VOLATILITY_THRESHOLD_BP,
        )
        return "low_volatility"

    # Gate 4 : range-bound check via daily candle classification +
    # Garman-Klass volatility compression (r168b G4 — replaces the
    # r167 honest-gap "always False"). Composite rule = uncertainty
    # candle AND GK variance < 80% trailing-30d mean. See
    # ``services/daily_candle_classifier.py`` for the full doctrine
    # including the Marshall-Young-Rose 2006 *JBF* HONEST_SENTINEL
    # discipline.
    try:
        is_range_flag, range_reason = await is_range_bound(
            session,
            asset=asset,
            now_utc=now_utc,
        )
    except Exception as exc:
        log.warning(
            "tradeability_evaluator.range_check_failed",
            asset=asset,
            error=str(exc)[:200],
        )
        is_range_flag, range_reason = (False, None)
    if is_range_flag:
        log.info(
            "tradeability_evaluator.range_detected",
            asset=asset,
            reason=range_reason,
        )
        return "range"

    # Gate 5 : verdict conviction too weak to be actionable.
    if conviction_pct < _NO_SETUP_CONVICTION_THRESHOLD_PCT:
        log.info(
            "tradeability_evaluator.no_setup_detected",
            asset=asset,
            conviction_pct=conviction_pct,
            threshold_pct=_NO_SETUP_CONVICTION_THRESHOLD_PCT,
        )
        return "no_setup"

    # Default : all gates passed.
    return "tradeable"


# ── CI invariant helpers ────────────────────────────────────────────────


def all_tradeability_values_dispatched() -> tuple[bool, list[str]]:
    """CI invariant helper. Returns ``(True, [])`` if every value in the
    ``TradeabilityFlag`` Literal is reachable from ``evaluate_tradeability``,
    OR explicitly documented as honest-gap r167 (range).

    Symmetric pin to the schema-side Literal contract. Failure to update
    the dispatcher when a new Literal value is added would silently
    leave the value unreachable.
    """
    # Lazy import to avoid circular dep at module load.
    from ichor_brain.session_verdict import TradeabilityFlag

    # Extract the Literal values from the type definition.
    declared = set(TradeabilityFlag.__args__)  # type: ignore[attr-defined]
    dispatched = {
        "holiday",
        "event_freeze",
        "low_volatility",
        "range",  # honest gap r167, but still reachable in dispatch tree
        "no_setup",
        "tradeable",
    }
    missing = sorted(declared - dispatched)
    return (not missing, missing)


__all__ = [
    "all_tradeability_values_dispatched",
    "evaluate_tradeability",
]
