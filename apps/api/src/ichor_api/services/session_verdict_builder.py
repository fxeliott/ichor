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

from collections.abc import Sequence
from datetime import UTC, datetime, time, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import SessionCardAudit
from .session_verdict import (
    LiveTrigger,
    PriorityAsset,
    SessionVerdict,
    VerdictDirection,
    VerdictNature,
)

if TYPE_CHECKING:
    from .dimension_vote import DimensionVote

log = structlog.get_logger(__name__)

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


def _extract_synthesis_primitives(
    card: SessionCardAudit,
) -> tuple[str | None, bool, str | None, float]:
    """Read the S04 synthesis snapshots frozen on the card at generation
    (migration 0055) into the primitives ``fuse_conviction`` consumes.

    Returns ``(confluence_lean, theme_present, dollar_consensus,
    dollar_strength)``. Every field defaults to its NO-EVIDENCE value when the
    snapshot is NULL (legacy / pre-0055 card) or malformed — so the fuser
    degrades gracefully to the bucket-only conviction. Pure + defensive ;
    never raises.
    """
    confluence_lean: str | None = None
    theme_present = False
    dollar_consensus: str | None = None
    dollar_strength = 0.0

    conf = card.confluence_snapshot
    if isinstance(conf, dict):
        lean = conf.get("dominant_direction")
        if lean in ("long", "short", "neutral"):
            confluence_lean = lean

    theme = card.theme_snapshot
    if isinstance(theme, dict):
        theme_present = bool(theme.get("present", False))

    dollar = card.dollar_snapshot
    if isinstance(dollar, dict):
        cons = dollar.get("consensus")
        if cons in ("usd_up", "usd_down", "mixed", "neutral"):
            dollar_consensus = cons
        try:
            dollar_strength = float(dollar.get("consensus_strength", 0.0) or 0.0)
        except (TypeError, ValueError):
            dollar_strength = 0.0

    return confluence_lean, theme_present, dollar_consensus, dollar_strength


def _derive_direction_and_conviction(
    scenarios: list[dict[str, Any]],
    *,
    asset: str,
    confluence_lean: str | None = None,
    theme_present: bool = False,
    dollar_consensus: str | None = None,
    dollar_strength: float = 0.0,
    votes: Sequence[DimensionVote] = (),
) -> tuple[VerdictDirection, float, str]:
    """S04 (« kill the 50/50 ») — delegate the apex conviction to the
    evidence-weighted fusion core (``services.conviction_fusion``).

    Direction stays bucket-derived (ADR-017 — bias + probability, never an
    order ; evidence scales MAGNITUDE, never sign). The synthesis evidence
    frozen on the card at generation (confluence lean / dominant-theme
    presence / cross-asset dollar consensus) corroborates or contradicts the
    bucket edge and produces an explicit French grounding.

    With NO synthesis primitives supplied — legacy / pre-0055 cards whose
    snapshots are NULL — the direction is byte-identical to the legacy
    bucket-only ADR-106 D2 path ; only the dead-zone becomes GRADED (the
    intended S04 change : a weak 0.05–0.15 edge survives iff corroborated,
    dies if contradicted, instead of cliff-dropping straight to neutral).

    ``votes`` (Chantier C) are extra ``DimensionVote`` layers forwarded verbatim
    to the fuser ; the default ``()`` keeps the output byte-identical (the real
    layers are wired behind a feature flag in a later slice, C-2b/C-3).

    Returns ``(direction, conviction_pct, rationale_fr)``. ``direction`` is
    ``up``/``down``/``neutral`` ; ``conviction_pct`` is in ``[0, 95]`` ;
    ``rationale_fr`` is the plain-French coach grounding (zero trade tokens).
    """
    # Lazy import keeps the module entry-point light and avoids any import
    # cycle through the services package at collection time.
    from .conviction_fusion import fuse_conviction

    grounding = fuse_conviction(
        asset=asset,
        scenarios=scenarios,
        confluence_lean=confluence_lean,  # type: ignore[arg-type]
        theme_present=theme_present,
        dollar_consensus=dollar_consensus,  # type: ignore[arg-type]
        dollar_strength=dollar_strength,
        votes=votes,
    )
    direction: VerdictDirection = grounding.direction
    return (direction, grounding.conviction_pct, grounding.rationale_fr)


