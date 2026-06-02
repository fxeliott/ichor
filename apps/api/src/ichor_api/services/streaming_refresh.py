"""Phase 7 — Streaming-cadence verdict refresh (ADR-109, §6.4 « réagir
l'instant où ça tombe »).

Between the 4×/day batch emissions a strong event can land — a fresh
economic release (published ``actual``), a central-bank speech, or a
strong-tone news burst. This service detects such an event PER ASSET —
anything that fired AFTER the asset's last persisted card — and, when
found, regenerates ONLY that asset's session card (full 4-pass + Pass-6
Opus) and pushes a notification, so the trader's NY-session verdict is
never stale to a market-moving event for more than one short cron tick.

Design (ultra-deep, anti-doublon, durable) :

* **Detection reuses ``_assemble_live_triggers`` verbatim** — the single
  source of truth for the 3 event sources (economic releases / CB
  speeches / strong-tone news), their freshness windows (12h/12h/6h),
  the per-asset currency relevance map, the strong-tone threshold, and
  the ADR-017 description validation. We only POST-FILTER its output to
  ``fired_at_utc > last_card.generated_at`` → "a NEW strong event since
  the asset's last card". Zero query duplication.
* **Regen reuses ``run_session_card._run`` verbatim** (``run_one_card``)
  — the exact path the 4×/day batch uses : 4-pass + Pass-6 Opus +
  safety gate + coherence reconciliation + persist to
  ``session_card_audit`` + Redis publish. The streaming card is byte-
  for-byte the same shape as a batch card. The regen window
  (``session_type``) is the asset's LATEST card window, so the refresh
  updates exactly what the trader is looking at (``build_session_verdict``
  reads the latest card by ``generated_at``).
* **Voie D** : the regen routes through the Win11 runner (``live=True``);
  detection + push are pure DB reads / web-push. Zero Anthropic spend.
* **ADR-017** : the push copy is built from the triggering ``LiveTrigger``
  whose ``description`` is already ADR-017-validated (``_try_build_live
  _trigger``); it is re-checked with ``is_adr017_clean`` defensively. The
  notification describes the event, never prescribes a trade.

Bounding (stateless, durable — no extra infra, no new failure mode) :

* **Per-asset cooldown** — skip if the asset's last card is younger than
  ``cooldown_minutes`` (default 45). Because every regen (AND every
  batch) advances ``generated_at``, this self-limits re-fires and also
  respects a card the batch just produced.
* **Per-fire cap** — at most ``max_regens_per_fire`` assets regenerated
  in one cron tick; the rest (most-recent-event-first priority) are
  logged as drops and picked up next tick. NEVER a silent cap.

  Derived hourly ceiling : with a ~12-min cron + 45-min cooldown over 6
  assets, an asset can regenerate at most once per cooldown window, so
  the system tops out at ~``6 × (60/45)`` ≈ 8 streaming regens/hour —
  deterministic, no cross-fire state required.

Every decision (regenerate / cooldown-drop / cap-drop / regen-fail /
no-event / no-card) yields an explicit ``RefreshOutcome`` and a structured
log line — no silent truncation.

This module is ADDITIVE and flag-gated at the CLI layer
(``streaming_refresh_enabled``, fail-closed). It NEVER touches the 4×/day
batch path.

ADR refs : ADR-109 (this), ADR-106 §D2/§D4 (verdict), ADR-085 (Pass-6),
ADR-017 (boundary), ADR-009 (Voie D), ADR-030 (ResolveCron).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..models import SessionCardAudit
from .session_verdict import LiveTrigger
from .session_verdict_builder import (
    _ASSET_TRIGGER_CURRENCIES,
    _assemble_live_triggers,
    _today_paris_midnight_utc,
)

log = structlog.get_logger(__name__)

# Default universe = the keys of the verdict's currency-relevance map,
# which are exactly the 6-asset batch universe (ADR-083 D1 : EUR_USD,
# GBP_USD, USD_CAD, XAU_USD, SPX500_USD, NAS100_USD). Deriving it here
# keeps the streaming watcher's universe a single source of truth with
# the detection layer it reuses — no import of the cli batch module (no
# services→cli layering inversion).
_DEFAULT_ASSETS: tuple[str, ...] = tuple(_ASSET_TRIGGER_CURRENCIES)

_DEFAULT_COOLDOWN_MINUTES = 45
_DEFAULT_MAX_REGENS_PER_FIRE = 3

# Human-readable French label for the triggering event class, used in the
# push body. ADR-017-safe (descriptive, never imperative).
_TRIGGER_TYPE_FR: dict[str, str] = {
    "economic_release": "résultat économique",
    "central_bank_speech": "banque centrale",
    "news_headline": "actualité forte",
}

# A callable that regenerates + persists ONE asset's session card and
# returns a shell-style exit code (0 = success). Default binding is
# ``run_session_card._run`` (lazy-imported to avoid a services→cli import
# at module load); injectable for tests.
RegenFn = Callable[..., Awaitable[int]]
# A callable that delivers a push notification to all subscribers and
# returns the number of deliveries. Default = ``push.send_to_all``.
PushFn = Callable[..., Awaitable[int]]


@dataclass(frozen=True)
class RefreshCandidate:
    """An asset that has a NEW strong event since its last card and is
    past its cooldown — eligible for a streaming regeneration."""

    asset: str
    session_type: str
    last_generated_at: datetime
    newest_trigger: LiveTrigger
    new_trigger_count: int


@dataclass(frozen=True)
class RefreshOutcome:
    """The recorded decision for one asset in a single cron fire."""

    asset: str
    action: str  # "regenerated" | "dry_run" | "skipped" | "dropped" | "failed"
    reason: str  # "regen_ok" | "would_regen" | "no_card" | "no_event"
    #             | "cooldown" | "per_fire_cap" | "regen_failed" | "detect_error"
    pushed: bool = False
    detail: str = ""


@dataclass(frozen=True)
class StreamingRefreshResult:
    """Aggregate of one cron fire — every asset has exactly one outcome
    (plus extra ``per_fire_cap`` outcomes for capped candidates)."""

    outcomes: list[RefreshOutcome] = field(default_factory=list)

    @property
    def regenerated(self) -> int:
        return sum(1 for o in self.outcomes if o.action == "regenerated")

    @property
    def pushed(self) -> int:
        return sum(1 for o in self.outcomes if o.pushed)

    @property
    def dropped(self) -> int:
        return sum(1 for o in self.outcomes if o.action == "dropped")

    @property
    def failed(self) -> int:
        return sum(1 for o in self.outcomes if o.action == "failed")


def _as_utc(dt: datetime) -> datetime:
    """Normalise a possibly-naive datetime to UTC-aware so comparisons
    against the UTC-aware ``LiveTrigger.fired_at_utc`` never raise."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


