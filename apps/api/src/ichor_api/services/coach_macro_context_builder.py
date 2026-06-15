"""CoachMacroContextBuilder — r161 Stride 8 narrative-synthesis layer.

Aggregates the 4-cycle business-cycle classification + 8-driver dominant
theme + 3-next-surprises calendar + FR coach paragraph into the
``CoachMacroContext`` rendered at the TOP of ``/briefing/[asset]`` above
``<SessionVerdictPanel>``. Materialises Eliot's r161 directive verbatim
"coach de compréhension" + "guide lumineux qui rend chaque élément
limpide".

**Algorithm (per Hewi Capital trader-coach transcript framework)** :

  1. **4-cycle business-cycle classification (growth × inflation 2×2)** :
     - Growth axis : ``PAYEMS`` m/m delta sign over last 3 months
       (positive avg = "strong", negative avg = "weak", mixed = "uncertain")
     - Inflation axis : ``CPIAUCSL`` 3-month direction (latest > 3-month
       average = "rising", < = "falling", flat ±0.05 m/m = "uncertain")
     - 2×2 matrix : (strong + rising) = reflation, (strong + falling) =
       expansion, (weak + rising) = stagflation, (weak + falling) =
       deflation, any uncertain = uncertain
     - Confidence : 75% both signals clean, 50% one mixed, 0% uncertain.
       Past ``MAX_FRESHNESS_DAYS = 60`` (r172c calibration), force ``cycle="uncertain"``
       (doctrine #11 calibrated honesty).

  2. **Dominant theme classification (rule-based max |z|)** :
     - Compute z-score of latest value vs trailing 252d mean per FRED
       series in ``_MACRO_FRED_SERIES`` (18 series, source :
       ``couche2_context.py:179-198`` SSOT — imported here)
     - Map each series to a ``MacroTheme`` literal (canonical 8 themes
       from ``packages/agents/.../macro.py:24``)
     - Dominant theme = theme whose representative series has the
       highest |z|. ``None`` when all |z| < 1.0 (no theme stands out
       — doctrine #11).

  3. **Top-3 next surprises (cycle-aware priority)** :
     - Query ``EconomicEvent`` for next 7 days, impact ∈ {high, medium},
       all currencies (asset-agnostic surface).
     - Priority assignment :
       * ``high`` = event class directly tied to current cycle's
         defining variable (CPI/PCE/PPI during stagflation/reflation
         OR NFP/PAYEMS during expansion/deflation OR FOMC always)
       * ``medium`` = HIGH-impact but not cycle-defining
       * ``low`` = medium-impact event included for completeness
     - Top 3 by (priority, proximity).

  4. **Coach paragraph (FR beginner-friendly synthesis)** :
     - 3-sentence template :
       (a) "Aujourd'hui [date FR], on est en [cycle FR] (confiance N%)."
       (b) "Le driver dominant est [theme FR] — [z-score intensity hint]."
       (c) "Surveille [top-1 surprise label + relative time] pour ta
            session NY."
     - 100..600 chars. ADR-017 regex-checked at SessionVerdict-
       construction time by the Pydantic validator.

**Doctrine alignment** :
  - ADR-017 : coach_paragraph + CalendarSurprise.why_it_matters BOTH
    regex-checked
  - Doctrine #4 SSOT : ``MacroTheme`` literal + ``_MACRO_FRED_SERIES``
    mapping imported, not re-defined
  - Doctrine #9 anti-accumulation : ``EconomicEvent`` query in this
    builder is technically a 3rd path vs ``build_economic_calendar_
    context`` + ``event_anticipation_view`` — DEFERRED REFACTOR r162+
    will extract a shared ``_fetch_upcoming_events_async()`` helper
  - Doctrine #11 calibrated honesty : ``cycle="uncertain"`` +
    ``cycle_confidence_pct=0`` returned when FRED stale OR 2×2 ambiguous
"""

from __future__ import annotations

