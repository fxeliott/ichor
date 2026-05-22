"""Convert a `SessionCard` into a `session_card_audit` row.

The brain package imports the api ORM model lazily inside the function
so the brain stays installable in environments that don't have the api
package on the path (e.g. pure-pipeline tests).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from .types import SessionCard

if TYPE_CHECKING:
    from ichor_api.models.session_card_audit import SessionCardAudit  # pragma: no cover


def to_audit_row(card: SessionCard) -> SessionCardAudit:
    """Map a `SessionCard` to an unflushed `SessionCardAudit` instance.

    Brier-related columns (`realized_*`, `brier_contribution`) are left
    NULL — they're back-filled later by the outcome reconciler.
    """
    from ichor_api.models.session_card_audit import SessionCardAudit  # local import

    return SessionCardAudit(
        id=uuid4(),
        generated_at=card.generated_at,
        created_at=datetime.now(UTC),
        session_type=card.session_type,
        asset=card.asset,
        model_id=card.model_id,
        regime_quadrant=card.regime.quadrant,
        bias_direction=card.specialization.bias_direction,
        conviction_pct=card.stress.revised_conviction_pct,
        magnitude_pips_low=card.specialization.magnitude_pips_low,
        magnitude_pips_high=card.specialization.magnitude_pips_high,
        timing_window_start=card.specialization.timing_window_start,
        timing_window_end=card.specialization.timing_window_end,
        mechanisms=_dump_list(card.specialization.mechanisms),
        invalidations=_dump_list(card.invalidation.conditions),
        catalysts=_dump_list(card.specialization.catalysts),
        correlations_snapshot=dict(card.specialization.correlations_snapshot),
        polymarket_overlay=_dump_list(card.specialization.polymarket_overlay),
        source_pool_hash=card.source_pool_hash,
        critic_verdict=card.critic.verdict,
        critic_findings=_dump_list(card.critic.findings),
        claude_raw_response=card.model_dump(mode="json"),
        claude_duration_ms=card.claude_duration_ms,
        # Sprint 16 : per-factor drivers from confluence_engine at
        # generation time. NULL when the upstream pipeline doesn't
        # pre-compute them — column added by migration 0026.
        drivers=_dump_list(card.drivers),
        # W105d (ADR-085) : Pass-6 7-bucket scenario decomposition.
        # `card.scenarios` is None when the orchestrator skipped Pass-6
        # (legacy or `tool_config.enabled_for_passes` excludes
        # `scenarios`). Migration 0039 column is NOT NULL with default
        # `'[]'::jsonb` — we pass an empty list rather than None so the
        # server default isn't shadowed by an explicit NULL.
        scenarios=_dump_list(card.scenarios) or [],
        # r62 (ADR-083 D3) : KeyLevel snapshot at finalization. Same
        # NOT NULL + DEFAULT `'[]'::jsonb` semantics as `scenarios` —
        # pass `[]` not `None` when the snapshot wasn't composed.
        key_levels=_dump_list(card.key_levels) or [],
        # realized_scenario_bucket left None — populated by the W105g
        # reconciler after the session window closes.
    )


def _dump_list(items: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    """Defensive copy so the ORM row doesn't share refs with the card."""
    if items is None:
        return None
    return [dict(it) for it in items]