async def _detect_one(
    session: AsyncSession,
    *,
    asset: str,
    now_utc: datetime,
    cooldown_minutes: int,
) -> tuple[RefreshCandidate | None, RefreshOutcome | None]:
    """Detect whether ``asset`` needs a streaming refresh.

    Returns ``(candidate, None)`` when eligible, or ``(None, outcome)``
    with an explicit drop/skip reason. Bounds the latest-card lookup to
    today's Paris-date (mirrors ``build_session_verdict``) so a refresh
    only ever targets the card the trader currently sees, and so a
    weekend/holiday with no card today is a clean ``no_card`` skip rather
    than a regen of a stale card.
    """
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
    card = (await session.execute(stmt)).scalar_one_or_none()
    if card is None:
        return None, RefreshOutcome(asset=asset, action="skipped", reason="no_card")

    last_gen = _as_utc(card.generated_at)

    # Reuse the verdict's live-trigger assembly verbatim (3 sources +
    # thresholds + currency relevance + ADR-017 validation), then keep
    # only what fired AFTER the last card = a genuinely NEW strong event.
    triggers = await _assemble_live_triggers(
        session,
        asset=asset,  # type: ignore[arg-type]  # str ⊇ PriorityAsset; the map covers all 6
        now_utc=now_utc,
    )
    new_triggers = [t for t in triggers if t.fired_at_utc > last_gen]
    if not new_triggers:
        return None, RefreshOutcome(asset=asset, action="skipped", reason="no_event")

    age_minutes = (now_utc - last_gen).total_seconds() / 60.0
    if age_minutes < cooldown_minutes:
        return None, RefreshOutcome(
            asset=asset,
            action="dropped",
            reason="cooldown",
            detail=(
                f"last card {age_minutes:.0f}min < {cooldown_minutes}min cooldown · "
                f"{len(new_triggers)} new trigger(s) deferred to next tick"
            ),
        )

    newest = max(new_triggers, key=lambda t: t.fired_at_utc)
    candidate = RefreshCandidate(
        asset=asset,
        session_type=card.session_type,
        last_generated_at=last_gen,
        newest_trigger=newest,
        new_trigger_count=len(new_triggers),
    )
    return candidate, None


