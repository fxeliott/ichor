"""CoachMacroContext — narrative synthesis layer for beginner-friendly
macro pedagogy per Eliot's r161 directive verbatim ("coach de
compréhension", "guide lumineux qui rend chaque élément limpide").

This is r161 Stride 8 foundation : a thin synthesis layer that aggregates
**existing** Ichor classifiers + calendar surfaces into ONE narrative
paragraph + structured metadata, rendered as the TOP-MOST panel on
``/briefing/[asset]`` above ``<SessionVerdictPanel>`` so the trader gets
the macro story BEFORE the per-asset verdict.

Doctrine alignment :

  * **Doctrine #4 SSOT** : reuses the canonical ``MacroTheme`` Literal
    from ``packages/agents/src/ichor_agents/agents/macro.py:24-33``
    (the 8 themes : monetary_policy / growth_data / inflation_data /
    labor_market / fiscal_policy / geopolitics / credit_conditions /
    commodity_supply). Re-defining the literal here would create the
    same drift class as the r123-era frontend regime ambient store
    vs ``regime_classifier`` documented at ``regime_classifier.py:31-37``.
  * **Doctrine #9 anti-accumulation** : the 4-cycle business-cycle
    classifier (expansion/reflation/déflation/stagflation per the
    Hewi Capital trader transcript) is **structurally distinct** from
    the existing ``regime_classifier.MasterRegime`` 7-bucket stress
    regime (crisis/broken_smile/stagflation/risk_off/goldilocks/risk_on/
    transitional). Both are kept because they answer different
    questions (cycle = "what macro phase" / regime = "what risk
    environment"). The ``stagflation`` label overlaps lexically but
    not algorithmically.
  * **ADR-017 boundary** : ``coach_paragraph`` is regex-checked
    against ``_FORBIDDEN_COACH_TOKENS_RE`` at construction time
    (mirror of ``Scenario._reject_trade_tokens`` discipline). The
    paragraph explains the macro story ; it never prescribes a
    trade action.
  * **Doctrine #11 calibrated honesty** : ``cycle="uncertain"`` +
    ``cycle_confidence_pct=0`` is a LEGITIMATE output when the FRED
    data is stale (>= ``MAX_FRESHNESS_DAYS``) OR when the growth ×
    inflation 2×2 classification is genuinely ambiguous (one axis
    "uncertain" → whole cycle "uncertain"). The coach paragraph
    surfaces the situation transparently rather than fabricating
    a confident classification.

ADR refs : ADR-106 (autonomous living-system + coach surface direction),
ADR-085 (Pass-6 7-bucket SSOT — verdict apex below this layer),
ADR-017 (no BUY/SELL boundary).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Doctrine #4 SSOT : reuse the canonical MacroTheme literal from the
# packages/agents domain ; the 8 themes are anchored to ``MacroAgent``'s
# Pydantic output schema (``packages/agents/.../macro.py:24-33``).
# Importing avoids the drift class identified by the r161 researcher
# audit (regime_classifier vs frontend ambient store r123 precedent).
try:  # pragma: no cover - import guard
    from ichor_agents.agents.macro import MacroTheme  # type: ignore[import-not-found]
except ImportError:
    # Standalone-test fallback : ichor_agents not installed in some
    # ichor_brain dev environments. The Literal value-set is identical.
    MacroTheme = Literal[  # type: ignore[misc, assignment]
        "monetary_policy",
        "growth_data",
        "inflation_data",
        "labor_market",
        "fiscal_policy",
        "geopolitics",
        "credit_conditions",
        "commodity_supply",
    ]


# r161 Stride 8 — ADR-017 boundary regex applied to ``coach_paragraph``.
# Mirror of ``packages/ichor_brain/scenarios.py:50-53``
# ``_FORBIDDEN_MECHANISM_TOKENS_RE`` ; the regex source-of-truth lives in
# scenarios.py and is duplicated here only to avoid a circular-import
# risk once frontend consumers wire the coach paragraph alongside
# ``SessionVerdict.coach_explanation`` (same coach-surface contract).
# Both regexes MUST stay byte-identical — CI guard via
# ``test_invariants_ichor.py`` extension (r161 carry-forward).
_FORBIDDEN_COACH_TOKENS_RE = re.compile(
    r"\b(BUY|SELL|TP|SL|long entry|short entry|stop loss|take profit)\b",
    re.IGNORECASE,
)


# The 4 business-cycle phases per the Hewi Capital trader-coach transcript
# verbatim (vidéo 1, 4-cycle framework). Growth × Inflation 2×2 matrix :
#
#               | inflation rising      | inflation falling
#   -----------|---------------------|--------------------
#   strong gr. | REFLATION           | EXPANSION (Goldilocks)
#   weak gr.   | STAGFLATION         | DEFLATION
#
# ``uncertain`` is the doctrine #11 calibrated-honesty escape valve
# when FRED data is stale OR one axis is genuinely ambiguous.
BusinessCycle = Literal["expansion", "reflation", "deflation", "stagflation", "uncertain"]


# Coarse growth + inflation axis labels — public so the frontend can
# render them as standalone chips (e.g., "Croissance: forte ·
# Inflation: en hausse"). Doctrine #4 SSOT for the 2×2 matrix.
GrowthSignal = Literal["strong", "weak", "uncertain"]
InflationSignal = Literal["rising", "falling", "uncertain"]


# Surprise priority tier for the calendar — drives UI emphasis. The
# rule-based dominant-surprise classifier (in ``coach_macro_context_
# builder.py``) maps a calendar event's distance-to-now + impact tier
# + sensitivity-to-current-cycle into this 3-tier label.
SurprisePriority = Literal["high", "medium", "low"]


# r168 G3 — Risk-on / risk-off / transitional ambient regime label per
# Eliot's methodology transcript §X verbatim : « régime risk on ou risk
# off et on a pas mal de choses à voir pour anticiper notre risque ou
# non » (Fathom 2026-05-25). One of the four "piliers" Eliot cites
# explicitly for his pre-trade lecture (alongside DXY corrélation,
# fundamental, géopolitique).
#
# Derivation : self-calibrating z-score classifier in
# ``coach_macro_context_builder._classify_risk_regime`` over VIXCLS
# (CBOE vol) + BAMLH0A0HYM2 (ICE BofA US HY OAS in %) FRED series with
# trailing 252d rolling window. The classifier returns ``risk_on`` only
# when BOTH stress indicators are significantly below their own 1y trend
# (z ≤ -0.7σ) ; ``risk_off`` when EITHER is significantly above (z ≥
# +0.7σ) ; ``transitional`` otherwise.
#
# **Pattern #15 R59 satisfied by design** : the ±0.7σ threshold is a
# statistical convention (sigma boundary, not peer-reviewed citation
# claim). Z-score is self-calibrating relative to the series's own 1y
# history — no absolute threshold pinning ; no literature anchor needed
# (cf. r147 Bauer DP21003 paper-hallucination catch + r150 PIVOT 1 VIX
# 5y rolling REJECTED for same reason).
#
# **r168 R59-verified peer-reviewed backbone** (researcher dispatch 2026-05-27,
# 14 WebSearches + DOI primary-source verification — see r168 session_log) :
#   - HY OAS z-score foundation : Gilchrist-Zakrajšek 2012 *AER* 102(4)
#     1692-1720 DOI 10.1257/aer.102.4.1692 ("Excess Bond Premium") +
#     López-Salido-Stein-Zakrajšek 2017 *QJE* 132(3) DOI 10.1093/qje/qjx014
#     (credit sentiment mean-reversion supports continuous z-score, NOT
#     absolute percentile thresholds — credit spreads non-stationary).
#   - VIX caveat : Whaley 2000 *JPM* 26(3) 12-17 proposed the "fear gauge"
#     framing at threshold 30 (NOT 20) ; Whaley himself walked it back in
#     2009. The popular VIX>20 = stress claim is **practitioner**, NOT
#     peer-reviewed. Memory's pre-r168 proposal "VIX > 22 → risk_off"
#     would have been a citation hallucination — REJECTED.
#   - Variance Risk Premium decomposition : Bekaert-Hoerova-Lo Duca 2013
#     *JME* 60(7) 771-788 DOI 10.1016/j.jmoneco.2013.06.003 — decomposes
#     VIX² into risk-aversion (VRP) + uncertainty (realized variance).
#     r169+ candidate : enrich classifier with VRP instead of raw VIX.
#   - Full RORO composite : Chari-Dilts Stedman-Lundblad 2025 *JIMF*
#     RORO Index (KC Fed RWP24-12 / CEPR DP20932 / NBER w31907) — PCA
#     first principal component of credit + equity-vol + funding + FX.
#     The canonical academic RORO. r170+ candidate.
#   - NFCI z-score methodology : Brave-Butters 2011 *Econ. Perspectives*
#     + Butters 2012 *IJCB* 8(2) 191-239 — standardized mean=0 SD=1
#     since 1973 ; empirical crisis threshold –0.39. r169+ candidate to
#     add NFCI as 3rd backbone indicator.
#
# Doctrine #4 SSOT : reuses ``_fetch_fred_window`` + ``_z_score_latest``
# already powering ``_classify_dominant_theme`` — no new query path.
# Doctrine #9 anti-accumulation : appends to the existing CoachMacroContext
# narrative, no new ADR ; ADR-106 §Impl(r168) APPEND-only.
# Doctrine #11 calibrated honesty : ``transitional`` + empty evidence
# is a LEGITIMATE output when neither stress indicator crosses ±0.7σ
# (no signal → honest absence, not forced classification).
RiskRegime = Literal["risk_on", "risk_off", "transitional"]


# Maximum allowed staleness (days) for FRED data feeding the cycle
# classifier. Past this threshold, the builder forces ``cycle="uncertain"``
# regardless of raw computation — doctrine #11 calibrated honesty.
#
# r172c calibration fix (2026-05-28, R2 audit B3 follow-up — Pattern #15
# R59 catch on R2 audit interpretation : R2 reported "FRED stale 56d" as
# a problem, but verified empirical (SSH `psql` 2026-05-28) confirms
# this is the NORMAL publication-lag of monthly BLS series, NOT a
# collector silent-skip). The previous threshold of 45 days was TOO
# TIGHT for the inherent observation-date-based lag :
#
#   - Monthly series `observation_date` = first day of measurement month
#     (e.g. CPI for April → observation_date=2026-04-01)
#   - BLS publication delay = 14-21 days AFTER end-of-month
#   - Worst-case lag from observation_date = 30d (month length) + 21d
#     (publication delay) ≈ 51-58 days for monthly series
#
# Net effect of the 45-day threshold : `cycle="uncertain"` was forced
# ~50% of every month (the last 2 weeks before next-month release),
# causing `<CoachMacroContextPanel>` to permanently render
# `cycle=uncertain / dominant_theme=null / risk_regime_evidence=[]`
# right when the trader needs it most (mid-month NY position windows).
#
# Empirical SSH 2026-05-28 : latest CPIAUCSL = 2026-04-01 = 57 days ago.
# Threshold 60 days covers this normal lag while still catching truly
# stale data (e.g. GDPC1 currently 147 days = quarterly normal but
# would correctly trigger uncertain if it stretched to >60d months,
# meeting doctrine #11 honest-degradation threshold). Per-series
# thresholds (daily=7d, monthly=60d, quarterly=120d) deferred r-future
# if empirically needed ; single-value 60d is the trader-discipline
# minimal-fix Pareto (doctrine #2 strict scope).
MAX_FRESHNESS_DAYS: int = 60


class CalendarSurprise(BaseModel):
    """One next-N upcoming economic event item surfaced for the coach
    narrative. Sourced by reusing ``services/event_anticipation_view.py``
    OR ``services/couche2_context.build_economic_calendar_context()``
    via the builder (doctrine #9 anti-accumulation : no 3rd query path
    over ``EconomicEvent``)."""

    model_config = {"frozen": True, "extra": "forbid"}

    event_label: str = Field(min_length=2, max_length=120)
    """Plain-French human-readable event label, e.g.
    "Core PCE Price Index (avril)" or "FOMC Statement".
    Sourced from ``EconomicEvent.title`` upstream ; trimmed/translated
    by the builder for the coach surface."""

    scheduled_at_paris: datetime
    """Paris-local datetime when the event is scheduled. UI surface
    renders relative ("dans 4h 30min") + absolute ("aujourd'hui 14h30 Paris")."""

    priority: SurprisePriority
    """How much this event matters relative to the current ``cycle`` +
    ``dominant_theme``. ``high`` = event class is directly tied to the
    current cycle's defining variable (e.g., a CPI release during a
    stagflation cycle = high). ``medium`` = HIGH-impact event but not
    cycle-defining. ``low`` = medium-impact event included for
    completeness."""

    why_it_matters: str = Field(min_length=10, max_length=200)
    """Plain-French one-sentence explanation of WHY this event matters
    for the current macro narrative. ADR-017 regex-checked (the
    description explains the event's macro relevance, never prescribes
    a trade action)."""

    @field_validator("why_it_matters")
    @classmethod
    def _reject_trade_tokens_in_why(cls, v: str) -> str:
        """ADR-017 boundary mirror. The ``why_it_matters`` explains the
        macro relevance ; it never instructs a trade."""
        if _FORBIDDEN_COACH_TOKENS_RE.search(v):
            raise ValueError(
                f"ADR-017 boundary violated : CalendarSurprise.why_it_matters "
                f"contains a forbidden trade-signal token. Got: {v!r}. The "
                "explanation describes the event's macro relevance ; it "
                "never prescribes BUY/SELL/TP/SL or entry/exit."
            )
        return v


class CoachMacroContext(BaseModel):
    """Canonical Ichor coach macro narrative read per ADR-106 §"coach
    explicateur" + Eliot r161 directive verbatim.

    Renders at the TOP of ``/briefing/[asset]`` ABOVE ``<SessionVerdictPanel>``
    so the trader gets the macro story BEFORE the per-asset verdict.
    Mirrors the Hewi Capital transcript framework :

      1. **Cycle** : where in the business cycle are we ? (4-phase
         growth × inflation 2×2 matrix)
      2. **Dominant theme** : among the 8 macro drivers, which one
         dominates the cross-asset narrative right now ? (max |z-score|
         per theme-mapped FRED series)
      3. **Upcoming surprises** : what are the next 3 events most likely
         to shift the verdict ? (event-anticipation view + cycle-aware
         priority)
      4. **Coach paragraph** : 100..600 chars FR beginner-friendly
         synthesis tying the 3 above into ONE narrative

    Doctrine alignment :
      - ADR-017 : ``coach_paragraph`` + ``CalendarSurprise.why_it_matters``
        BOTH regex-checked at construction time
      - Doctrine #4 SSOT : ``MacroTheme`` imported from agents/macro.py
      - Doctrine #11 calibrated honesty : ``cycle="uncertain"`` +
        ``cycle_confidence_pct=0`` returned when FRED data is stale or
        2×2 ambiguous
    """

    model_config = {"frozen": True, "extra": "forbid"}

    cycle: BusinessCycle
    """The 4-phase business-cycle classification (expansion / reflation /
    deflation / stagflation / uncertain). ``uncertain`` is a legitimate
    doctrine #11 output."""

    cycle_confidence_pct: float = Field(ge=0.0, le=95.0)
    """0..95% confidence in the cycle classification. Capped at 95 per
    ADR-022 cap-95 invariant. 0 when ``cycle="uncertain"``."""

    growth_signal: GrowthSignal
    """Coarse growth axis label (strong / weak / uncertain). Surfaced
    standalone for the frontend chip ("Croissance: forte")."""

    inflation_signal: InflationSignal
    """Coarse inflation axis label (rising / falling / uncertain).
    Surfaced standalone for the frontend chip ("Inflation: en hausse")."""

    dominant_theme: MacroTheme | None
    """The single macro driver dominating the narrative right now,
    classified by rule-based max |z-score| over the 18 FRED series
    mapped to the 8 ``MacroTheme`` labels. ``None`` when all series
    are stale or |z| < 1.0 (no theme stands out)."""

    dominant_theme_strength_z: float | None = Field(default=None, ge=-10.0, le=10.0)
    """The z-score magnitude of the representative series that earned
    the ``dominant_theme`` classification. Surfaced to the frontend as
    an intensity indicator ("|z|=2.3 → exceptionnellement marqué")."""

    risk_regime: RiskRegime = "transitional"
    """r168 G3 — Eliot's §X risk-on/risk-off pillar. Self-calibrating z-score
    classifier over VIXCLS + BAMLH0A0HYM2. Default ``transitional`` preserves
    backward-compat with pre-r168 emissions (any older row deserialised lands
    as ``transitional`` = honest no-signal). The frontend
    ``<CoachMacroContextPanel>`` r168 renders this as a chip ABOVE the
    growth/inflation row per ADR-106 D4 surface hierarchy."""

    risk_regime_evidence: list[str] = Field(default_factory=list, max_length=3)
    """r168 G3 — Up to 3 plain-text evidence strings (FRED series name +
    z-score) that drove the ``risk_regime`` classification. Empty when
    ``risk_regime == "transitional"`` and no signal crossed ±0.7σ threshold
    (doctrine #11 honest absence). ADR-017 boundary preserved by construction
    (every string is mechanical "VIXCLS z=+1.23" — zero forbidden tokens)."""

    top_next_surprises: list[CalendarSurprise] = Field(default_factory=list, max_length=3)
    """Up to 3 next-N upcoming economic events ordered by priority +
    proximity. Empty when no event in the 7-day forward window matches
    high/medium-impact criteria."""

    coach_paragraph: str = Field(min_length=100, max_length=600)
    """Plain-French beginner-friendly synthesis paragraph tying cycle +
    dominant theme + upcoming surprises into ONE narrative. Surfaced
    as the panel's prose body. ADR-017 regex-checked at construction
    time."""

    data_freshness_days: int = Field(ge=0, le=365)
    """Number of days since the most-recent FRED observation used by the
    classifier. Past ``MAX_FRESHNESS_DAYS = 60``, the builder forces
    ``cycle="uncertain"`` regardless of raw computation. Surfaced to
    the frontend so the user knows how stale the underlying data is."""

    generated_at_utc: datetime
    """Wall-clock UTC of this read's generation. Frontend renders
    "synthétisé il y a N min" relative label."""

    @field_validator("coach_paragraph")
    @classmethod
    def _reject_trade_tokens_in_coach(cls, v: str) -> str:
        """ADR-017 boundary : the coach paragraph explains the macro
        narrative ; it never prescribes a trade action. Mirror of
        ``Scenario._reject_trade_tokens`` + ``SessionVerdict._reject_
        trade_tokens_in_coach`` discipline."""
        if _FORBIDDEN_COACH_TOKENS_RE.search(v):
            raise ValueError(
                "ADR-017 boundary violated : CoachMacroContext.coach_paragraph "
                f"contains a forbidden trade-signal token. Got: {v!r}. The "
                "paragraph explains the macro narrative (cycle + dominant "
                "theme + upcoming surprises) ; it never prescribes "
                "BUY/SELL/TP/SL or entry/exit. The trader applies his/her "
                "own technical execution on TradingView."
            )
        return v
