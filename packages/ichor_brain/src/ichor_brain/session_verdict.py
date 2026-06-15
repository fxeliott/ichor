"""SessionVerdict — the canonical Ichor output contract per Eliot's r161 directive.

The system delivers ONE verdict per (asset, NY session day) that aggregates the
7-bucket Pass-6 ``ScenarioDecomposition``, the Engine 8 event-anticipation prior,
the empirical reaction-beta calibration (when r161+ Dukascopy backfill ships),
and any LIVE triggers / invalidations that have fired since the briefing was
emitted. The verdict's shape was crystallised by Eliot in the r161 directive :

    « hausse sur la session à 85 %, de façon structurée » ou « en momentum »
    — avec un pourcentage de conviction clair et la nature précise du
    mouvement attendu.

The verdict is NOT a trade signal (ADR-017 boundary). It is a probability-
calibrated directional bias + nature classification + invalidation state
snapshot that the trader consults BEFORE applying his/her own technical
read on TradingView. The trader's window is 13h-20h Paris ; the verdict is
calibrated for that window and stamps the verdict's window boundaries
explicitly so it cannot be misapplied to other timeframes.

Architectural alignment :

  * The verdict is DERIVED from ``ScenarioDecomposition`` (Pass-6 emission,
    ADR-085 ratified). It does NOT bypass the 7-bucket discipline — instead
    it aggregates the 3 bullish buckets (mild_bull + strong_bull + melt_up)
    vs the 3 bearish buckets (mild_bear + strong_bear + crash_flush) +
    weighted magnitude_pips to compute a single ``direction`` +
    ``conviction_pct``. The ``nature`` field is derived from the relative
    weight of tail-buckets (melt_up + crash_flush) vs mid-buckets
    (mild_bull + mild_bear) : tail-heavy = momentum, mid-heavy = structured.
  * The verdict is LIVE — ``invalidation_state`` carries the current
    invalidation status of each underlying scenario (per r161 Strand A
    ``Scenario.invalidations`` field + Strand D monitor service) and
    ``live_triggers`` surfaces the events that have fired since emission.
    HONEST STATE (2026-06-15 adversarial audit) : the *in-place* conviction
    reaction specified in ADR-106 §D3.1 — on a ``hard`` invalidation, zero
    the offending bucket's ``p``, ``cap_and_normalize``, re-derive — is NOT
    yet wired into ``build_session_verdict``. The invalidation status is
    DISPLAYED, but ``conviction_pct`` is not auto-reduced in place. Today the
    only event-driven conviction change is a full Pass-6 card regen via
    ``services/streaming_refresh.py`` (flag-gated, fail-closed). Wiring the
    in-place reaction is a scoped next increment : it needs the ADR-106
    §D3.1 re-distribution semantics disambiguated (``cap_and_normalize``
    preserves the sum, so "redistributes mass" is ambiguous vs a
    renormalise-to-1) AND a live witness once the monitor is armed.
  * ADR-017 boundary preserved : ``coach_explanation`` is regex-checked
    for trade-instruction tokens (BUY/SELL/TP/SL) ; ``live_triggers[*]
    .description`` likewise. The verdict has no entry/exit price, no
    stop, no target — only direction + conviction + nature + the
    pedagogical explanation a beginner needs to understand WHY.

doctrines :
  - #2 strict scope : the verdict is a thin aggregation layer over Pass-6.
    No new pass, no new LLM call, no new schema migration.
  - #4 SSOT : the verdict references ``Scenario.label`` enum + the
    ``BUCKET_LABELS`` tuple verbatim. No drift possible.
  - #11 calibrated honesty : ``conviction_pct`` caps at CAP_95 = 95 (ADR-022).
    The verdict can return ``direction="neutral"`` + ``nature="uncertain"``
    + ``conviction_pct=0`` if the scenario decomposition is too flat to
    yield a directional read — never fabricate a verdict to fill the void.

ADR refs :
  - ADR-106 (this verdict contract + autonomous 24/7 system architecture)
  - ADR-085 (Pass-6 scenario_decompose, source of the 7 buckets)
  - ADR-017 (no BUY/SELL boundary)
  - ADR-022 (cap-95 conviction invariant)
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .scenarios import BUCKET_LABELS, CAP_95, BucketLabel

# r161 Strand H — ADR-017 boundary regex applied to ``coach_explanation`` +
# ``live_triggers[*].description``. Same forbidden-token set as the canonical
# ``_FORBIDDEN_MECHANISM_TOKENS_RE`` in ``scenarios.py:50-53`` (single source
# of truth on regex shape ; the constant is re-defined here only because
# importing across module boundaries would create a circular-import risk
# once the verdict consumer side wires ``ScenarioDecomposition`` into a
# verdict aggregator). Both regexes MUST stay byte-identical — if one is
# updated, the other follows. CI-guarded via ``test_invariants_ichor.py``
# extension (r161 follow-up).
_FORBIDDEN_VERDICT_TOKENS_RE = re.compile(
    r"\b(BUY|SELL|TP|SL|long entry|short entry|stop loss|take profit)\b",
    re.IGNORECASE,
)


# The 5 priority assets the verdict supports. Mirror of
# ``packages/agents/src/ichor_agents/agents/news_nlp.py:48-57`` +
# ``apps/web2/components/briefing/assets.ts:21-29`` (USD_CAD intentionally
# out-of-scope frontend ; verdict surface follows the frontend universe).
PriorityAsset = Literal[
    "EUR_USD",
    "GBP_USD",
    "XAU_USD",
    "SPX500_USD",
    "NAS100_USD",
]


# The verdict's directional read. ``neutral`` is a legitimate output when
# the scenario decomposition is too flat (no bucket dominance) — doctrine
# #11 calibrated honesty refuses to fabricate a direction.
VerdictDirection = Literal["up", "down", "neutral"]


# The nature of the expected move. Derived deterministically from the tail-
# vs-mid weight of the underlying Pass-6 scenario probabilities (see
# verdict-builder docstring in the future ``services/session_verdict_builder.py``
# r161 Strand I).
VerdictNature = Literal["structured", "momentum", "range_bound", "uncertain"]


# r167 G1 — TradeabilityFlag : closes Eliot's #1 CRITICAL gap from his trading
# methodology transcript (Fathom 2026-05-25 §VIII). When the day is structurally
# unsuitable for taking a NY-session position (bank holiday / pending high-impact
# event freeze / abnormally low volatility / market range absolu / no strong
# setup), Ichor surfaces a HONEST DISCLOSURE rather than emitting a conviction
# read that the trader would have to OVERRIDE.
#
# Eliot verbatim from the methodology transcript : « on était en bank holiday
# aujourd'hui, mais on peut bien le voir ici sur la session de New York... toute
# une session orange. Donc on n'a vraiment pas du tout de volatilité, donc ça
# vraiment pas du tout intéressant à trader pour aujourd'hui ».
#
# The 6 values map to 6 distinct decision contexts :
#   - ``tradeable``       : all gates pass — verdict reads as normal, trader
#                           proceeds with technical entry analysis.
#   - ``no_setup``        : verdict conviction_pct < 30 — read is too weak ;
#                           trader passes without holiday/event-freeze cause.
#   - ``holiday``         : US market holiday (cf. ``market_session.us_market_
#                           holidays``) — NY session sees reduced volume even
#                           on FX/XAU, Eliot's discipline = no trade.
#   - ``event_freeze``    : high-impact economic event scheduled within next
#                           2h — Eliot's discipline = wait the event then trade
#                           reaction, never trade across the event.
#   - ``low_volatility``  : current hour-UTC median_bp from rolling 30-day
#                           hourly_volatility window is below threshold (5 bp
#                           default) — market is structurally inert, momentum
#                           unlikely.
#   - ``range``           : last N daily candles all small body (range-bound
#                           inertia). WIRED since r168b — the evaluator's
#                           Gate 4 calls ``daily_candle_classifier.is_range_bound``
#                           (uncertainty candle + Garman-Klass variance
#                           compression). No longer the r167 "always False" gap.
#
# Derivation logic lives in ``services/tradeability_evaluator.py`` (r167 G1).
# Frontend surfaces ``<SessionVerdictPanel>`` disclosure banner via r167 G8
# when ``tradeability != "tradeable"``.
TradeabilityFlag = Literal[
    "tradeable",
    "no_setup",
    "holiday",
    "event_freeze",
    "low_volatility",
    "range",
]


# Live-trigger type taxonomy. Each value maps to a specific upstream feed
# the system polls (Strands C-F of r161 Scenario Invalidation Engine).
LiveTriggerType = Literal[
    "economic_release",  # ForexFactory / Yelza event fired
    "central_bank_speech",  # Fed / ECB / BoE / BoJ speaker on-the-record
    "news_headline",  # GDELT / RSS / Mastodon-Truth-Social keyword match
    "polymarket_shift",  # Polymarket probability shift > threshold
    "cross_asset_breakout",  # DXY / VIX / 10Y crossed a polled level
    "scenario_invalidation",  # one Pass-6 bucket fired its invalidation
    "scenario_confirmation",  # one Pass-6 bucket had its mechanism confirmed
]


# Impact direction of a live trigger on the current verdict.
LiveTriggerImpact = Literal[
    "confirms_verdict",  # trigger reinforces direction + raises conviction
    "tests_verdict",  # trigger neutral but worth watching
    "invalidates_verdict",  # trigger contradicts direction, conviction down
]


class LiveTrigger(BaseModel):
    """One real-time event that has fired since the briefing was emitted
    and that materially affects the verdict. Sourced by the monitoring
    services landing in r161 Strands D-F (scenario_invalidation_monitor,
    news_relevance_router, polymarket_shift_detector).

    ADR-017 boundary : ``description`` explains WHAT happened in the
    world, never WHAT to do about it.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    trigger_type: LiveTriggerType
    description: str = Field(min_length=10, max_length=200)
    """Plain-French (or plain-English) one-sentence explanation of WHAT
    fired. Critic-verifiable. ADR-017 boundary applies."""

    fired_at_utc: datetime
    """Wall-clock when the trigger materialised. UTC for unambiguous
    cross-timezone storage ; UI surface renders in Paris time."""

    impact: LiveTriggerImpact
    """Which way this trigger pushes the verdict's conviction."""

    source: str = Field(min_length=2, max_length=64)
    """Provenance tag : ``"forexfactory"``, ``"polymarket:fed_cuts_2026"``,
    ``"gdelt:keyword=hormuz"``, ``"engine8:event_class=CPI"``. Used by
    Critic for source-stamping discipline + downstream Brier calibration
    (Phase D auto-learning loops)."""

    @field_validator("description")
    @classmethod
    def _reject_trade_tokens_in_trigger_description(cls, v: str) -> str:
        """ADR-017 boundary mirror. The trigger describes the world,
        never prescribes a trade action."""
        if _FORBIDDEN_VERDICT_TOKENS_RE.search(v):
            raise ValueError(
                "ADR-017 boundary violated : LiveTrigger.description contains "
                f"a forbidden trade-signal token. Got: {v!r}. The description "
                "explains the event that fired ; it never prescribes "
                "BUY/SELL/TP/SL or entry/exit."
            )
        return v