async def detect_refresh_candidates(
    session: AsyncSession,
    *,
    assets: Sequence[str],
    now_utc: datetime,
    cooldown_minutes: int = _DEFAULT_COOLDOWN_MINUTES,
) -> tuple[list[RefreshCandidate], list[RefreshOutcome]]:
    """Detect, across ``assets``, which need a streaming refresh.

    Fail-soft per asset : a detection error on one asset is logged and
    recorded as a ``detect_error`` skip, never aborts the others.
    """
    candidates: list[RefreshCandidate] = []
    outcomes: list[RefreshOutcome] = []
    for asset in assets:
        try:
            candidate, outcome = await _detect_one(
                session,
                asset=asset,
                now_utc=now_utc,
                cooldown_minutes=cooldown_minutes,
            )
        except Exception:
            log.warning("streaming_refresh.detect_failed", asset=asset, exc_info=True)
            outcomes.append(RefreshOutcome(asset=asset, action="skipped", reason="detect_error"))
            continue
        if candidate is not None:
            candidates.append(candidate)
        if outcome is not None:
            outcomes.append(outcome)
    return candidates, outcomes


async def _notify_refresh(asset: str, trigger: LiveTrigger, *, push_fn: PushFn) -> bool:
    """Push an event-keyed notification mirroring ``alerts_runner._maybe
    _notify``'s contract : ADR-017 re-check + ``send_to_all`` to
    ``/briefing/{asset}`` + fail-soft. The body is the triggering event's
    description (already ADR-017-clean from ``_try_build_live_trigger``).
    """
    from .adr017_filter import is_adr017_clean

    asset_pretty = asset.replace("_", "/")
    type_fr = _TRIGGER_TYPE_FR.get(trigger.trigger_type, "événement")
    title = f"Ichor · {asset_pretty} · verdict réactualisé"
    body = f"{type_fr} : {trigger.description}"
    if not (is_adr017_clean(title) and is_adr017_clean(body)):
        log.warning("streaming_refresh.notify_adr017_skip", asset=asset)
        return False
    try:
        delivered = await push_fn(title[:120], body[:240], url=f"/briefing/{asset}")
        log.info("streaming_refresh.notify_sent", asset=asset, delivered=delivered)
        return True
    except Exception:
        log.warning("streaming_refresh.notify_failed", asset=asset, exc_info=True)
        return False