async def _load_reconciled_p_up_y(session: Any) -> list[tuple[float, int]]:
    """C-5 (ADR-118/119) — pooled realised ``(p_up, y)`` from reconciled cards
    (oldest-first), READ-ONLY. Mirrors ``run_calibration_witness._load_samples`` but
    POOLED across all assets/sessions (the Chantier-B witness found the pooled fit
    conclusive on 368 cards). Skips neutral / ambiguous cards (``y is None``). Used
    only on the flag-ON calibration path; the verdict never writes here."""
    from sqlalchemy import select as _select

    from ..models import SessionCardAudit
    from .brier import conviction_to_p_up
    from .brier_optimizer import derive_realized_outcome

    # Bound the apex-path query (durability — prompt ⑥ "permanent, sans fragilité"):
    # take the MOST-RECENT reconciled window (most relevant for a self-adapting
    # calibrator), then re-sort oldest-first for the chronological train/test split.
    # 5000 reconciled cards ≈ years of history at the project's cadence.
    _CALIBRATION_HISTORY_CAP = 5000
    stmt = (
        _select(
            SessionCardAudit.bias_direction,
            SessionCardAudit.conviction_pct,
            SessionCardAudit.brier_contribution,
        )
        .where(SessionCardAudit.brier_contribution.is_not(None))
        .order_by(SessionCardAudit.generated_at.desc())
        .limit(_CALIBRATION_HISTORY_CAP)
    )
    rows = list(reversed((await session.execute(stmt)).all()))
    pairs: list[tuple[float, int]] = []
    for bias, conviction, brier in rows:
        if brier is None:
            continue
        y = derive_realized_outcome(bias, conviction, brier)
        if y is None:  # neutral bias carried no directional forecast
            continue
        pairs.append((conviction_to_p_up(bias, conviction), y))
    return pairs


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
    conviction_rationale_fr: str = "",
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

    base = (
        f"Verdict NY session pour {asset} : {direction_fr} avec "
        f"{conviction_pct:.0f} % de conviction, de type {nature_fr}. "
        f"Le bucket Pass-6 dominant est {top_label} ({top_pct} % de masse). "
        f"Cette lecture est calibrée pour la fenêtre 14h00→20h00 Paris ; "
        f"toute prise de position hors fenêtre doit se baser sur un verdict "
        f"distinct. La conviction est plafonnée à 95 % par construction "
        f"(ADR-022) — aucun verdict ne peut exprimer une certitude absolue."
    )

    # S04 — surface the evidence-weighted grounding ("conviction X % parce que
    # A et B confirment, D s'oppose") so the coach explains WHY the apex reads
    # as it does. Appended only if it fits the 800-char Pydantic ceiling
    # (SessionVerdict.coach_explanation max_length) — never risk a 422 that
    # would block verdict emission.
    if conviction_rationale_fr:
        candidate = f"{base} {conviction_rationale_fr}"
        if len(candidate) <= 800:
            return candidate
    return base


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


async def _safe_evaluate_tradeability(
    session: AsyncSession,
    *,
    asset: str,
    conviction_pct: float,
    now_utc: datetime,
) -> str:
    """r167 G1 — defensive wrapper around ``tradeability_evaluator.evaluate
    _tradeability``. Returns ``"tradeable"`` on ANY exception so the
    verdict emission is never blocked by an evaluator failure (fail-open
    asymmetry : false ``tradeable`` on infra hiccup is less harmful than
    false-flag blocking a normal trading day).

    Imported lazily inside the function to keep the build_session_verdict
    module entry-point fast and to defer the tradeability_evaluator
    initialisation cost until first invocation."""
    try:
        from .tradeability_evaluator import evaluate_tradeability

        return await evaluate_tradeability(
            session,
            asset=asset,
            conviction_pct=conviction_pct,
            now_utc=now_utc,
        )
    except Exception:
        # Doctrine #11 calibrated honesty + fail-open : default to
        # tradeable to never block verdict emission. The tradeability
        # evaluator itself logs structured warnings on internal gates.
        return "tradeable"


# ── Phase 1 A1 (2026-06-02) — real live_triggers feed (ADR-106 Strand E) ──
#
# Per-asset currencies whose macro releases are relevant to the verdict.
# All priority assets are USD-driven; the two non-USD-base FX pairs also
# react to their cross leg. `.get(asset, ("USD",))` keeps any future asset
# safe by defaulting to the dominant USD macro driver.
_ASSET_TRIGGER_CURRENCIES: dict[str, tuple[str, ...]] = {
    "EUR_USD": ("USD", "EUR"),
    "GBP_USD": ("USD", "GBP"),
    "USD_CAD": ("USD", "CAD"),
    "XAU_USD": ("USD",),
    "SPX500_USD": ("USD",),
    "NAS100_USD": ("USD",),
}

