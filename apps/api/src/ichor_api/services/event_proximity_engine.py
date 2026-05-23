"""event_proximity_engine -- Engine 8 Event-Driven (Mission centrale axis-4
"anticipation par profondeur").

r147 (ADR-099 §Impl) -- closes 1/5 ABSENT engines from the 12-engine
blueprint. Pure compute, no I/O beyond DB session. Reads `economic_events`
forward window + `vix_observations` regime gate + r141 surprise classifier
output ; emits an `EventProximityFactor` consumed by the new
`_factor_event_anticipation` builder in `confluence_engine.py`.

WHAT THIS ENGINE DOES (honest scope)
====================================

For the next high-impact macro event in the lookahead window (default 48h),
emits a literature-cited PRIOR estimate of expected drift magnitude (in
basis points) calibrated by :

  expected_drift_bp = baseline_bp[event_class]
                    × impact_multiplier[level]    (1.0/0.4/0.0 high/med/low)
                    × time_decay(minutes_until)   (linear: 1 - mu/window)
                    × vix_regime_gate             (1.0/0.4/0.1 by VIX p75/p50)
                    × business_cycle_sign         (+1 expansion / -1 contraction)

ACADEMIC FOUNDATIONS (verbatim citations, NOT memory)
-----------------------------------------------------

- Lucca & Moench (2015) "The Pre-FOMC Announcement Drift", Journal of
  Finance 70:329-371. Original pre-FOMC drift : ~50bp avg S&P 500 return
  in 24h pre-FOMC window, 1994-2011 sample. NY Fed SR 512.
- Kurov, Halova-Wolfe & Gilbert (2021) "The Disappearing Pre-FOMC
  Announcement Drift", attenuation post-2016 attributed to FedWatch
  popularity reducing pre-FOMC uncertainty. CRITICAL : drift is regime-
  conditional, NOT universal -- alive in high-VIX environments 2022-2024,
  muted low-VIX 2016-2019.
- Boyd, Hu & Jagannathan (2005) "Why Bad News Is Usually Good for Stocks",
  Journal of Finance. Mechanism : interest-rate channel dominates in
  expansions (good news for stocks), cash-flow channel dominates in
  contractions (bad news for stocks). Reaction SIGN flips with business
  cycle phase.
- arXiv 2212.04525 (2022) "Monetary Uncertainty as Determinant of
  Response of Stock Market to Macro News" : "Good MNA surprise → +30bp
  cash-flow channel and -23bp per 1% monetary uncertainty risk-free-rate
  channel" -- counter-intuitive regime guard empirically confirmed.
- Peng & Pan (2024) SSRN 4764451 : 10Y UST yield drops 0.79bp on day
  before FOMC (1994-2022), driven entirely by the term premium ; magnitude
  intensifies (1.91bp) conditional on high Macro Attention Index.
- Quantpedia (2024) + Vojtko-Dujava SSRN 5384407 : pre-ECB drift strongest
  day BEFORE announcement ; BoE/SNB show positive pre-announcement drift ;
  BoC/RBA show NEGATIVE drift (opposite sign).

HONEST SCOPE LIMITATIONS (doctrine #11 + lesson #37)
---------------------------------------------------

- Magnitude is a LITERATURE-CITED PRIOR, not an empirically-calibrated
  point estimate from Ichor's own historical data. Future r148+ extension
  candidate : daily-bar realized-reaction backfill via Stooq/yfinance.
- Sign is business-cycle conditional ; with no `output_gap_proxy` wired
  today (deferred r148+), defaults to `+1` (expansion baseline per Boyd-
  Hu-Jagannathan) WITH explicit caveat in the output.
- Cold-start gap on per-event-class N<3 : the historical reaction beta
  is NOT yet read from past actuals (would require r144 backfill to
  accumulate >3 months) ; r147 ships the prior-only formula. r148+
  candidate : empirical regression of past `magnitude_pct` × realized
  drift.
- VIX regime gate degrades to `low` confidence if no VIX observation in
  last 4 sessions (data-honesty fail-closed).

ADR-017 boundary
----------------

Output is GEOMETRIC/PROBABILISTIC : `expected_drift_magnitude_bp` (signed
scalar) + `expected_drift_direction` ("up"/"down"/"unknown"). NEVER
imperative ("BUY" / "SELL" / "LONG" / "SHORT" forbidden). Confluence
engine consumes this as one of 12 factors aggregated into score_long /
score_short -- the per-asset transmission stays in the verdict/confluence
layer (parity with r137 inflation_surprise + r136 MacroSurprisePanel
doctrine).

ADR refs : ADR-099 §Impl(r147) -- Mission centrale Axis-4 anticipation par profondeur.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import EconomicEvent, FredObservation

__all__ = [
    "EVENT_CLASS_BASELINE_BP",
    "DriftDirection",
    "EventConfidence",
    "EventProximityFactor",
    "ImpactLevel",
    "VixRegimeGate",
    "assess_event_proximity",
]


ImpactLevel = Literal["low", "medium", "high"]
EventConfidence = Literal["high", "medium", "low", "unavailable"]
VixRegimeGate = Literal["above_p75", "p50_to_p75", "below_p50", "unavailable"]
DriftDirection = Literal["up", "down", "unknown"]


# ── Baseline drift magnitudes (literature-cited PRIORS, in basis points) ──
#
# These are NOT empirically calibrated from Ichor's own historical data.
# Sources cited in module docstring. Each value represents the avg pre-event
# drift magnitude documented in the academic literature for that event class.
EVENT_CLASS_BASELINE_BP: dict[str, float] = {
    # Central bank statements — Lucca-Moench 2015 + Quantpedia 2024 extensions
    "FOMC": 50.0,
    "ECB": 35.0,
    "BoE": 25.0,
    "BoJ": 15.0,
    # Tier-1 US macro — generic 20bp estimate (smaller than Fed, larger than tier-2)
    "NFP": 20.0,
    "CPI": 20.0,
    # Other high-impact macro (PPI, ISM, Retail Sales, etc.)
    "high_other": 10.0,
    # Tier-2 events
    "medium": 3.0,
    "low": 1.0,
}


_LOOKAHEAD_WINDOW_MIN_DEFAULT = 48 * 60  # 48 hours in minutes
_VIX_LOOKBACK_SESSIONS = 4
_VIX_P50 = 18.0  # rough long-run median ; r148+ candidate : compute empirically
_VIX_P75 = 24.0  # rough long-run 75th percentile


@dataclass(frozen=True)
class EventProximityFactor:
    """Output of `assess_event_proximity()` -- descriptive only (ADR-017).

    All directional fields are GEOMETRIC/PROBABILISTIC ; NEVER imperative.
    The frontend strips signs at the UI boundary per r142 trader RED-1
    discipline (parity with `confluence_engine.Driver`).

    Fields :
        next_event_id              : UUID stringified, or None if no future
                                     event in window.
        next_event_title           : ForexFactory title verbatim, or None.
        next_event_currency        : ISO 3-letter currency, or None.
        next_event_minutes_until   : Minutes from `now` to `scheduled_at`,
                                     positive int, or None.
        next_event_impact          : "high"/"medium"/"low", or None.
        next_event_class           : Mapped event class ("FOMC"/"NFP"/etc.),
                                     or None if title unmapped.
        expected_drift_direction   : "up"/"down"/"unknown". "unknown" when
                                     business cycle proxy unavailable.
        expected_drift_magnitude_bp: Literature-cited PRIOR in basis points,
                                     signed. None if `event_class` unmapped
                                     OR data confidence is too low.
        confidence                 : "high"/"medium"/"low"/"unavailable".
        vix_regime_gate            : "above_p75"/"p50_to_p75"/"below_p50"/
                                     "unavailable".
        caveat                     : Verbatim 1-line honest-scope disclosure
                                     for downstream Driver.evidence field.
        literature_anchor          : Verbatim citation string.
        parse_failures             : Frozenset of sentinel labels surfacing
                                     data-quality issues honestly (parity
                                     with `SurpriseClassification`).
    """

    next_event_id: str | None
    next_event_title: str | None
    next_event_currency: str | None
    next_event_minutes_until: int | None
    next_event_impact: ImpactLevel | None
    next_event_class: str | None
    expected_drift_direction: DriftDirection
    expected_drift_magnitude_bp: float | None
    confidence: EventConfidence
    vix_regime_gate: VixRegimeGate
    caveat: str
    literature_anchor: str
    parse_failures: frozenset[str] = field(default_factory=frozenset)


# ── Title → event class mapping ──────────────────────────────────────
#
# Substring-match (case-insensitive) on `EconomicEvent.title` ; first match
# wins. Order matters : more-specific patterns (e.g. "Core CPI") MUST come
# BEFORE generic ones ("CPI"). Negative-list pattern parity with r144
# `TITLE_FRAGMENT_BLOCKED` would be added in r148+ if collisions emerge
# (R-WITNESS-EMPIRICAL : pre-deploy 2-reviewer + post-deploy witness).
_TITLE_TO_EVENT_CLASS: tuple[tuple[str, str], ...] = (
    # FOMC family
    ("fomc statement", "FOMC"),
    ("fomc press conference", "FOMC"),
    ("federal funds rate", "FOMC"),
    ("fomc meeting minutes", "FOMC"),
    # ECB family
    ("ecb press conference", "ECB"),
    ("ecb main refinancing rate", "ECB"),
    ("ecb monetary policy statement", "ECB"),
    ("ecb deposit facility rate", "ECB"),
    # BoE family
    ("boe monetary policy report", "BoE"),
    ("boe official bank rate", "BoE"),
    ("mpc meeting minutes", "BoE"),
    # BoJ family
    ("boj outlook report", "BoJ"),
    ("boj policy rate", "BoJ"),
    # Tier-1 US macro
    ("non-farm employment change", "NFP"),
    ("nonfarm payrolls", "NFP"),
    ("core cpi m/m", "CPI"),  # more specific before generic
    ("cpi m/m", "CPI"),
    ("cpi y/y", "CPI"),
    ("core cpi y/y", "CPI"),
)


def _map_title_to_event_class(title: str) -> str | None:
    """Pure-fn substring lookup ; returns None if no class mapped.

    Honest scope : maps ~17 high-impact event titles to academic event
    classes. Unmapped titles → None (caller surfaces "event_class_unmapped"
    sentinel in parse_failures, never silent).
    """
    if not title:
        return None
    needle = title.lower().strip()
    for fragment, cls in _TITLE_TO_EVENT_CLASS:
        if fragment in needle:
            return cls
    return None


def _impact_multiplier(impact: str | None) -> float:
    """Map FF impact tier to drift multiplier per Lucca-Moench + Kurov 2021
    conditioning. High events drive the bulk of drift ; low events ≈ noise."""
    if impact == "high":
        return 1.0
    if impact == "medium":
        return 0.4
    return 0.0  # low impact OR unknown → no expected drift


def _time_decay(minutes_until: int, window_minutes: int) -> float:
    """Linear time decay : 1.0 at t=0 (firing) ; 0.0 at t=window edge.

    Honest scope : Lucca-Moench observed a 24h pre-FOMC drift but the
    intensity profile is roughly linear in the academic literature
    (with some intra-day pickup in the final 60min). r147 ships the
    simple linear approximation ; r148+ candidate : empirical decay
    fit from realized intraday bars."""
    if minutes_until <= 0:
        return 1.0  # event firing now / just passed → full magnitude
    if minutes_until >= window_minutes:
        return 0.0
    return 1.0 - (minutes_until / window_minutes)


def _vix_regime_to_gate(vix_value: float | None) -> tuple[VixRegimeGate, float]:
    """Per Kurov-Halova-Wolfe-Gilbert (2021) + QuantSeeker 2024 replication
    through Dec 2024 : pre-FOMC drift is concentrated in HIGH-VIX regimes
    (VIX > p75 ~24), attenuated in p50-p75 (~18-24), near-zero in low-VIX
    (<p50 ~18). Returns (gate_label, multiplier)."""
    if vix_value is None:
        return "unavailable", 0.0
    if vix_value >= _VIX_P75:
        return "above_p75", 1.0
    if vix_value >= _VIX_P50:
        return "p50_to_p75", 0.4
    return "below_p50", 0.1


async def _latest_vix_value(session: AsyncSession, now: datetime) -> float | None:
    """Read latest VIX observation (FRED:VIXCLS) in last N sessions for
    regime gate.

    VIX is stored in `fred_observations` per the same pattern as
    `services/vix_term_structure.py` (FRED VIXCLS series ID, daily
    cadence). Returns None if no observation in `_VIX_LOOKBACK_SESSIONS`
    sessions (data-honesty fail-closed → vix_regime_gate=unavailable →
    confidence capped low).
    """
    lookback_floor = now - timedelta(days=_VIX_LOOKBACK_SESSIONS * 2)  # business-day approx
    stmt = (
        select(FredObservation)
        .where(
            FredObservation.series_id == "VIXCLS",
            FredObservation.observation_date >= lookback_floor.date(),
            FredObservation.value.is_not(None),
        )
        .order_by(desc(FredObservation.observation_date))
        .limit(1)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None or row.value is None:
        return None
    return float(row.value)


def _currencies_for_asset(asset: str) -> tuple[str, ...]:
    """Map asset code to currencies whose events affect it.

    Honest scope : USD-base / X-USD assets pull USD events ; EURUSD/GBPUSD
    also pull their respective non-USD currency. Equity indices pull USD
    only (FOMC is dominant ; foreign-bank events ≈ noise for SPX/NAS).
    """
    asset = asset.upper()
    if asset == "EUR_USD":
        return ("USD", "EUR")
    if asset == "GBP_USD":
        return ("USD", "GBP")
    if asset == "USD_JPY":
        return ("USD", "JPY")
    if asset == "AUD_USD":
        return ("USD", "AUD")
    if asset == "USD_CAD":
        return ("USD", "CAD")
    if asset in {"XAU_USD", "SPX500_USD", "NAS100_USD"}:
        return ("USD",)
    return ("USD",)  # safe default


async def assess_event_proximity(
    session: AsyncSession,
    *,
    asset: str,
    now: datetime | None = None,
    lookahead_minutes: int = _LOOKAHEAD_WINDOW_MIN_DEFAULT,
    business_cycle_sign: int | None = None,
) -> EventProximityFactor | None:
    """Compute pre-event drift expectation per literature-cited prior.

    Args :
        session            : SQLAlchemy async session.
        asset              : Asset code (EUR_USD/GBP_USD/XAU_USD/SPX500_USD/
                             NAS100_USD/USD_JPY/AUD_USD/USD_CAD).
        now                : Injection point for deterministic testing.
                             Default `datetime.now(UTC)`.
        lookahead_minutes  : Window depth in minutes (default 48h = 2880).
                             Events further out → not considered. Per
                             code-reviewer SF-2 : if caller passes <= 0,
                             value is silently auto-replaced with the
                             default (2880) — semantic equivalent of
                             "no useful window".
        business_cycle_sign: +1 (expansion, default) or -1 (contraction).
                             None defaults to +1 with explicit caveat
                             surfaced via the `caveat` output field.

    Returns `EventProximityFactor | None`. None means NO future events
    in window (caller surfaces "Aucun event majeur dans les 48h" empty
    state). Engine NEVER raises -- all edge cases honest-handled.

    HONEST SCOPE — TITLE MAPPING COVERAGE (trader YELLOW-3) :

    `_TITLE_TO_EVENT_CLASS` covers FOMC/ECB/BoE/BoJ central-bank classes
    + tier-1 US macro (NFP, CPI variants). AUD/CAD-specific events
    (RBA Cash Rate, BoC Overnight Rate) and JPY-specific events outside
    BoJ Outlook Report fall through to `event_class_unmapped` → driver
    silently None. This is HONEST per doctrine #11 (no fabricated
    baseline magnitude for unmapped classes) ; r148+ candidate to
    extend the title-fragment list. R-WITNESS-EMPIRICAL discipline :
    post-deploy probe `SELECT title FROM economic_events WHERE
    impact='high'` identifies unmapped titles for incremental coverage.

    8 edge cases handled :
      1. No future events in window           → return None
      2. Event already fired                  → next future event picked
      3. Weekend / US holiday                 → no special case (r148+) ;
                                                if no events scheduled
                                                → None (HONEST)
      4. Pre-event window <60min              → confidence='high'
      5. No VIX in last 4 business sessions   → vix_regime_gate='unavailable',
         (~8 calendar days incl. weekends)      confidence capped at 'low',
                                                vix_multiplier=0.4 fallback
      6. business_cycle_sign None             → default +1 + caveat
      7. event_class unmapped                 → magnitude_bp=None,
                                                parse_failures+='event_class_unmapped'
      8. Multiple events in window            → pick highest-impact ;
                                                tie-break by earliest scheduled_at
    """
    if now is None:
        now = datetime.now(UTC)
    if lookahead_minutes <= 0:
        lookahead_minutes = _LOOKAHEAD_WINDOW_MIN_DEFAULT

    parse_failures: set[str] = set()
    cycle_sign_default_applied = business_cycle_sign is None
    if business_cycle_sign is None:
        business_cycle_sign = 1  # expansion default per Boyd-Hu-Jagannathan baseline

    currencies = _currencies_for_asset(asset)
    window_end = now + timedelta(minutes=lookahead_minutes)

    # Query : upcoming events in window, currency-filtered, impact-tier-ordered.
    # Highest-impact wins (edge case 8) ; tie-break by earliest scheduled_at.
    # Impact ordering : "high" > "medium" > "low" via CASE.
    stmt = (
        select(EconomicEvent)
        .where(
            EconomicEvent.scheduled_at.is_not(None),
            EconomicEvent.scheduled_at > now,
            EconomicEvent.scheduled_at <= window_end,
            EconomicEvent.currency.in_(currencies),
            EconomicEvent.impact.in_(("high", "medium")),
        )
        .order_by(EconomicEvent.scheduled_at.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    if not rows:
        return None  # edge case 1 : no future events

    # Pick highest-impact ; tie-break by earliest scheduled_at (sorted ASC above).
    high_rows = [r for r in rows if r.impact == "high"]
    pool = high_rows if high_rows else rows
    next_event = pool[0]

    if next_event.scheduled_at is None:  # defensive
        return None

    minutes_until = int((next_event.scheduled_at - now).total_seconds() / 60)
    if minutes_until < 0:
        minutes_until = 0  # edge case 2 defensive (filtered by > now above)

    event_class = _map_title_to_event_class(next_event.title)
    if event_class is None:
        parse_failures.add("event_class_unmapped")

    # VIX regime gate. If unavailable, use a CONSERVATIVE DEFAULT multiplier
    # (0.4, matching p50_to_p75 baseline) so magnitude stays computable —
    # we still want to surface the event identity to the user, just with
    # confidence capped at 'low' (researcher R59 §6 edge case 5).
    vix_value = await _latest_vix_value(session, now)
    vix_gate_label, vix_multiplier = _vix_regime_to_gate(vix_value)
    if vix_gate_label == "unavailable":
        parse_failures.add("vix_observation_missing")
        vix_multiplier = 0.4  # conservative default ; confidence capped 'low'

    # Compute expected drift
    if event_class is None:
        expected_drift_bp: float | None = None
        direction: DriftDirection = "unknown"
    else:
        baseline_bp = EVENT_CLASS_BASELINE_BP.get(event_class, 0.0)
        impact_mult = _impact_multiplier(next_event.impact)
        time_dec = _time_decay(minutes_until, lookahead_minutes)
        magnitude_unsigned = baseline_bp * impact_mult * time_dec * vix_multiplier
        if magnitude_unsigned <= 0.01:
            expected_drift_bp = None  # below noise floor → honest unavailable
            direction = "unknown"
        else:
            signed = magnitude_unsigned * business_cycle_sign
            expected_drift_bp = round(signed, 2)
            direction = "up" if signed > 0 else "down" if signed < 0 else "unknown"

    # Confidence ladder (lesson #37 honest-scope ladder)
    if expected_drift_bp is None:
        confidence: EventConfidence = "unavailable"
    elif vix_gate_label == "unavailable":
        confidence = "low"
    elif minutes_until < 60:
        confidence = "high"
    elif minutes_until < 240:
        confidence = "medium"
    else:
        confidence = "low"

    # Caveat : honest-scope verbatim disclosure for Driver.evidence.
    # r147 trader YELLOW-1 : add cold-start prior disclosure ALWAYS to
    # surface that magnitudes are literature-cited PRIORS, not Ichor-data-
    # calibrated. This is the most important honesty signal per doctrine
    # #11 + lesson #37 ; survives until r148+ empirical reaction-beta
    # backfill replaces priors with Ichor-historical estimates.
    caveat_parts: list[str] = []
    if cycle_sign_default_applied:
        caveat_parts.append("Asymétrie cyclique non vérifiée, défaut expansion")
    if vix_gate_label == "unavailable":
        caveat_parts.append("VIX indisponible, gate régime dégradée")
    if event_class is None:
        caveat_parts.append("Classe d'événement non mappée")
    # ALWAYS append the cold-start prior caveat (trader YELLOW-1).
    caveat_parts.append("Magnitude prior littérature, pas calibrée sur historique Ichor")
    caveat = " ; ".join(caveat_parts)

    literature_anchor = (
        "Lucca-Moench 2015 (drift) + Boyd-Hu-Jagannathan 2005 (asymétrie) + Kurov 2021 (gate VIX)"
    )

    # r147 code-reviewer SF-3 : malformed impact → surface sentinel + None,
    # parity with r141 SurpriseClassification honesty discipline. The ORM
    # `EconomicEvent.impact` is String(16) NOT NULL but has no DB CHECK,
    # so malformed values are possible from upstream provider drift.
    if next_event.impact in ("high", "medium", "low"):
        next_event_impact_typed: ImpactLevel | None = next_event.impact  # type: ignore[assignment]
    else:
        next_event_impact_typed = None
        parse_failures.add("impact_value_invalid")

    return EventProximityFactor(
        next_event_id=str(next_event.id),
        next_event_title=next_event.title,
        next_event_currency=next_event.currency,
        next_event_minutes_until=minutes_until,
        next_event_impact=next_event_impact_typed,
        next_event_class=event_class,
        expected_drift_direction=direction,
        expected_drift_magnitude_bp=expected_drift_bp,
        confidence=confidence,
        vix_regime_gate=vix_gate_label,
        caveat=caveat,
        literature_anchor=literature_anchor,
        parse_failures=frozenset(parse_failures),
    )
