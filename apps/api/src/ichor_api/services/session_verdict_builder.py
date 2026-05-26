"""SessionVerdictBuilder — aggregates the 7-bucket Pass-6 ScenarioDecomposition
into the canonical ``SessionVerdict`` per ADR-106 D2.

This is r161 Strand G partial : the verdict aggregation layer. Pure compute,
no LLM call, no external dependency — Voie D-clean. The builder reads the
latest ``session_card_audit`` row for a given (asset, today's NY session)
tuple and derives the verdict deterministically.

**Fallback path (doctrine #11 calibrated honesty)** : when Pass-6 is gated
off (``enable_scenarios=False`` per ``orchestrator.py:114``) the
``session_card_audit.scenarios`` JSONB column persists as ``[]``. The
builder honestly returns a downgraded verdict (``derived_from_scenarios=
False``, ``direction="neutral"``, ``conviction_pct=0``,
``nature="uncertain"``) rather than fabricating a read. The
``coach_explanation`` paragraph surfaces the situation transparently to
the trader so they know the system is in foundation mode awaiting
Pass-6 activation.

**Populated path (Pass-6 active)** : the 7 buckets are aggregated per
ADR-106 D2 algorithm with the 3 directional dead-zones (0.15 directional
threshold, 0.55 nature threshold, 0.45 range threshold) and the
``conviction_pct = max(bullish_mass, bearish_mass) * 100`` rule capped
at ``CAP_95 * 100``.

**ADR-017 boundary preserved by construction** : the verdict's
``coach_explanation`` is regex-checked by the SessionVerdict Pydantic
validator at construction time. The builder generates the paragraph
from templated text + dynamic derived values ; templates contain ZERO
forbidden tokens (BUY/SELL/TP/SL/long entry/short entry/stop loss/
take profit). CI-guarded via ``test_invariants_ichor.py`` extension
(r161 carry-forward).

ADR refs : ADR-106 §D2 (derivation rule), §D3 (refresh cycle), §D4
(frontend surface), §D5 (endpoint contract).
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import SessionCardAudit
from .session_verdict import (
    LiveTrigger,
    PriorityAsset,
    ScenarioInvalidationState,
    SessionVerdict,
    VerdictDirection,
    VerdictNature,
)

# ADR-106 D2 dead-zone thresholds. Anchored to ADR-022 (cap-95) + ADR-085
# (§"The 7 buckets" stratification). Intentionally non-configurable at
# r161 — r162+ calibration via Phase D Brier feedback (ADR-087 W116 PBS).
_DIRECTIONAL_DEAD_ZONE = 0.15
"""bullish_mass vs bearish_mass spread below which direction is
``neutral``. Calibrated to ADR-022 cap-95 : no individual bucket can
cross 0.95, so a 0.15 spread = a meaningful asymmetry, not a coin-flip."""

_NATURE_TAIL_VS_MID_THRESHOLD = 0.55
"""tail_mass / (tail_mass + mid_mass) above which nature is ``momentum``,
below 1 - threshold = ``structured``. The 0.55 anchor reflects the
ADR-085 calibration that ``melt_up + crash_flush`` tail buckets are
~10% prior + ``mild_bull + mild_bear`` mid buckets are ~30% prior, so
a 0.55 majority is a 2x deviation from the natural ratio."""

_RANGE_BOUND_NEUTRAL_THRESHOLD = 0.45
"""neutral_mass = base.p above which nature is ``range_bound`` (the
``base`` bucket dominates the decomposition, indicating low directional
conviction and a fade-extremes regime)."""

# Window stamps per Eliot's r161 directive : "Je prends position entre
# 14h et 16h, et je coupe tout à 20h. C'est ma fenêtre, c'est mon mode
# opératoire." The verdict is calibrated for this window explicitly.
_NY_WINDOW_OPEN_HOUR_PARIS = 14
_NY_WINDOW_CLOSE_HOUR_PARIS = 20
_VERDICT_EXPIRY_BUFFER_MINUTES = 15  # 20h00 + 15min = 20h15 Paris stale

# Paris timezone — locked, never configurable. Eliot's working timezone
# per CLAUDE.md project memory.
_PARIS_TZ = ZoneInfo("Europe/Paris")


def _today_paris_midnight_utc(now_utc: datetime) -> datetime:
    """Return the UTC instant of midnight Paris time today (local to the
    user's working session). Used as the lower bound for fetching the
    latest session_card_audit row for "today's NY session"."""
    paris_now = now_utc.astimezone(_PARIS_TZ)
    midnight_paris = datetime.combine(paris_now.date(), time.min, tzinfo=_PARIS_TZ)
    return midnight_paris.astimezone(UTC)


def _window_stamps_paris(now_utc: datetime) -> tuple[datetime, datetime, datetime]:
    """Return (ne_pas_actionner_avant_paris, couper_au_plus_tard_paris,
    expires_at_utc) for today's NY session window."""
    paris_now = now_utc.astimezone(_PARIS_TZ)
    today = paris_now.date()
    window_open = datetime.combine(today, time(_NY_WINDOW_OPEN_HOUR_PARIS, 0), tzinfo=_PARIS_TZ)
    window_close = datetime.combine(today, time(_NY_WINDOW_CLOSE_HOUR_PARIS, 0), tzinfo=_PARIS_TZ)
    expires_utc = (window_close + timedelta(minutes=_VERDICT_EXPIRY_BUFFER_MINUTES)).astimezone(UTC)
    return window_open, window_close, expires_utc


def _derive_direction_and_conviction(
    scenarios: list[dict[str, Any]],
) -> tuple[VerdictDirection, float]:
    """Apply ADR-106 D2 directional aggregation rule.

    Returns ``(direction, conviction_pct)``. ``direction`` is ``up``,
    ``down``, or ``neutral`` ; ``conviction_pct`` is in ``[0, 95]``.
    """
    by_label = {s["label"]: float(s["p"]) for s in scenarios}
    bullish_mass = (
        by_label.get("mild_bull", 0.0)
        + by_label.get("strong_bull", 0.0)
        + by_label.get("melt_up", 0.0)
    )
    bearish_mass = (
        by_label.get("mild_bear", 0.0)
        + by_label.get("strong_bear", 0.0)
        + by_label.get("crash_flush", 0.0)
    )

    spread = abs(bullish_mass - bearish_mass)
    if spread < _DIRECTIONAL_DEAD_ZONE:
        return ("neutral", 0.0)

    direction: VerdictDirection = "up" if bullish_mass > bearish_mass else "down"
    raw_conviction = max(bullish_mass, bearish_mass) * 100.0
    # Cap at 95 per ADR-022 ; the Pydantic Field constraint will also
    # enforce this, but we clamp defensively to avoid a 422 cascade.
    capped = min(raw_conviction, 95.0)
    return (direction, capped)


def _derive_nature(scenarios: list[dict[str, Any]]) -> VerdictNature:
    """Apply ADR-106 D2 nature classification rule.

    Returns one of ``momentum``, ``structured``, ``range_bound``,
    ``uncertain``.
    """
    by_label = {s["label"]: float(s["p"]) for s in scenarios}
    neutral_mass = by_label.get("base", 0.0)
    if neutral_mass >= _RANGE_BOUND_NEUTRAL_THRESHOLD:
        return "range_bound"

    tail_mass = by_label.get("melt_up", 0.0) + by_label.get("crash_flush", 0.0)
    mid_mass = by_label.get("mild_bull", 0.0) + by_label.get("mild_bear", 0.0)
    denominator = tail_mass + mid_mass + 1e-9

    tail_ratio = tail_mass / denominator
    mid_ratio = mid_mass / denominator
    if tail_ratio >= _NATURE_TAIL_VS_MID_THRESHOLD:
        return "momentum"
    if mid_ratio >= _NATURE_TAIL_VS_MID_THRESHOLD:
        return "structured"
    return "uncertain"


def _build_coach_explanation_populated(
    asset: PriorityAsset,
    direction: VerdictDirection,
    conviction_pct: float,
    nature: VerdictNature,
    scenarios: list[dict[str, Any]],
) -> str:
    """Generate the plain-French beginner-friendly explanation when
    Pass-6 has populated the 7 buckets. The template surfaces : (a) the
    direction + conviction + nature, (b) the dominant bucket(s), (c) the
    fenêtre opératoire stamp, (d) the calibrated-honesty caveat. ZERO
    forbidden tokens by construction.
    """
    by_label = {s["label"]: float(s["p"]) for s in scenarios}
    sorted_buckets = sorted(by_label.items(), key=lambda kv: kv[1], reverse=True)
    top_label, top_p = sorted_buckets[0]
    top_pct = round(top_p * 100, 1)

    direction_fr = {
        "up": "biais haussier",
        "down": "biais baissier",
        "neutral": "biais neutre",
    }[direction]

    nature_fr = {
        "momentum": "mouvement de momentum (impulsif, probablement post-événement)",
        "structured": "mouvement structuré (rythme mesuré, niveaux identifiables)",
        "range_bound": "mouvement range-bound (faible volatilité, fade des extrêmes)",
        "uncertain": "mouvement de nature incertaine (décomposition mixte)",
    }[nature]

    return (
        f"Verdict NY session pour {asset} : {direction_fr} avec "
        f"{conviction_pct:.0f} % de conviction, de type {nature_fr}. "
        f"Le bucket Pass-6 dominant est {top_label} ({top_pct} % de masse). "
        f"Cette lecture est calibrée pour la fenêtre 14h00→20h00 Paris ; "
        f"toute prise de position hors fenêtre doit se baser sur un verdict "
        f"distinct. La conviction est plafonnée à 95 % par construction "
        f"(ADR-022) — aucun verdict ne peut exprimer une certitude absolue."
    )


def _build_coach_explanation_fallback(asset: PriorityAsset) -> str:
    """Generate the plain-French explanation when Pass-6 is dormant
    (``derived_from_scenarios=False`` fallback). Doctrine #11 calibrated
    honesty : explain transparently why the verdict is downgraded
    rather than fabricating a directional read. ZERO forbidden tokens
    by construction.
    """
    return (
        f"Verdict NY session pour {asset} : en mode dormant. Pass-6 "
        f"scenario_decompose n'est pas encore activé en production : les 7 "
        f"buckets ne sont pas générés, donc le verdict ne peut pas être "
        f"dérivé. Par calibrated honesty (doctrine #11), le système refuse "
        f"de fabriquer un read directionnel et retourne biais neutre + "
        f"nature incertaine. La fondation architecturale est en place "
        f"(ADR-106 ratifié r161) ; l'activation Pass-6 + les déclencheurs "
        f"en direct + les invalidations automatiques arriveront dans les "
        f"prochaines sessions du système (Strides 1-7 de la roadmap)."
    )


async def build_session_verdict(
    session: AsyncSession,
    *,
    asset: PriorityAsset,
    now_utc: datetime | None = None,
) -> SessionVerdict | None:
    """Build the canonical ``SessionVerdict`` for (asset, today's NY session).

    Returns ``None`` if no ``session_card_audit`` row exists yet for
    today's Paris-date midnight onwards (caller turns this into HTTP 404).

    Returns a ``SessionVerdict`` with ``derived_from_scenarios=False``
    downgraded fallback when Pass-6 is gated off OR the scenarios JSONB
    is malformed (less than 7 buckets, missing labels, etc.).

    Returns a fully-derived ``SessionVerdict`` per ADR-106 D2 when the
    7 buckets are populated.

    Args :
      session  : Async SQLAlchemy session bound to the live request scope.
      asset    : Priority-5 asset code (frontend universe).
      now_utc  : Injection point for deterministic testing. Default
                 ``datetime.now(UTC)``.

    Returns :
      ``SessionVerdict | None``. ``None`` = no session card yet today.
    """
    if now_utc is None:
        now_utc = datetime.now(UTC)

    midnight_utc = _today_paris_midnight_utc(now_utc)

    stmt = (
        select(SessionCardAudit)
        .where(
            SessionCardAudit.asset == asset,
            SessionCardAudit.generated_at >= midnight_utc,
        )
        .order_by(SessionCardAudit.generated_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    card = result.scalar_one_or_none()

    if card is None:
        # No session card yet today → caller returns HTTP 404.
        return None

    window_open, window_close, expires_utc = _window_stamps_paris(now_utc)

    scenarios_raw: list[dict[str, Any]] = list(card.scenarios or [])

    # Fallback path : Pass-6 dormant OR malformed JSONB.
    if len(scenarios_raw) != 7 or not all(
        isinstance(s, dict) and "label" in s and "p" in s for s in scenarios_raw
    ):
        return SessionVerdict(
            asset=asset,
            direction="neutral",
            conviction_pct=0.0,
            nature="uncertain",
            derived_from_scenarios=False,
            scenario_decomposition_id=None,
            invalidation_state=None,
            live_triggers=[],
            coach_explanation=_build_coach_explanation_fallback(asset),
            ne_pas_actionner_avant_paris=window_open,
            couper_au_plus_tard_paris=window_close,
            last_updated_utc=card.generated_at,
            expires_at_utc=expires_utc,
        )

    # Populated path : derive per ADR-106 D2.
    direction, conviction_pct = _derive_direction_and_conviction(scenarios_raw)
    nature = _derive_nature(scenarios_raw)

    coach_explanation = _build_coach_explanation_populated(
        asset=asset,
        direction=direction,
        conviction_pct=conviction_pct,
        nature=nature,
        scenarios=scenarios_raw,
    )

    # invalidation_state will be populated by r161 Strand D monitor service
    # once it lands. For now (Strand A foundation + Strand H contract +
    # Strand G builder shipped), invalidation_state is None and
    # live_triggers is empty. Frontend renders "Déclencheurs : 0" + "Aucun
    # scénario invalidé" placeholder until Strands C-F activate the monitor.
    invalidation_state: ScenarioInvalidationState | None = None
    live_triggers: list[LiveTrigger] = []

    return SessionVerdict(
        asset=asset,
        direction=direction,
        conviction_pct=conviction_pct,
        nature=nature,
        derived_from_scenarios=True,
        scenario_decomposition_id=str(card.id),
        invalidation_state=invalidation_state,
        live_triggers=live_triggers,
        coach_explanation=coach_explanation,
        ne_pas_actionner_avant_paris=window_open,
        couper_au_plus_tard_paris=window_close,
        last_updated_utc=card.generated_at,
        expires_at_utc=expires_utc,
    )