# FinBERT signed-confidence threshold for a "strong" news tone burst.
# news_items.tone_score ∈ [-1, 1] (+conf positive / -conf negative / 0
# neutral, see cli/run_news_tone_scorer._signed_score). 0.85 keeps only
# high-confidence headlines out of the firehose.
_STRONG_TONE_ABS = 0.85

# News trigger budget. The news feed is global and asset-agnostic (NewsItem
# has no currency/asset column), so we widen the SQL candidate window then
# keep only the first `_NEWS_TRIGGER_CAP` rows that pass the per-asset
# `matches_asset` keyword guard. Without the wider window a tech-heavy 4-row
# slice could yield zero on-asset triggers after filtering.
_NEWS_CANDIDATE_LIMIT = 40
_NEWS_TRIGGER_CAP = 4

# FR labels for the tone burst surfaced in the trigger description.
_TONE_LABEL_FR: dict[str, str] = {"positive": "positive", "negative": "négative"}


def _clip_trigger_description(text: str, *, minimum: int = 10, maximum: int = 200) -> str | None:
    """Clamp a free-text description to the LiveTrigger 10..200 contract.

    Returns ``None`` (= skip the trigger) when the cleaned text is shorter
    than ``minimum`` — we never pad with filler to satisfy the floor.
    """
    cleaned = " ".join(text.split()).strip()
    if len(cleaned) < minimum:
        return None
    return cleaned[:maximum]


def _try_build_live_trigger(
    *,
    trigger_type: str,
    description: str,
    fired_at_utc: datetime,
    impact: str,
    source: str,
) -> LiveTrigger | None:
    """Construct one ``LiveTrigger``, returning ``None`` (skip) on ANY
    validation failure rather than raising.

    The single biggest risk is the ADR-017 regex on ``description`` : a
    real headline can legitimately contain BUY/SELL ("sell-off",
    "buy-to-let"), which would raise ``ValidationError``. We skip that row
    instead of fabricating or crashing (doctrine #11 calibrated honesty).
    ``fired_at_utc`` is normalised to UTC-aware so the cross-source sort
    can never mix naive and aware datetimes.
    """
    desc = _clip_trigger_description(description)
    if desc is None:
        return None
    fired = fired_at_utc if fired_at_utc.tzinfo is not None else fired_at_utc.replace(tzinfo=UTC)
    try:
        return LiveTrigger(
            trigger_type=trigger_type,  # validated against the Literal
            description=desc,
            fired_at_utc=fired,
            impact=impact,
            source=source[:64],
        )
    except Exception:
        return None