class ScenarioInvalidationState(BaseModel):
    """Aggregated invalidation status of the 7 Pass-6 buckets at verdict
    emission/refresh time. Sourced by the
    ``services/scenario_invalidation_monitor.py`` (r161 Strand D) that
    polls each scenario's ``invalidations: list[InvalidationCondition]``
    field against current data.

    The verdict consumer (frontend chip + endpoint) uses this to surface
    "scenario X invalidated → conviction adjusted from 78% → 65%" when
    the user inspects the verdict's provenance.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    scenarios_invalidated_hard: list[BucketLabel] = Field(default_factory=list)
    """Buckets whose hard invalidations have fired. Their probability is
    auto-redistributed across surviving buckets per
    ``cap_and_normalize`` semantics."""

    scenarios_invalidated_soft: list[BucketLabel] = Field(default_factory=list)
    """Buckets whose soft invalidations have fired. Conviction is
    reduced but probability is not auto-redistributed."""

    scenarios_with_notes: list[BucketLabel] = Field(default_factory=list)
    """Buckets whose note-severity invalidations have fired. Surfaced
    to the user as 'context changed' without modifying probability."""

    last_check_utc: datetime
    """Wall-clock of the last invalidation-monitor poll."""

    @field_validator(
        "scenarios_invalidated_hard",
        "scenarios_invalidated_soft",
        "scenarios_with_notes",
    )
    @classmethod
    def _validate_bucket_labels_canonical(cls, v: list[BucketLabel]) -> list[BucketLabel]:
        """Doctrine #4 SSOT : every label in these lists MUST be in the
        canonical ``BUCKET_LABELS`` tuple. Defence-in-depth (the Literal
        type already enforces this at typing level, but a runtime check
        guards against future stringly-typed deserialisation drift)."""
        canonical = set(BUCKET_LABELS)
        for lbl in v:
            if lbl not in canonical:
                raise ValueError(
                    f"bucket label {lbl!r} is not in canonical BUCKET_LABELS "
                    f"set {canonical}. Doctrine #4 SSOT violation."
                )
        return v


class SessionVerdict(BaseModel):
    """The canonical Ichor verdict per Eliot's r161 directive verbatim :
    « hausse sur la session à 85 %, de façon structurée » ou « en momentum ».

    Emission cadence :
      - Pre-NY (~13h00 Paris) : first verdict for the NY session
      - Refresh on LIVE trigger fire : conviction + invalidation state
        update, ``last_updated_utc`` bumps
      - Refresh on Pass-6 re-emission : new ``scenario_decomposition_id``,
        verdict re-derived
      - Stale after ``expires_at_utc`` (typically 20h00 Paris, the trader
        closes all positions)

    Consumer surfaces :
      - Frontend ``<SessionVerdictPanel>`` (r161 Strand G) renders the
        verdict prominently on /briefing/[asset] above the
        ``<EventAnticipationPanel>``
      - Endpoint ``GET /v1/verdict/session-ny/{asset}`` (r161 Strand G)
        returns the latest verdict + 60s polling for refresh until
        WebSocket/SSE lands (r162+ Stride 7)

    Doctrine alignment :
      - ADR-017 : ``direction`` is geometric/probabilistic (up/down/neutral),
        never imperative ; ``coach_explanation`` regex-checked
      - ADR-022 : ``conviction_pct`` capped at CAP_95 = 95
      - ADR-085 : derived from 7-bucket ``ScenarioDecomposition``
      - Doctrine #11 calibrated honesty : ``direction="neutral"`` +
        ``conviction_pct=0`` is a LEGITIMATE output when the scenario
        decomposition is too flat to yield a read
    """

    model_config = {"frozen": True, "extra": "forbid"}

    asset: PriorityAsset

    session_window: Literal["ny_13h_to_20h_paris"] = "ny_13h_to_20h_paris"
    """Eliot's canonical execution window (owner TRANCHE 2026-06-13, confirmed
    2026-06-15) : fenêtre d'exécution 13h-16h (pic de qualité 14h-16h), coupe
    tout à 20h Paris. The verdict is calibrated for this window explicitly so
    consumers cannot misapply it to other timeframes (e.g., the London-session
    pulse uses a different verdict shape)."""

    direction: VerdictDirection
    """Direction the system reads as more probable for the session.
    ``neutral`` is a legitimate output (doctrine #11)."""

    conviction_pct: float = Field(ge=0.0, le=CAP_95 * 100.0)
    """0..95 percent. Capped at 95% per ADR-022 (no individual verdict
    can express certainty). 0 = no read, 50 = coin-flip (typically
    returned as ``direction="neutral"`` instead), 85 = strong read.
    The cap is enforced as ``CAP_95 * 100`` so it tracks the cap-95
    invariant if it ever changes in ``scenarios.py``."""

    nature: VerdictNature
    """Nature of the expected move :
      - ``structured`` : range-bound or measured directional move with
        identifiable rhythm
      - ``momentum`` : impulsive directional move, likely tail-driven
        (post-event, post-trigger, post-news-headline)
      - ``range_bound`` : low volatility, no directional bias, fade
        extremes
      - ``uncertain`` : the scenario decomposition is too flat or the
        invalidation state is mixed ; doctrine #11 calibrated honesty"""

    derived_from_scenarios: bool
    """True if the verdict was aggregated from a Pass-6 emission. False
    if the verdict is a fallback (e.g., Pass-6 gated off or the
    decomposition was rejected by validators). When False, the verdict
    is downgraded — conviction_pct capped at 50 + nature forced to
    ``uncertain``."""

    scenario_decomposition_id: str | None = Field(default=None, max_length=64)
    """UUID stringified pointer to the source ``scenario_decomposition``
    row in ``session_card_audit.scenarios``. Allows the consumer to
    drill from the verdict down to the 7 buckets that produced it."""

    invalidation_state: ScenarioInvalidationState | None = None
    """Current invalidation status of the 7 underlying scenarios.
    ``None`` if the invalidation monitor (r161 Strand D) has not yet
    run since verdict emission ; populated on first monitor cycle."""

    live_triggers: list[LiveTrigger] = Field(default_factory=list, max_length=10)
    """Up to 10 live triggers that have fired since verdict emission.
    Ordered most-recent-first. Cap at 10 prevents UI saturation ;
    overflow drops the oldest. Doctrine #2 strict scope ; the trader
    reads at most 3-5 in practice per the transcript Hewi Capital
    framework."""

    coach_explanation: str = Field(min_length=80, max_length=800)
    """Plain-French beginner-friendly explanation of WHY this verdict.
    Should answer : (a) what's the dominant macro narrative driving the
    session, (b) which buckets carry the weight, (c) what to watch for
    invalidation, (d) why this nature (structured vs momentum). ADR-017
    regex-checked. Pedagogical without an 'explanation section' (the
    explanation is the field itself, mirroring Eliot's directive
    "L'explication doit être intégrée naturellement dans la façon dont
    les données sont présentées — pas dans un encart séparé")."""

    ne_pas_actionner_avant_paris: datetime
    """Paris-local datetime BEFORE which the trader should not act on
    this verdict. Typically 13h00 Paris (Eliot's execution-window start ;
    quality peak 14h-16h)."""

    couper_au_plus_tard_paris: datetime
    """Paris-local datetime BY WHICH the trader closes all positions.
    Typically 20h00 Paris (Eliot's window close)."""

    last_updated_utc: datetime
    """Wall-clock UTC of the last verdict refresh (trigger fire OR
    Pass-6 re-emission). Frontend renders 'updated 2 min ago' from
    this field."""

    expires_at_utc: datetime
    """Wall-clock UTC after which the verdict is STALE and must not be
    consumed. Frontend banner switches to "verdict expiré, attente
    nouvelle session" past this. Typically set to
    ``couper_au_plus_tard_paris`` + 15min buffer."""

    tradeability: TradeabilityFlag = "tradeable"
    """r167 G1 — closes Eliot's #1 CRITICAL gap from his methodology
    transcript (Fathom 2026-05-25 §VIII : « pas du tout intéressant à
    trader pour aujourd'hui »).

    6-state Literal indicating whether the day is structurally suitable
    for taking a NY-session position. Default ``"tradeable"`` preserves
    backward-compat with pre-r167 emissions (any older row deserialised
    with this Pydantic class lands as ``"tradeable"`` — same semantic
    as "no honest reason to abstain").

    Derived deterministically by ``services/tradeability_evaluator.py``
    composite rule (priority-ordered : holiday > event_freeze >
    low_volatility > range > no_setup > tradeable). The evaluator is
    called by ``session_verdict_builder.py`` for BOTH the populated path
    and the fallback path so a dormant verdict can still honestly
    surface ``"holiday"`` or ``"event_freeze"`` to the trader.

    Frontend ``<SessionVerdictPanel>`` r167 G8 renders a disclosure
    banner (demoted chrome + honest FR copy) when this field is anything
    other than ``"tradeable"`` ; the trader sees clearly WHY the verdict
    should not be acted on today, even though the verdict still emits."""

    @field_validator("coach_explanation")
    @classmethod
    def _reject_trade_tokens_in_coach(cls, v: str) -> str:
        """ADR-017 boundary mirror. The coach explanation educates the
        trader about the macro/structural reason for the verdict ; it
        never prescribes a trade action. Mirror of
        ``Scenario._reject_trade_tokens`` in ``scenarios.py:115-129``."""
        if _FORBIDDEN_VERDICT_TOKENS_RE.search(v):
            raise ValueError(
                "ADR-017 boundary violated : SessionVerdict.coach_explanation "
                f"contains a forbidden trade-signal token. Got: {v!r}. The "
                "coach_explanation explains WHY the verdict reads as it does ; "
                "it never prescribes BUY/SELL/TP/SL or entry/exit. The trader "
                "applies his/her own technical entry/exit on TradingView."
            )
        return v