async def run_streaming_refresh(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    now_utc: datetime | None = None,
    cooldown_minutes: int = _DEFAULT_COOLDOWN_MINUTES,
    max_regens_per_fire: int = _DEFAULT_MAX_REGENS_PER_FIRE,
    assets: Sequence[str] | None = None,
    dry_run: bool = False,
    enable_rag: bool = True,
    enable_tools: bool = False,
    regen_fn: RegenFn | None = None,
    push_fn: PushFn | None = None,
) -> StreamingRefreshResult:
    """Run one streaming-refresh cron fire.

    Detect (one short read-only session, closed BEFORE the ~200s regens),
    prioritise most-recent-event first, apply the per-fire cap, then
    regenerate + push each surviving candidate. ``regen_fn`` / ``push_fn``
    default to the production bindings (lazy-imported) and are injectable
    for tests.
    """
    if now_utc is None:
        now_utc = datetime.now(UTC)
    universe = tuple(assets) if assets else _DEFAULT_ASSETS

    # 1 — detect (own session; closed before the slow regens so we never
    #     hold a DB connection across a 200s Opus card).
    async with session_factory() as session:
        candidates, outcomes = await detect_refresh_candidates(
            session,
            assets=universe,
            now_utc=now_utc,
            cooldown_minutes=cooldown_minutes,
        )

    # 2 — prioritise the most-recent event first (a fresher catalyst is
    #     the more valuable refresh under the per-fire cap).
    candidates.sort(key=lambda c: c.newest_trigger.fired_at_utc, reverse=True)

    # 3 — per-fire cap : the overflow is logged (NEVER silent) and picked
    #     up on the next tick.
    to_regen = candidates[:max_regens_per_fire]
    capped = candidates[max_regens_per_fire:]
    for c in capped:
        log.info(
            "streaming_refresh.drop",
            asset=c.asset,
            reason="per_fire_cap",
            new_triggers=c.new_trigger_count,
            cap=max_regens_per_fire,
            candidates=len(candidates),
        )
        outcomes.append(
            RefreshOutcome(
                asset=c.asset,
                action="dropped",
                reason="per_fire_cap",
                detail=f"{len(candidates)} candidates > cap {max_regens_per_fire}; deferred to next tick",
            )
        )

    # 4 — regenerate + push each surviving candidate. Lazy-bind the
    #     production callables (avoid a services→cli import at load time).
    if regen_fn is None:
        from ..cli.run_session_card import _run as _default_regen

        regen_fn = _default_regen
    if push_fn is None:
        from .push import send_to_all as _default_push

        push_fn = _default_push

    for c in to_regen:
        if dry_run:
            log.info(
                "streaming_refresh.dry_run",
                asset=c.asset,
                session_type=c.session_type,
                trigger_type=c.newest_trigger.trigger_type,
                trigger=c.newest_trigger.description[:80],
            )
            outcomes.append(
                RefreshOutcome(
                    asset=c.asset,
                    action="dry_run",
                    reason="would_regen",
                    detail=c.newest_trigger.description[:120],
                )
            )
            continue

        try:
            rc = await regen_fn(
                c.asset,
                c.session_type,
                live=True,
                enable_rag=enable_rag,
                enable_tools=enable_tools,
            )
        except Exception:
            log.warning("streaming_refresh.regen_raised", asset=c.asset, exc_info=True)
            outcomes.append(
                RefreshOutcome(
                    asset=c.asset, action="failed", reason="regen_failed", detail="exception"
                )
            )
            continue

        if rc != 0:
            log.warning("streaming_refresh.regen_nonzero", asset=c.asset, rc=rc)
            outcomes.append(
                RefreshOutcome(
                    asset=c.asset, action="failed", reason="regen_failed", detail=f"rc={rc}"
                )
            )
            continue

        pushed = await _notify_refresh(c.asset, c.newest_trigger, push_fn=push_fn)
        log.info(
            "streaming_refresh.regenerated",
            asset=c.asset,
            session_type=c.session_type,
            trigger_type=c.newest_trigger.trigger_type,
            pushed=pushed,
        )
        outcomes.append(
            RefreshOutcome(
                asset=c.asset,
                action="regenerated",
                reason="regen_ok",
                pushed=pushed,
                detail=c.newest_trigger.description[:120],
            )
        )

    return StreamingRefreshResult(outcomes=outcomes)