async def _assemble_live_triggers(
    session: AsyncSession,
    *,
    asset: PriorityAsset,
    now_utc: datetime,
) -> list[LiveTrigger]:
    """Build the live-trigger feed from REAL recent data (read-only, no LLM).

    ADR-106 Strand E. Three honest sources :
      • economic releases with a published ``actual`` in the last 12 h
        (high/medium impact, asset-relevant currency) → ``economic_release``
      • central-bank speeches in the last 12 h → ``central_bank_speech``
      • strong-tone news headlines in the last 6 h → ``news_headline``

    Every trigger reports that a real event has FIRED and ``tests`` the
    verdict. We never fabricate a directional ``confirms``/``invalidates``
    without reasoning (doctrine #11). Scenario invalidations are
    deliberately NOT re-emitted here — the frontend already renders them
    as their own block (avoids the doublon).

    Fail-open by construction : each source is independently ``try/except``'d
    and any single bad row is skipped, so this helper never raises. Returns
    most-recent-first, capped at 10 (the ``SessionVerdict.live_triggers``
    contract enforces ``max_length=10``).
    """
    from ..models import CbSpeech, EconomicEvent, NewsItem

    triggers: list[LiveTrigger] = []
    currencies = _ASSET_TRIGGER_CURRENCIES.get(asset, ("USD",))

    # 1 — Economic releases (<12 h, actual published, high/medium impact).
    try:
        cutoff = now_utc - timedelta(hours=12)
        stmt = (
            select(EconomicEvent)
            .where(
                EconomicEvent.scheduled_at.is_not(None),
                EconomicEvent.scheduled_at >= cutoff,
                EconomicEvent.scheduled_at <= now_utc,
                EconomicEvent.actual.is_not(None),
                EconomicEvent.currency.in_(currencies),
                EconomicEvent.impact.in_(("high", "medium")),
            )
            .order_by(EconomicEvent.scheduled_at.desc())
            .limit(8)
        )
        for row in (await session.execute(stmt)).scalars().all():
            consensus = row.forecast if row.forecast not in (None, "") else "n/d"
            trigger = _try_build_live_trigger(
                trigger_type="economic_release",
                description=f"{row.title} — résultat {row.actual} (consensus {consensus})",
                fired_at_utc=row.scheduled_at,
                impact="tests_verdict",
                source=f"economic_events:{row.currency}",
            )
            if trigger is not None:
                triggers.append(trigger)
    except Exception:
        log.warning("verdict.live_triggers.economic_failed", asset=asset, exc_info=True)

    # 2 — Central-bank speeches (<12 h).
    try:
        cutoff = now_utc - timedelta(hours=12)
        stmt = (
            select(CbSpeech)
            .where(CbSpeech.published_at >= cutoff, CbSpeech.published_at <= now_utc)
            .order_by(CbSpeech.published_at.desc())
            .limit(5)
        )
        for row in (await session.execute(stmt)).scalars().all():
            speaker = (row.speaker or "").strip()
            lede = f"{row.central_bank} · {speaker} : " if speaker else f"{row.central_bank} : "
            trigger = _try_build_live_trigger(
                trigger_type="central_bank_speech",
                description=f"{lede}{row.title}",
                fired_at_utc=row.published_at,
                impact="tests_verdict",
                source=f"cb_speeches:{row.central_bank}",
            )
            if trigger is not None:
                triggers.append(trigger)
    except Exception:
        log.warning("verdict.live_triggers.cb_failed", asset=asset, exc_info=True)

    # 3 — Strong-tone news headlines (<6 h), filtered to THIS asset.
    #
    # NewsItem has no currency/asset column — association is keyword-only —
    # so we cannot mirror section 1's SQL `currency.in_(...)` guard. Instead
    # we widen the SQL window and apply the per-row `matches_asset` keyword
    # guard in Python, then cap to the news budget. We deliberately do NOT
    # use `filter_rows_by_asset_affinity`: its `min_required=3` scarce-
    # fallback re-globalizes to the full feed — exactly the off-asset
    # contamination this guard removes (before this, every asset got the same
    # global firehose). `matches_asset` keeps the honest "asset outside
    # NEWS_KEYWORDS → keep all" fallback, so no regression for an unmapped
    # or future asset.
    try:
        from .asset_news_affinity import matches_asset

        cutoff = now_utc - timedelta(hours=6)
        stmt = (
            select(NewsItem)
            .where(
                NewsItem.published_at.is_not(None),
                NewsItem.published_at >= cutoff,
                NewsItem.tone_label.is_not(None),
                NewsItem.tone_score.is_not(None),
                func.abs(NewsItem.tone_score) >= _STRONG_TONE_ABS,
            )
            .order_by(NewsItem.published_at.desc())
            .limit(_NEWS_CANDIDATE_LIMIT)
        )
        news_added = 0
        for row in (await session.execute(stmt)).scalars().all():
            if not matches_asset(row.title or "", row.url or "", asset, row.summary or ""):
                continue
            tone_fr = _TONE_LABEL_FR.get(row.tone_label or "", row.tone_label or "")
            trigger = _try_build_live_trigger(
                trigger_type="news_headline",
                description=f"{row.title} (tonalité {tone_fr})",
                fired_at_utc=row.published_at,
                impact="tests_verdict",
                source=f"news:{row.source}",
            )
            if trigger is not None:
                triggers.append(trigger)
                news_added += 1
                if news_added >= _NEWS_TRIGGER_CAP:
                    break
    except Exception:
        log.warning("verdict.live_triggers.news_failed", asset=asset, exc_info=True)

    triggers.sort(key=lambda t: t.fired_at_utc, reverse=True)
    return triggers[:10]


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

    # r167 G1 — evaluate TradeabilityFlag for the fallback path. The
    # holiday/event_freeze gates are STRUCTURAL (independent of Pass-6
    # state) so a dormant verdict still surfaces "holiday" if today is
    # one — closes Eliot's transcript §VIII gap precisely. Defensive
    # try/except : evaluator failure defaults to "tradeable" (fail-open
    # — false-positive trade day is less harmful than false holiday).
    fallback_tradeability = await _safe_evaluate_tradeability(
        session,
        asset=asset,
        conviction_pct=0.0,
        now_utc=now_utc,
    )

    # Phase 1 A1 — assemble the real live-trigger feed ONCE; both the
    # dormant fallback and the populated verdict surface it (recent
    # economic releases / CB speeches / strong-tone news still fired even
    # when Pass-6 is dormant). Fail-open by construction: never raises.
    live_triggers = await _assemble_live_triggers(session, asset=asset, now_utc=now_utc)

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
            live_triggers=live_triggers,
            coach_explanation=_build_coach_explanation_fallback(asset),
            ne_pas_actionner_avant_paris=window_open,
            couper_au_plus_tard_paris=window_close,
            last_updated_utc=card.generated_at,
            expires_at_utc=expires_utc,
            tradeability=fallback_tradeability,
        )

    # Populated path : derive per ADR-106 D2, now FUSED with the synthesis
    # evidence frozen on the card at generation (S04 — « kill the 50/50 »).
    # The primitives are NULL on legacy / pre-0055 cards → the fuser degrades
    # to the bucket-only conviction (graded dead-zone still applies).
    (
        confluence_lean,
        theme_present,
        dollar_consensus,
        dollar_strength,
    ) = _extract_synthesis_primitives(card)

    # S06 Chantier C — fold the DimensionVotes frozen on the card at generation
    # into the fusion (COT directional + volume non-directional), gated by their
    # feature flags (fail-closed → both OFF ⇒ votes stays () ⇒ byte-identical to
    # the legacy 3-layer path, C-2a). The read fires when ANY dimension flag is on
    # and reads every frozen vote; the write side only froze the votes whose flags
    # were on, so the set is consistent. votes_from_snapshot is defensive: a NULL /
    # legacy / malformed `dimension_votes` degrades to () or honest-absence entries
    # that contribute EXACTLY 0 (ADR-103) — never raises. Lazy import mirrors the
    # fuse_conviction import below (collection-time cycle avoidance).
    votes: Sequence[DimensionVote] = ()
    from .correlations_vote import CORRELATIONS_DIMENSION_VOTE_FLAG
    from .cot_vote import COT_DIMENSION_VOTE_FLAG
    from .feature_flags import is_enabled
    from .geopolitics_vote import GEOPOLITICS_DIMENSION_VOTE_FLAG
    from .manipulation_liquidity_vote import MANIPULATION_LIQUIDITY_DIMENSION_VOTE_FLAG
    from .positioning_divergence_vote import POSITIONING_DIVERGENCE_DIMENSION_VOTE_FLAG
    from .positioning_tff_vote import POSITIONING_TFF_DIMENSION_VOTE_FLAG
    from .sentiment_vote import SENTIMENT_DIMENSION_VOTE_FLAG
    from .vol_regime_vote import VOL_REGIME_DIMENSION_VOTE_FLAG
    from .volume_vote import VOLUME_DIMENSION_VOTE_FLAG

    if (
        await is_enabled(session, COT_DIMENSION_VOTE_FLAG)
        or await is_enabled(session, VOLUME_DIMENSION_VOTE_FLAG)
        or await is_enabled(session, GEOPOLITICS_DIMENSION_VOTE_FLAG)
        or await is_enabled(session, POSITIONING_TFF_DIMENSION_VOTE_FLAG)
        or await is_enabled(session, SENTIMENT_DIMENSION_VOTE_FLAG)
        or await is_enabled(session, VOL_REGIME_DIMENSION_VOTE_FLAG)
        or await is_enabled(session, POSITIONING_DIVERGENCE_DIMENSION_VOTE_FLAG)
        or await is_enabled(session, MANIPULATION_LIQUIDITY_DIMENSION_VOTE_FLAG)
        or await is_enabled(session, CORRELATIONS_DIMENSION_VOTE_FLAG)
    ):
        from .dimension_vote import votes_from_snapshot

        votes = votes_from_snapshot(card.dimension_votes)

    direction, conviction_pct, conviction_rationale_fr = _derive_direction_and_conviction(
        scenarios_raw,
        asset=asset,
        confluence_lean=confluence_lean,
        theme_present=theme_present,
        dollar_consensus=dollar_consensus,
        dollar_strength=dollar_strength,
        votes=votes,
    )

    # S06 C-5 (ADR-118/119) — recalibrate the apex conviction against Ichor's OWN
    # realised track-record, gated by `conviction_calibrator_oos_enabled` (fail-closed
    # → OFF ⇒ raw conviction ⇒ byte-identical to today, golden-harness-guarded). The
    # calibrator is chosen + refit ON-THE-FLY from reconciled outcomes and returns None
    # (no change) unless a family CONCLUSIVELY beats raw OOS (the honesty gate). Direction
    # is NEVER changed (ADR-017): calibration only shrinks/grows the magnitude, and a
    # cross-side calibration collapses conviction to 0 rather than flipping (cap-95 held).
    if direction != "neutral":
        from .brier import BiasDirection
        from .conviction_calibration import (
            CONVICTION_CALIBRATOR_FLAG,
            select_and_fit_live_calibrator,
        )
        from .feature_flags import is_enabled

        if await is_enabled(session, CONVICTION_CALIBRATOR_FLAG):
            calibrator = select_and_fit_live_calibrator(await _load_reconciled_p_up_y(session))
            if calibrator is not None:
                _bias: BiasDirection = "long" if direction == "up" else "short"
                conviction_pct = calibrator.calibrate_conviction(_bias, conviction_pct)

    nature = _derive_nature(scenarios_raw)

    coach_explanation = _build_coach_explanation_populated(
        asset=asset,
        direction=direction,
        conviction_pct=conviction_pct,
        nature=nature,
        scenarios=scenarios_raw,
        conviction_rationale_fr=conviction_rationale_fr,
    )

    # r164 Strand D : invalidation_state now populated by the
    # `scenario_invalidation_monitor.evaluate_scenario_invalidations()`
    # service. The monitor walks each bucket's `invalidations[]` list
    # (populated by r163 Strand C Pass-6 system prompt) and evaluates
    # each `InvalidationCondition` against current data from the
    # appropriate Ichor source (FRED / Polygon / CBOE / Polymarket /
    # honest_gap). Returns `None` when no invalidations are populated
    # on the card yet — typical pre-deploy state since Pass-6
    # `enable_scenarios=False` default keeps `card.scenarios=[]` AND
    # even when scenarios are populated, the LLM prompt change (r163
    # Strand C) needs to propagate via deploy + new emissions before
    # the field is filled. Doctrine #11 calibrated honesty preserved :
    # `None` = "monitor has no data to report" ; non-None with 3 empty
    # lists = "evaluated, all clear" (distinct semantic).
    #
    # Strand E (r165) wires the alerts_runner pipeline on top so a
    # hard-invalidation fire ALSO emits an Ichor alert via the canonical
    # `check_metric()` quadruplet. Strand F (r165) wires the CRON.
    #
    # Phase 1 A1 (2026-06-02) — live_triggers is assembled ABOVE by
    # `_assemble_live_triggers` (economic releases / CB speeches /
    # strong-tone news) and shared by both paths. It is NOT re-emitted from
    # invalidations — the frontend already renders those as their own block.
    try:
        from .scenario_invalidation_monitor import evaluate_scenario_invalidations

        invalidation_state = await evaluate_scenario_invalidations(
            session,
            session_card_id=str(card.id),
            now_utc=now_utc,
        )
    except Exception:
        # Defensive : monitor failure must NOT block verdict emission.
        # Frontend interprets `invalidation_state=None` as "no data" per
        # doctrine #11 (vs hard "all clear" when non-None with empty lists).
        invalidation_state = None

    # r167 G1 — evaluate TradeabilityFlag for the populated path. Uses the
    # derived conviction_pct so the `no_setup` gate (last priority before
    # `tradeable`) can fire for weak Pass-6 emissions even when no
    # structural blocker (holiday / event_freeze / low_vol) is present.
    populated_tradeability = await _safe_evaluate_tradeability(
        session,
        asset=asset,
        conviction_pct=conviction_pct,
        now_utc=now_utc,
    )

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
        tradeability=populated_tradeability,
        ne_pas_actionner_avant_paris=window_open,
        couper_au_plus_tard_paris=window_close,
        last_updated_utc=card.generated_at,
        expires_at_utc=expires_utc,
    )
