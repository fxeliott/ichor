"""r165 Strand E — Scenario Invalidation Alerts (ADR-106 §175 Stride 1).

Wraps the r164 ``scenario_invalidation_monitor`` service into the canonical
Ichor alerts pipeline. When the monitor detects that a Pass-6 bucket's
invalidation conditions have fired, this module surfaces the event as an
``Alert`` row (severity-tiered : critical / warning / info) consumable by :

  - The ``/v1/alerts`` endpoint (frontend banner / push notification).
  - The ``alerts_runner`` dedup logic (no spam on every cron tick).
  - The Phase D Brier feedback loop (W116 PBS scoring eventually).

Three severity tiers map 1-to-1 with the monitor's ``InvalidationStatus``
hard/soft/note enum :

  - ``SCENARIO_INVALIDATION_HARD`` (critical) : at least one bucket has a
    hard invalidation fired → bucket's probability is auto-zeroed +
    redistributed (per ADR-106 D2). Trader sees verdict conviction shift
    materially.
  - ``SCENARIO_INVALIDATION_SOFT`` (warning) : at least one bucket has a
    soft invalidation fired (no hard fired in this card) → conviction
    reduced but mass NOT redistributed.
  - ``SCENARIO_INVALIDATION_NOTE`` (info) : at least one bucket has a
    note-severity invalidation fired (no hard/soft) → "context changed"
    visual cue without modifying probabilities.

The 3 ``AlertDef`` entries are added to ``catalog.ALL_ALERTS`` so the
frontend alerts page + push notifier discover them automatically. The
evaluator function ``evaluate_scenario_invalidation_hits()`` is NOT
plugged into ``alerts_runner.check_metric()`` (which expects a single
metric value) — instead it returns ``(AlertHit, asset)`` tuples that the
``check_scenario_invalidations()`` wrapper in ``alerts_runner.py``
de-dups + persists via the same ``_persist_hit()`` machinery.

Doctrine alignment
==================

- **ADR-017 boundary** : zero BUY/SELL emission. The alert merely says
  "scenario X invalidated by condition Y" — descriptive metadata.
- **ADR-106 §175** : Stride 1 continuation. Strand A (schema r161) +
  Strand H (verdict contract r161) + Strand G (apex panel r161) +
  Strand C (Pass-6 prompt r163) + Strand D (monitor r164) + THIS Strand E
  (alerts pipeline r165) + Strand F (CRON r165) complete the cycle.
- **Voie D** : ZERO Anthropic SDK. Pure read of monitor results +
  AlertHit construction.
- **Doctrine #2 strict scope** : single module, evaluator only ; the
  ``check_scenario_invalidations`` runner lives in alerts_runner.py
  for SSOT alignment with the existing pipeline.
- **Doctrine #4 SSOT** : ``AlertDef`` + ``AlertHit`` + ``BUCKET_LABELS``
  + ``InvalidationStatus`` all imported from canonical sources.
- **Doctrine #9 anti-accumulation** : the 3 alert codes follow the
  existing ``catalog.py`` naming convention ``UPPER_SNAKE_CASE`` ;
  added to ``ALL_ALERTS`` via the existing extension pattern (PLAN +
  AUDIT_V2 + this) — no new registry.
- **Doctrine #11 calibrated honesty** : the evaluator returns ``[]`` when
  no card has populated invalidations OR no condition has fired ; the
  alerts pipeline silently no-ops, no fabricated "no alerts" alert.

Build gate target post-r165
============================

- pytest baseline maintained 135/135 + new tests for the catalog
  + evaluator + CI invariant lockstep alerts_catalog × monitor
  severity enum.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import SessionCardAudit
from ..services.scenario_invalidation_monitor import (
    InvalidationStatus,
    evaluate_scenario_invalidations,
)

# S03 (2026-06-11) — AlertDef AND AlertHit now come from the leaf module
# `defs`, killing BOTH halves of the r165 import cycle for good (this module
# previously imported AlertDef back from the catalog that imports it, and
# AlertHit lazily from the catalog-importing evaluator).
from .defs import AlertDef, AlertHit

if TYPE_CHECKING:
    from ichor_brain.session_verdict import BucketLabel  # noqa: F401

log = structlog.get_logger(__name__)


# ── Alert definitions ───────────────────────────────────────────────────


SCENARIO_INVALIDATION_HARD = AlertDef(
    code="SCENARIO_INVALIDATION_HARD",
    severity="critical",
    title_template="Scenario invalidé HARD · {asset} · buckets {buckets}",
    metric_name="scenario_invalidation_hard",
    default_threshold=1.0,
    default_direction="above",
    crisis_mode=False,
    description=(
        "Pass-6 bucket invalidation hard fired — bucket probability "
        "auto-zeroed + mass redistributed per ADR-106 D2. Verdict "
        "conviction shifts materially. Sourced from "
        "r164 scenario_invalidation_monitor."
    ),
)


SCENARIO_INVALIDATION_SOFT = AlertDef(
    code="SCENARIO_INVALIDATION_SOFT",
    severity="warning",
    title_template="Scenario partiellement invalidé · {asset} · buckets {buckets}",
    metric_name="scenario_invalidation_soft",
    default_threshold=1.0,
    default_direction="above",
    crisis_mode=False,
    description=(
        "Pass-6 bucket soft invalidation fired — conviction reduced "
        "but probability NOT auto-redistributed. Consumer surface "
        "shows the contradiction without altering buckets. Sourced "
        "from r164 scenario_invalidation_monitor."
    ),
)


SCENARIO_INVALIDATION_NOTE = AlertDef(
    code="SCENARIO_INVALIDATION_NOTE",
    severity="info",
    title_template="Contexte scenario · {asset} · buckets {buckets}",
    metric_name="scenario_invalidation_note",
    default_threshold=1.0,
    default_direction="above",
    crisis_mode=False,
    description=(
        "Pass-6 bucket note-severity invalidation fired — context "
        "shift surface only, no probability or conviction modification. "
        "Sourced from r164 scenario_invalidation_monitor."
    ),
)


SCENARIO_INVALIDATION_ALERTS: tuple[AlertDef, ...] = (
    SCENARIO_INVALIDATION_HARD,
    SCENARIO_INVALIDATION_SOFT,
    SCENARIO_INVALIDATION_NOTE,
)
"""r165 Strand E — 3 alert definitions joining the canonical catalog.

