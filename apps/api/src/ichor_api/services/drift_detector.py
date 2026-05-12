"""Phase D W114 — ADWIN drift detector + tiered dispatcher (ADR-087).

Detects concept drift on per-asset Brier-residual streams + per-feature
streams via Bifet-Gavaldà ADWIN (Adaptive Windowing) from `river.drift`.

Stateless run model :
  The reconciler nightly cron pulls the last N=200 cards per asset and
  feeds their `brier_contribution` (target ADWIN) + selected feature
  values (per-feature ADWIN) into freshly-instantiated detectors. Drift
  is checked on the most recent update. State is persisted in
  `auto_improvement_log` rows (one per drift event), NOT in pickled
  detector blobs — simpler, auditable, and the daily cadence makes
  re-feeding 200 values cheap (~ms per asset).

Tiered dispatcher (3 tiers per researcher SOTA brief 2025) :

  - tier 1 : single detector fires → structlog alert, advisory only.
    `decision='pending_review'`, no behavior change.
  - tier 2 : 2+ correlated detectors within 60 min OR magnitude > 2σ
    → freeze the Vovk aggregator pocket + spawn challenger weights.
    Write `decision='pending_review'`, `disposition='sequester'`. The
    actual pocket-freeze logic lands in W115 (which provides
    `brier_aggregator_weights.pocket_version` for atomic swap).
  - tier 3 : target ADWIN + 3+ feature ADWINs simultaneously fire
    → regime-collapse signal, escalate to human review via the
    existing `OnFailure=ichor-notify@%n.service` chain (A.4.b).
    Write `decision='pending_review'`, `disposition='retire'`.

References (per round-15 researcher SOTA brief) :
  - Bifet & Gavaldà 2007, SIAM ICDM (ADWIN2 paper).
  - River 0.27 ADWIN docs : https://riverml.xyz/dev/api/drift/ADWIN/
  - Adaptive-Delta ADWIN 2025 (ResearchGate 397309076) — future
    upgrade path if vanilla delta=0.001/0.002 over-fires.

`delta` choice rationale :
  - River default `delta=0.002`. We use `delta=0.001` per-feature
    (microstructure noise dominates → tighter tolerance) and
    `delta=0.002` per-target (Brier residual evolves slowly →
    accept default responsiveness).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

log = structlog.get_logger(__name__)


# Lazy-import river so the module is importable even when the
# `phase-d` extras aren't installed. Production deploy on Hetzner
# MUST install `river>=0.21` ; dev/CI without river will get a clear
# error only when the dispatcher actually runs.
def _adwin(delta: float) -> Any:
    try:
        from river.drift import ADWIN  # type: ignore[import-not-found]
    except ImportError as e:  # pragma: no cover — exercised in CI without phase-d extras
        raise RuntimeError(
            "river.drift.ADWIN missing — install `apps/api[phase-d]` "
            "(adds river>=0.21). Phase D W114 cannot run without it."
        ) from e
    return ADWIN(delta=delta)


@dataclass
class DriftEvent:
    """One ADWIN drift detection, returned by `feed_*`. The dispatcher
    consumes a list of these to decide tier 1/2/3."""

    detector_name: str
    """Identifier : `'target'` or `'feature:<feature_name>'`."""
    asset: str
    """Asset that owns this detector (e.g. `EUR_USD`)."""
    estimation_before: float
    """ADWIN estimation just before drift was detected."""
    estimation_after: float
    """ADWIN estimation just after drift was detected (current window)."""
    magnitude: float
    """`abs(estimation_after - estimation_before)`. Used to tier severity."""
    n_observations: int
    """How many samples were fed in this run before drift fired."""


@dataclass
class AssetDriftBundle:
    """Per-asset detector bundle : 1 target ADWIN + N feature ADWINs.

    Target tracks the Brier residual stream (`|y - p|^2`) — drift =
    model failing. Feature ADWINs track input distributions (e.g., VPIN,
    DXY z-score, FRED:DGS10 surprise) — drift = world changed.
    """

    asset: str
    target_delta: float = 0.002
    feature_delta: float = 0.001
    feature_names: tuple[str, ...] = field(default_factory=tuple)
    """Optional feature stream names to instantiate. Empty tuple = target-only."""

    def feed_target(self, residuals: list[float]) -> DriftEvent | None:
        """Replay `residuals` into a fresh target ADWIN. Returns a
        `DriftEvent` if drift was detected on the final update, else
        None.

        Stateless : ADWIN is re-instantiated each call. Caller supplies
        the sliding window (typically last N=200 reconciled cards).
        """
        if not residuals:
            return None
        det = _adwin(self.target_delta)
        prev_est = 0.0
        for i, x in enumerate(residuals):
            prev_est = float(getattr(det, "estimation", 0.0))
            det.update(x)
            # Only report drift on the LAST update (latest signal). Drift
            # mid-window is historical and already past — re-running this
            # algorithm tomorrow will catch persistent drift again.
            if det.drift_detected and i == len(residuals) - 1:
                est_after = float(getattr(det, "estimation", x))
                return DriftEvent(
                    detector_name="target",
                    asset=self.asset,
                    estimation_before=prev_est,
                    estimation_after=est_after,
                    magnitude=abs(est_after - prev_est),
                    n_observations=len(residuals),
                )
        return None

    def feed_feature(self, feature_name: str, values: list[float]) -> DriftEvent | None:
        """Same protocol as `feed_target`, for one feature stream.

        Caller is responsible for filtering `values` to the asset's
        sliding window.
        """
        if not values:
            return None
        if feature_name not in self.feature_names:
            raise ValueError(
                f"feature_name={feature_name!r} not in bundle.feature_names {self.feature_names!r}"
            )
        det = _adwin(self.feature_delta)
        prev_est = 0.0
        for i, x in enumerate(values):
            prev_est = float(getattr(det, "estimation", 0.0))
            det.update(x)
            if det.drift_detected and i == len(values) - 1:
                est_after = float(getattr(det, "estimation", x))
                return DriftEvent(
                    detector_name=f"feature:{feature_name}",
                    asset=self.asset,
                    estimation_before=prev_est,
                    estimation_after=est_after,
                    magnitude=abs(est_after - prev_est),
                    n_observations=len(values),
                )
        return None


def classify_tier(events: list[DriftEvent], magnitude_sigma_threshold: float = 2.0) -> int:
    """Map a list of co-firing `DriftEvent`s to a tier in {0, 1, 2, 3}.

    Tier 0 = no drift (no events).
    Tier 1 = single detector fired with small magnitude.
    Tier 2 = 2+ detectors fired OR magnitude > `magnitude_sigma_threshold`.
    Tier 3 = target detector + 3+ feature detectors fired simultaneously
             (regime collapse).
    """
    if not events:
        return 0

    n = len(events)
    has_target = any(e.detector_name == "target" for e in events)
    n_features = sum(1 for e in events if e.detector_name.startswith("feature:"))
    max_magnitude = max(e.magnitude for e in events)

    if has_target and n_features >= 3:
        return 3
    if n >= 2 or max_magnitude > magnitude_sigma_threshold:
        return 2
    return 1


async def dispatch_drift_events(
    events: list[DriftEvent],
    *,
    record_fn: Any | None = None,
) -> int:
    """Dispatcher : classify the events into a tier, take action, and
    record one `auto_improvement_log` row.

    `record_fn` is injectable for testing (defaults to
    `services.auto_improvement_log.record`). Returns the tier (0-3).

    Tier 0 : no-op, no DB write.
    Tier 1 : structlog alert + `decision='pending_review'`.
    Tier 2 : same as tier 1 but `disposition='sequester'` (W115 will
             read this and freeze the pocket).
    Tier 3 : same but `disposition='retire'` ; the OnFailure ntfy
             chain reads structlog level=critical to escalate.
    """
    tier = classify_tier(events)
    if tier == 0:
        log.info("drift.no_events")
        return 0

    if record_fn is None:
        # Local import to keep test wiring clean.
        from . import auto_improvement_log as _ail

        record_fn = _ail.record

    assets = sorted({e.asset for e in events})
    detector_names = sorted({e.detector_name for e in events})
    max_event = max(events, key=lambda e: e.magnitude)

    disposition: str | None
    if tier == 3:
        disposition = "retire"
        log.critical(
            "drift.tier3_regime_collapse",
            assets=assets,
            detectors=detector_names,
            max_magnitude=max_event.magnitude,
        )
    elif tier == 2:
        disposition = "sequester"
        log.warning(
            "drift.tier2",
            assets=assets,
            detectors=detector_names,
            max_magnitude=max_event.magnitude,
        )
    else:
        disposition = None
        log.info(
            "drift.tier1",
            assets=assets,
            detectors=detector_names,
            max_magnitude=max_event.magnitude,
        )

    primary_asset = assets[0] if len(assets) == 1 else None
    input_summary = {
        "detectors": detector_names,
        "n_events": len(events),
        "events": [
            {
                "detector_name": e.detector_name,
                "asset": e.asset,
                "estimation_before": e.estimation_before,
                "estimation_after": e.estimation_after,
                "magnitude": e.magnitude,
                "n_observations": e.n_observations,
            }
            for e in events
        ],
    }
    output_summary = {
        "tier": tier,
        "action": {1: "structlog_alert", 2: "pocket_sequester", 3: "human_review"}[tier],
        "max_event": {
            "detector_name": max_event.detector_name,
            "magnitude": max_event.magnitude,
        },
    }

    await record_fn(
        loop_kind="adwin_drift",
        trigger_event=f"reconciler:tier{tier}",
        asset=primary_asset,
        regime=None,
        input_summary=input_summary,
        output_summary=output_summary,
        metric_before=max_event.estimation_before,
        metric_after=max_event.estimation_after,
        metric_name="adwin_estimation",
        decision="pending_review",
        disposition=disposition,
        model_version="adwin_v1",
    )
    return tier