import statistics
from datetime import UTC, datetime, timedelta

from ichor_brain.coach_macro_context import (
    MAX_FRESHNESS_DAYS,
    BusinessCycle,
    CalendarSurprise,
    CoachMacroContext,
    GrowthSignal,
    InflationSignal,
    MacroTheme,  # type: ignore[attr-defined]
    RiskRegime,
    SurprisePriority,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import EconomicEvent, FredObservation

# Doctrine #4 SSOT : the 18 FRED series → 8-theme mapping. The KEYS
# mirror ``services/couche2_context.py:179-198`` verbatim (single source
# of truth) ; the VALUES (theme labels) map each series to one of the
# 8 canonical ``MacroTheme`` literals. r162+ candidate : extract this
# mapping to a shared module so both ``couche2_context`` and this
# builder import from one place.
_SERIES_TO_THEME: dict[str, MacroTheme] = {
    # Inflation data — direct CPI / PCE / PPI prints
    "CPIAUCSL": "inflation_data",
    "CPILFESL": "inflation_data",
    "PCEPI": "inflation_data",
    "PCEPILFE": "inflation_data",
    "PPIACO": "inflation_data",
    # Labor market — employment + jobless
    "PAYEMS": "labor_market",
    "UNRATE": "labor_market",
    "ICSA": "labor_market",
    # Growth data — output + activity
    "GDP": "growth_data",
    "INDPRO": "growth_data",
    # Monetary policy — rate curve + Fed funds
    "DGS10": "monetary_policy",
    "DGS2": "monetary_policy",
    "DFF": "monetary_policy",
    "T10Y2Y": "monetary_policy",
    # Commodity supply — oil canary
    "DCOILWTICO": "commodity_supply",
    # Credit conditions — credit stress + dollar
    "DTWEXBGS": "credit_conditions",
    "BAMLH0A0HYM2": "credit_conditions",
    "VIXCLS": "credit_conditions",
}

# Cycle-aware HIGH-priority event class signals. The classifier maps an
# event's title (lower-cased substring match) to its priority tier
# given the current cycle. Empty list = no cycle-specific HIGH events.
_CYCLE_HIGH_PRIORITY_TITLE_KEYWORDS: dict[BusinessCycle, list[str]] = {
    "reflation": ["cpi", "pce", "ppi", "inflation", "wage"],
    "stagflation": ["cpi", "pce", "ppi", "inflation", "wage", "fomc", "fed"],
    "expansion": ["nfp", "non-farm payrolls", "fomc", "fed", "gdp", "retail sales"],
    "deflation": ["nfp", "non-farm payrolls", "fomc", "fed", "gdp", "jobless claims"],
    "uncertain": ["fomc", "fed"],  # always-relevant fallback
}

# Cycle-defining minimum window (days) for the growth + inflation trend
# extraction. PAYEMS + CPI are monthly ; 90 days gives ~3 prints which
# is the minimum sample for a m/m trend signal.
_TREND_WINDOW_DAYS: int = 90

# z-score rolling window for theme classification. 252 trading days ≈
# 1 calendar year — standard frequentist baseline for macro series.
_ZSCORE_ROLLING_DAYS: int = 252

# Threshold below which the dominant theme is reported as ``None``
# (doctrine #11 calibrated honesty : if no series is more than 1
# standard deviation from its rolling mean, no theme stands out).
_MIN_DOMINANT_Z_THRESHOLD: float = 1.0


async def _fetch_fred_window(
    session: AsyncSession, series_id: str, window_days: int
) -> list[FredObservation]:
    """Fetch FRED observations for one series over the last ``window_days``
    in ASCENDING ``observation_date`` order. Helper isolated for
    testability + doctrine #9 future shared-helper extraction.
    """
    since = datetime.now(UTC).date() - timedelta(days=window_days)
    stmt = (
        select(FredObservation)
        .where(
            FredObservation.series_id == series_id,
            FredObservation.observation_date >= since,
        )
        .order_by(FredObservation.observation_date.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


def _trend_direction(values: list[float], *, dead_zone: float = 0.0) -> str:
    """Return ``"rising"``/``"falling"``/``"flat"`` based on latest value
    vs mean of preceding values. ``dead_zone`` is the |delta| floor below
    which the trend is reported as ``"flat"`` (doctrine #11).
    """
    if len(values) < 2:
        return "flat"
    latest = values[-1]
    history = values[:-1]
    if not history:
        return "flat"
    avg = sum(history) / len(history)
    delta = latest - avg
    if abs(delta) <= dead_zone:
        return "flat"
    return "rising" if delta > 0 else "falling"


def _classify_growth(payems_obs: list[FredObservation]) -> GrowthSignal:
    """Coarse growth axis label from PAYEMS m/m trend. ``strong`` if
    avg of last 3 m/m deltas > 0 (job creation continuing), ``weak`` if
    < 0, ``uncertain`` otherwise.
    """
    if len(payems_obs) < 4:
        return "uncertain"
    values = [float(o.value) for o in payems_obs[-4:]]
    deltas = [values[i] - values[i - 1] for i in range(1, len(values))]
    avg_delta = sum(deltas) / len(deltas)
    if avg_delta > 50.0:  # k jobs/month threshold — non-trivial creation
        return "strong"
    if avg_delta < -50.0:
        return "weak"
    return "uncertain"


def _classify_inflation(cpi_obs: list[FredObservation]) -> InflationSignal:
    """Coarse inflation axis label from CPIAUCSL 3-month trend. ``rising``
    if latest m/m change is materially above 3-month avg m/m change,
    ``falling`` if below, ``uncertain`` otherwise.
    """
    if len(cpi_obs) < 5:
        return "uncertain"
    values = [float(o.value) for o in cpi_obs[-5:]]
    # m/m % changes
    mm_changes = [
        (values[i] - values[i - 1]) / values[i - 1] * 100.0 for i in range(1, len(values))
    ]
    if not mm_changes:
        return "uncertain"
    direction = _trend_direction(mm_changes, dead_zone=0.05)
    if direction == "rising":
        return "rising"
    if direction == "falling":
        return "falling"
    return "uncertain"


def _classify_cycle(
    growth: GrowthSignal, inflation: InflationSignal
) -> tuple[BusinessCycle, float]:
    """Apply the growth × inflation 2×2 matrix. Returns ``(cycle, confidence_pct)``.

    | growth \\ inflation | rising      | falling   | uncertain |
    |--------------------|-------------|-----------|-----------|
    | strong             | reflation   | expansion | uncertain |
    | weak               | stagflation | deflation | uncertain |
    | uncertain          | uncertain   | uncertain | uncertain |
    """
    if growth == "uncertain" or inflation == "uncertain":
        return ("uncertain", 0.0)

    if growth == "strong" and inflation == "rising":
        return ("reflation", 75.0)
    if growth == "strong" and inflation == "falling":
        return ("expansion", 75.0)
    if growth == "weak" and inflation == "rising":
        return ("stagflation", 75.0)
    if growth == "weak" and inflation == "falling":
        return ("deflation", 75.0)

    return ("uncertain", 0.0)


def _z_score_latest(obs: list[FredObservation]) -> float | None:
    """Compute the z-score of the latest observation vs the trailing
    population mean+stdev. Returns ``None`` when the sample is too
    small or stdev is zero (degenerate)."""
    if len(obs) < 30:
        return None
    values = [float(o.value) for o in obs]
    try:
        mean = statistics.mean(values[:-1])
        stdev = statistics.pstdev(values[:-1])
    except statistics.StatisticsError:
        return None
    if stdev == 0:
        return None
    return (values[-1] - mean) / stdev


async def _classify_dominant_theme(
    session: AsyncSession,
) -> tuple[MacroTheme | None, float | None]:
    """Iterate ``_SERIES_TO_THEME``, compute z-score per series, return
    ``(theme, z_value)`` of the highest |z|. Returns ``(None, None)``
    when no series exceeds ``_MIN_DOMINANT_Z_THRESHOLD``."""
    best_theme: MacroTheme | None = None
    best_z: float | None = None

    for series_id, theme in _SERIES_TO_THEME.items():
        obs = await _fetch_fred_window(session, series_id, _ZSCORE_ROLLING_DAYS)
        z = _z_score_latest(obs)
        if z is None:
            continue
        if best_z is None or abs(z) > abs(best_z):
            best_z = z
            best_theme = theme

    if best_z is None or abs(best_z) < _MIN_DOMINANT_Z_THRESHOLD:
        return (None, None)

    return (best_theme, best_z)


# r168 G3 — Risk-regime classifier thresholds (self-calibrating sigma boundaries).
# Pattern #15 R59 immune by design : these are statistical conventions on the
# z-score scale (1-sigma = 0.7 rounded), NOT peer-reviewed claims about
# absolute VIX/HY-IG levels. The z-score is computed over the 252d trailing
# rolling window (same as ``_classify_dominant_theme``) — no new threshold
# pinning, no new query path, no new constant requiring citation.
_RISK_REGIME_Z_RISK_ON: float = -0.7
"""Both VIXCLS and BAMLH0A0HYM2 must be at OR below this z-threshold for
``risk_on``. -0.7σ ≈ bottom 25th-percentile of 1y history ; stress
indicators *both* significantly below trend = calm + tight credit."""


_RISK_REGIME_Z_RISK_OFF: float = +0.7
"""Either VIXCLS or BAMLH0A0HYM2 above this z-threshold triggers
``risk_off``. +0.7σ ≈ top 25th-percentile of 1y history ; one stress
indicator significantly above trend = elevated risk-aversion."""


async def _classify_risk_regime(
    session: AsyncSession,
) -> tuple[RiskRegime, list[str]]:
    """Classify ``risk_on`` / ``risk_off`` / ``transitional`` from z-scores
    of VIXCLS + BAMLH0A0HYM2 over the trailing 252d rolling window.

    Returns ``(regime, evidence)`` where ``evidence`` is up to 3 mechanical
    "<SERIES_ID> z=±X.XX" strings surfacing the classification signal.

    **Pattern #15 R59 immune by design** :
      - No absolute threshold ("VIX > 22 means stress" would be a citation
        claim — REJECTED in r150 PIVOT 1 + r147 Bauer DP21003 hallucination
        catch lineage)
      - Z-score is self-calibrating relative to the series' own 1y history
      - The ±0.7σ boundary is statistical convention (~1-sigma rounded), not
        peer-reviewed citation

    **Doctrine alignment** :
      - #4 SSOT : reuses ``_fetch_fred_window`` + ``_z_score_latest``
        already used by ``_classify_dominant_theme``. No new query path,
        no new constant requiring R59 citation.
      - #9 anti-accumulation : VIXCLS + BAMLH0A0HYM2 are already in
        ``_SERIES_TO_THEME`` (theme=credit_conditions) ; the z-scoring is
        re-performed here (different decision context) but reuses the
        SAME pure helpers — no logic duplication.
      - #11 calibrated honesty : returns ``transitional`` + empty evidence
        when neither indicator crosses ±0.7σ OR when both series are stale
        / sample-too-small. Doctrine #2 strict-scope : honest classification
        beats forced classification.

    **Why not reuse ``regime_classifier.classify_master_regime``** :
      The 7-bucket ``MasterRegime`` requires 7 inputs (skew/vix/hy_oas/nfci/
      cli_us/expinf/term_prem). The skew + nfci + cli_us + expinf + term_prem
      inputs require non-FRED data sources (cboe_skew_observations table +
      FRED-Chicago NFCI feed + OECD CLI feed + EXPINF1YR + THREEFYTP10). For
      r168 atomic ship we keep scope narrow : only the 2 FRED-side stress
      indicators (VIXCLS + BAMLH0A0HYM2). r169+ candidate : extend the
      classifier to use the full ``RegimeInputs`` once the full input
      assembly is shared with ``data_pool._section_executive_summary``.
    """
    # Doctrine #4 SSOT : same FRED series IDs as ``_SERIES_TO_THEME``.
    vix_obs = await _fetch_fred_window(session, "VIXCLS", _ZSCORE_ROLLING_DAYS)
    hy_obs = await _fetch_fred_window(session, "BAMLH0A0HYM2", _ZSCORE_ROLLING_DAYS)

    vix_z = _z_score_latest(vix_obs)
    hy_z = _z_score_latest(hy_obs)

    evidence: list[str] = []
    if vix_z is not None:
        evidence.append(f"VIXCLS z={vix_z:+.2f}σ")
    if hy_z is not None:
        evidence.append(f"BAMLH0A0HYM2 z={hy_z:+.2f}σ")

    # Doctrine #11 honest absence : if BOTH series are insufficient → transitional
    if vix_z is None and hy_z is None:
        return ("transitional", evidence)

    # Risk-on : BOTH stress indicators significantly below their 1y trend.
    # The AND discipline avoids labelling "risk_on" on a single quiet metric
    # while the other is elevated. Both calm = consistent calm regime.
    if (
        vix_z is not None
        and vix_z <= _RISK_REGIME_Z_RISK_ON
        and hy_z is not None
        and hy_z <= _RISK_REGIME_Z_RISK_ON
    ):
        return ("risk_on", evidence)

    # Risk-off : EITHER stress indicator significantly above its 1y trend.
    # The OR discipline catches single-channel stress (vol-only OR credit-only).
    if (vix_z is not None and vix_z >= _RISK_REGIME_Z_RISK_OFF) or (
        hy_z is not None and hy_z >= _RISK_REGIME_Z_RISK_OFF
    ):
        return ("risk_off", evidence)

    # Default : signal sub-threshold → honest transitional.
    return ("transitional", evidence)


def _surprise_priority(title: str, impact: str, cycle: BusinessCycle) -> SurprisePriority:
    """Map event title + impact + current cycle to one of 3 priority tiers."""
    keywords = _CYCLE_HIGH_PRIORITY_TITLE_KEYWORDS.get(cycle, [])
    title_lc = title.lower()
    if any(kw in title_lc for kw in keywords):
        return "high"
    if impact == "high":
        return "medium"
    return "low"


async def _fetch_next_surprises(
    session: AsyncSession, *, cycle: BusinessCycle, max_items: int = 3
) -> list[CalendarSurprise]:
    """Query upcoming EconomicEvent rows + map to CalendarSurprise with
    cycle-aware priority. Asset-agnostic — surface is the same across
    the 5 priority assets (the per-asset relevance is in the verdict
    layer below this).

    DEFERRED REFACTOR r162+ : extract a shared ``_fetch_upcoming_events
    _async(session, hours_ahead, impact_filter)`` helper so this
    builder + ``couche2_context.build_economic_calendar_context`` +
    ``event_anticipation_view`` all read from ONE query path
    (doctrine #9 anti-accumulation, currently a mild violation).
    """
    now = datetime.now(UTC)
    horizon = now + timedelta(days=7)
    stmt = (
        select(EconomicEvent)
        .where(
            EconomicEvent.scheduled_at.is_not(None),
            EconomicEvent.scheduled_at >= now,
            EconomicEvent.scheduled_at <= horizon,
            EconomicEvent.impact.in_(("high", "medium")),
        )
        .order_by(EconomicEvent.scheduled_at.asc())
        .limit(20)
    )
    rows = (await session.execute(stmt)).scalars().all()

    candidates: list[tuple[CalendarSurprise, int]] = []
    priority_rank = {"high": 0, "medium": 1, "low": 2}

    for row in rows:
        if row.scheduled_at is None:
            continue
        priority = _surprise_priority(row.title or "", row.impact or "low", cycle)
        why = _build_why_it_matters(row.title or "Évènement", priority, cycle)
        try:
            surprise = CalendarSurprise(
                event_label=(row.title or "Évènement")[:120],
                scheduled_at_paris=row.scheduled_at,
                priority=priority,
                why_it_matters=why,
            )
        except ValueError:
            # ADR-017 regex caught a forbidden token in the upstream
            # title (very rare) — skip rather than crash the whole brief.
            continue
        candidates.append((surprise, priority_rank[priority]))

    # Sort by (priority_rank ASC, scheduled_at ASC). Stable on ties.
    candidates.sort(key=lambda c: (c[1], c[0].scheduled_at_paris))
    return [c[0] for c in candidates[:max_items]]


def _build_why_it_matters(title: str, priority: SurprisePriority, cycle: BusinessCycle) -> str:
    """Generate a plain-French 1-sentence explainer for one upcoming
    event. ADR-017-safe by construction (template contains zero
    forbidden tokens). Length 10..200 chars per
    ``CalendarSurprise.why_it_matters`` Pydantic constraint."""
    cycle_fr = _CYCLE_FR.get(cycle, "macro")
    if priority == "high":
        return (
            f"Donnée directement liée au cycle {cycle_fr} actuel — "
            f"surveille la surprise pour anticiper le repricing."
        )
    if priority == "medium":
        return (
            f"Évènement à fort impact mais pas spécifique au cycle {cycle_fr} ; "
            f"surveille pour la volatilité globale."
        )
    return "Évènement à impact modéré, inclus pour visibilité du calendrier de la semaine en cours."


_CYCLE_FR: dict[BusinessCycle, str] = {
    "expansion": "expansion (Goldilocks)",
    "reflation": "reflation",
    "deflation": "déflation",
    "stagflation": "stagflation",
    "uncertain": "incertain",
}


_THEME_FR: dict[str, str] = {
    "monetary_policy": "la politique monétaire",
    "growth_data": "les données de croissance",
    "inflation_data": "l'inflation",
    "labor_market": "le marché du travail",
    "fiscal_policy": "la politique fiscale",
    "geopolitics": "la géopolitique",
    "credit_conditions": "les conditions de crédit",
    "commodity_supply": "l'offre des matières premières",
}


def _z_intensity_hint_fr(z: float | None) -> str:
    """FR description of z-score intensity. Used inside the coach
    paragraph."""
    if z is None:
        return "intensité non mesurable cette session"
    az = abs(z)
    if az >= 3.0:
        return "intensité exceptionnelle (|z| ≥ 3)"
    if az >= 2.0:
        return "intensité marquée (|z| ≥ 2)"
    if az >= 1.0:
        return "intensité modérée (|z| ≥ 1)"
    return "intensité faible"


def _build_coach_paragraph(
    cycle: BusinessCycle,
    cycle_confidence_pct: float,
    dominant_theme: MacroTheme | None,
    theme_z: float | None,
    top_next_surprises: list[CalendarSurprise],
    now_utc: datetime,
) -> str:
    """Generate the 3-sentence FR coach paragraph. ADR-017-safe by
    construction (template contains zero forbidden tokens). 100..600
    chars per Pydantic constraint."""
    date_fr = now_utc.strftime("%A %d %B %Y").lower()
    cycle_fr = _CYCLE_FR[cycle]
    if cycle == "uncertain":
        sentence_1 = (
            f"Aujourd'hui {date_fr}, le cycle macro est incertain — soit "
            f"les données FRED sont stales, soit l'axe croissance × inflation "
            f"est trop ambigu pour trancher (doctrine de calibrated honesty)."
        )
    else:
        sentence_1 = (
            f"Aujourd'hui {date_fr}, on est en cycle de {cycle_fr} "
            f"(confiance {cycle_confidence_pct:.0f} %)."
        )

    if dominant_theme is None:
        sentence_2 = (
            "Aucun driver macro ne se détache nettement cette semaine "
            "(toutes les séries FRED restent proches de leur moyenne)."
        )
    else:
        theme_fr = _THEME_FR.get(dominant_theme, dominant_theme)
        intensity_fr = _z_intensity_hint_fr(theme_z)
        sentence_2 = f"Le driver dominant est {theme_fr} — {intensity_fr}."

    if not top_next_surprises:
        sentence_3 = "Aucun évènement à impact majeur n'est attendu dans les 7 jours."
    else:
        next_event = top_next_surprises[0]
        sentence_3 = (
            f"Surveille « {next_event.event_label} » "
            f"({next_event.scheduled_at_paris.strftime('%A %d %B %Hh%M').lower()} Paris) "
            f"pour ta session NY 13h-20h."
        )

    paragraph = " ".join([sentence_1, sentence_2, sentence_3])
    # Clamp at 600 chars to respect the Pydantic constraint.
    if len(paragraph) > 600:
        paragraph = paragraph[:597] + "..."
    return paragraph


async def build_coach_macro_context(
    session: AsyncSession, *, now_utc: datetime | None = None
) -> CoachMacroContext:
    """Build the canonical ``CoachMacroContext`` aggregating the 4-cycle
    classification + dominant theme + top-3 upcoming surprises + FR
    coach paragraph. Pure read-only ; Voie D-clean ; no LLM call.

    Returns a fully-populated ``CoachMacroContext`` even when classifiers
    return ``uncertain`` / ``None`` (doctrine #11 calibrated honesty —
    the paragraph surfaces the situation transparently).
    """
    if now_utc is None:
        now_utc = datetime.now(UTC)

    # --- Cycle classification --------------------------------------
    payems_obs = await _fetch_fred_window(session, "PAYEMS", _TREND_WINDOW_DAYS)
    cpi_obs = await _fetch_fred_window(session, "CPIAUCSL", _TREND_WINDOW_DAYS)
    growth = _classify_growth(payems_obs)
    inflation = _classify_inflation(cpi_obs)
    cycle, confidence = _classify_cycle(growth, inflation)

    # Freshness check — force ``uncertain`` past MAX_FRESHNESS_DAYS.
    freshest_dates = [
        o.observation_date for o in (payems_obs + cpi_obs) if o.observation_date is not None
    ]
    if not freshest_dates:
        freshness_days = 365
    else:
        latest = max(freshest_dates)
        freshness_days = (now_utc.date() - latest).days
    if freshness_days > MAX_FRESHNESS_DAYS:
        cycle = "uncertain"
        confidence = 0.0

    # --- Dominant theme classification -----------------------------
    dominant_theme, theme_z = await _classify_dominant_theme(session)

    # --- r168 G3 Risk regime classification (self-calibrating z-score)
    risk_regime, risk_regime_evidence = await _classify_risk_regime(session)

    # --- Top-3 next surprises (cycle-aware) ------------------------
    surprises = await _fetch_next_surprises(session, cycle=cycle, max_items=3)

    # --- FR coach paragraph ----------------------------------------
    coach_paragraph = _build_coach_paragraph(
        cycle=cycle,
        cycle_confidence_pct=confidence,
        dominant_theme=dominant_theme,
        theme_z=theme_z,
        top_next_surprises=surprises,
        now_utc=now_utc,
    )

    return CoachMacroContext(
        cycle=cycle,
        cycle_confidence_pct=confidence,
        growth_signal=growth,
        inflation_signal=inflation,
        dominant_theme=dominant_theme,
        dominant_theme_strength_z=theme_z,
        risk_regime=risk_regime,
        risk_regime_evidence=risk_regime_evidence,
        top_next_surprises=surprises,
        coach_paragraph=coach_paragraph,
        data_freshness_days=min(freshness_days, 365),
        generated_at_utc=now_utc,
    )