The 3 severity tiers mirror the monitor's ``InvalidationStatus`` enum
(``fired_hard`` / ``fired_soft`` / ``fired_note``). The ``catalog.py``
``ALL_ALERTS`` tuple imports this constant and concatenates it via the
existing extension pattern.
"""


# ── Map InvalidationStatus → AlertDef ───────────────────────────────────


_STATUS_TO_ALERT_DEF: dict[InvalidationStatus, AlertDef | None] = {
    "fired_hard": SCENARIO_INVALIDATION_HARD,
    "fired_soft": SCENARIO_INVALIDATION_SOFT,
    "fired_note": SCENARIO_INVALIDATION_NOTE,
    "not_fired": None,
    "not_evaluable": None,
}


def _alert_def_for_status(status: InvalidationStatus) -> AlertDef | None:
    """Map a monitor status to its corresponding AlertDef, or None when
    the status is not actionable (``not_fired`` / ``not_evaluable``)."""
    return _STATUS_TO_ALERT_DEF.get(status)


# ── Pure evaluator — reads cards + calls monitor + builds AlertHits ─────


async def evaluate_scenario_invalidation_hits(
    session: AsyncSession,
    *,
    now_utc: datetime | None = None,
    lookback_hours: int = 24,
) -> list[tuple[AlertHit, str]]:
    """Read recent ``session_card_audit`` rows + evaluate invalidations
    per card + build canonical AlertHit objects paired with their asset.

    Returns a list of ``(AlertHit, asset)`` tuples — empty when :
      - no recent cards in the lookback window (no Pass-6 emissions yet)
      - no card has populated ``invalidations`` (pre-r163 or LLM skipped)
      - all conditions evaluate to ``not_fired`` / ``not_evaluable``

    Doctrine #11 calibrated honesty : empty list is a LEGITIMATE output.
    The caller's persistence wrapper just no-ops, no fabricated alert.

    The aggregation rule (mirror of ``evaluate_scenario_invalidations``
    in the monitor) :
      - For each card : the monitor returns a ``ScenarioInvalidationState``
        with 3 bucket-label lists (hard / soft / note).
      - Per severity tier with non-empty list → emit ONE AlertHit for
        the highest-severity tier present (strict hierarchy hard > soft
        > note ; mirror of the monitor's per-bucket discipline).
      - Each AlertHit carries the bucket labels that fired in its
        ``source_payload["buckets"]`` for the title rendering.

    Caveat : the dedup in ``alerts_runner`` is per (alert_code, asset)
    pair within a recent window (5 min default). So if the same hard
    invalidation persists across two cron ticks, only ONE alert lands.
    """
    from datetime import timedelta

    now = now_utc or datetime.now(UTC)

    since = now - timedelta(hours=lookback_hours)

    # Read all recent cards (one per asset/session_type ; up to ~24/day).
    stmt = (
        select(SessionCardAudit.id, SessionCardAudit.asset, SessionCardAudit.generated_at)
        .where(SessionCardAudit.generated_at >= since)
        .order_by(SessionCardAudit.generated_at.desc())
    )
    rows = (await session.execute(stmt)).all()

    if not rows:
        return []

    hits: list[tuple[AlertHit, str]] = []

    for card_id, asset, generated_at in rows:
        try:
            state = await evaluate_scenario_invalidations(
                session,
                session_card_id=str(card_id),
                now_utc=now,
            )
        except Exception as exc:
            log.warning(
                "scenario_invalidation_alerts.monitor_failed",
                card_id=str(card_id),
                asset=asset,
                error=str(exc)[:200],
            )
            continue

        if state is None:
            # No invalidations populated on this card OR monitor returned
            # the doctrine #11 "no data" signal. No alert emission.
            continue

        # Strict hierarchy hard > soft > note. ONE alert per (card, severity)
        # tier present — the highest tier wins. The card may have multiple
        # buckets in the SAME tier list ; we surface them all in the payload.
        for tier_status, bucket_list in (
            ("fired_hard", state.scenarios_invalidated_hard),
            ("fired_soft", state.scenarios_invalidated_soft),
            ("fired_note", state.scenarios_with_notes),
        ):
            if not bucket_list:
                continue
            alert_def = _alert_def_for_status(tier_status)  # type: ignore[arg-type]
            if alert_def is None:
                continue
            payload = {
                "card_id": str(card_id),
                "card_generated_at": generated_at.isoformat() if generated_at else None,
                "buckets": ",".join(sorted(bucket_list)),
                "n_buckets": len(bucket_list),
                "last_check_utc": state.last_check_utc.isoformat(),
            }
            hit = AlertHit(
                alert_def=alert_def,
                metric_value=float(len(bucket_list)),
                threshold=alert_def.default_threshold,
                direction_observed="above",
                source_payload=payload,
            )
            hits.append((hit, asset))
            # Highest tier wins → break after first non-empty tier.
            break

    return hits


__all__ = [
    "SCENARIO_INVALIDATION_ALERTS",
    "SCENARIO_INVALIDATION_HARD",
    "SCENARIO_INVALIDATION_NOTE",
    "SCENARIO_INVALIDATION_SOFT",
    "evaluate_scenario_invalidation_hits",
]
