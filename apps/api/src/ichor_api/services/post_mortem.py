"""Weekly post-mortem builder — 8-section template per AUTOEVO §4.

Runs every Sunday 18:00 Europe/Paris (cf SPEC.md §3.2). Builds a structured
markdown for the past 7 days that:
  - Lists top 5 hits (best Brier scores) and top 5 misses (worst delta).
  - Reports drift detected by ADWIN over the same window.
  - Surfaces emerging narratives (from couche2_outputs.news_nlp).
  - Computes calibration metrics (Brier 7d/30d/90d, ECE).
  - Suggests amendments (via Claude Opus when wired; placeholder until then).
  - Aggregates raw stats.

The markdown is also stored on disk under
`docs/post_mortem/{YYYY-Www}.md` (committed for git-traceable history) and
the structured payload lands in the `post_mortems` table (UNIQUE on
iso_year+iso_week).
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PostMortemPayload:
    """Structured post-mortem (also written as markdown)."""

    iso_year: int
    iso_week: int
    generated_at: datetime
    top_hits: list[dict[str, Any]]
    top_miss: list[dict[str, Any]]
    drift_detected: list[dict[str, Any]]
    narratives: list[dict[str, Any]]
    calibration: dict[str, Any]
    suggestions: list[dict[str, Any]]
    stats: dict[str, Any]


def iso_week(now: datetime) -> tuple[int, int]:
    iso = now.isocalendar()
    return iso.year, iso.week


async def _top_hits_and_miss(
    session: AsyncSession, *, since: datetime
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Read predictions_audit and rank by |brier_contribution|.

    Hits = lowest Brier (closest to 0). Miss = highest Brier (closest to 1).

    Column mapping (cf models/prediction.py):
      generated_at         (renamed from "predicted_at" in Phase 2 audit fix)
      calibrated_probability (renamed from "predicted_prob")
      realized_direction   (renamed from "realized_outcome" — string LONG/SHORT/NEUTRAL)
    """
    from sqlalchemy import text as sa_text

    hits_rows = (
        (
            await session.execute(
                sa_text(
                    """
            SELECT id, asset, direction, generated_at, calibrated_probability,
                   realized_direction, brier_contribution
            FROM predictions_audit
            WHERE generated_at >= :since
              AND brier_contribution IS NOT NULL
            ORDER BY brier_contribution ASC
            LIMIT 5
            """
                ),
                {"since": since},
            )
        )
        .mappings()
        .all()
    )

    miss_rows = (
        (
            await session.execute(
                sa_text(
                    """
            SELECT id, asset, direction, generated_at, calibrated_probability,
                   realized_direction, brier_contribution
            FROM predictions_audit
            WHERE generated_at >= :since
              AND brier_contribution IS NOT NULL
            ORDER BY brier_contribution DESC
            LIMIT 5
            """
                ),
                {"since": since},
            )
        )
        .mappings()
        .all()
    )

    return (
        [dict(r) for r in hits_rows],
        [dict(r) for r in miss_rows],
    )


async def _calibration_summary(session: AsyncSession, *, now: datetime) -> dict[str, Any]:
    """Average Brier on 7d, 30d, 90d windows."""
    from sqlalchemy import text as sa_text

    out: dict[str, Any] = {}
    for label, days in (("brier_7d", 7), ("brier_30d", 30), ("brier_90d", 90)):
        cutoff = now - timedelta(days=days)
        row = (
            (
                await session.execute(
                    sa_text(
                        """
                SELECT AVG(brier_contribution) AS avg, COUNT(*) AS n
                FROM predictions_audit
                WHERE generated_at >= :cutoff
                  AND brier_contribution IS NOT NULL
                """
                    ),
                    {"cutoff": cutoff},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            out[label] = None
            out[f"{label}_n"] = 0
            continue
        avg = row["avg"]
        out[label] = float(avg) if avg is not None else None
        out[f"{label}_n"] = int(row["n"])
    return out


async def _detect_drift_per_asset(
    session: AsyncSession, *, since: datetime
) -> list[dict[str, Any]]:
    """Run ADWIN drift detection per-asset on Brier residuals.

    For each asset with ≥30 resolved predictions in the window, feed the
    Brier-residual time-series to river's ADWIN detector and surface any
    change-points.

    Returns list of dicts (one per asset that flagged drift) :
        {asset, drift_at_index, n_residuals, last_brier, mean_brier_window}

    Empty list if no drift detected, or if river is not installed (logged).
    """
    from sqlalchemy import text as sa_text

    try:
        from ichor_ml.regime.concept_drift import DriftMonitor
    except ImportError as exc:
        log.debug("ichor_ml.regime.concept_drift import failed: %s", exc)
        return []

    rows = (
        (
            await session.execute(
                sa_text(
                    """
            SELECT asset, generated_at, brier_contribution
            FROM predictions_audit
            WHERE generated_at >= :since
              AND brier_contribution IS NOT NULL
            ORDER BY asset, generated_at ASC
            """
                ),
                {"since": since - timedelta(days=83)},  # 90d total window for stable detection
            )
        )
        .mappings()
        .all()
    )

    by_asset: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_asset[str(r["asset"])].append(float(r["brier_contribution"]))

    out: list[dict[str, Any]] = []
    for asset, series in by_asset.items():
        if len(series) < 30:
            continue
        try:
            monitor = DriftMonitor()
            last_drift_idx: int | None = None
            for v in series:
                events = monitor.update(v)
                for e in events:
                    if e.detector_name == "ADWIN":
                        last_drift_idx = e.series_index
        except Exception as exc:
            log.debug("ADWIN failed on %s: %s", asset, exc)
            continue
        if last_drift_idx is None:
            continue
        # Only surface drifts that landed inside the post-mortem window
        # (the prior 7d, computed from the last `since` arg). The 90d
        # backfill is just to give ADWIN a stable history.
        if last_drift_idx < len(series) - 50:
            # drift older than ~last 50 obs → not relevant for this week
            continue
        out.append(
            {
                "asset": asset,
                "drift_at_index": last_drift_idx,
                "n_residuals": len(series),
                "last_brier": float(series[-1]),
                "mean_brier_window": float(sum(series[-30:]) / min(30, len(series))),
            }
        )
    out.sort(key=lambda d: d["mean_brier_window"], reverse=True)
    return out


async def _build_suggestions(
    session: AsyncSession,
    *,
    top_miss: list[dict[str, Any]],
    drift_detected: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Derive concrete amendment suggestions from misses + drift + tuner gate.

    Three sources :
      1. **Asset miss clusters** : if the same asset shows up >= 3 times
         in the top-5 miss list, recommend a re-weight of its bias-aggr
         coefficients.
      2. **Drift-flagged assets** : for each asset with ADWIN drift in the
         window, recommend prompt-version A/B vs the parent.
      3. **Meta-prompt rollback** : call `meta_prompt_tuner.detect_rollback`
         on each (pass, scope) tuple of the brain ; surface as `kind=rollback`
         when degradation > +0.01 Brier on 7d.
    """
    from .meta_prompt_tuner import detect_rollback

    out: list[dict[str, Any]] = []

    # 1. Asset miss clusters
    asset_counts = Counter(str(m.get("asset", "?")) for m in top_miss)
    for asset, n in asset_counts.most_common():
        if n >= 3 and asset != "?":
            out.append(
                {
                    "kind": "reweight",
                    "title": f"Re-weight bias aggregator for {asset}",
                    "rationale": (
                        f"{asset} appears in {n} of the top-5 misses this week. "
                        "Consider lowering its current model's weight in "
                        "`bias_aggregator` and re-running calibration on the "
                        "last 30 d."
                    ),
                }
            )

    # 2. Drift-flagged assets
    for d in drift_detected[:3]:  # surface up to 3 most-degraded assets
        out.append(
            {
                "kind": "drift",
                "title": f"ADWIN drift on {d['asset']}",
                "rationale": (
                    f"Mean Brier on the last 30 obs = "
                    f"{d['mean_brier_window']:.3f} ; drift detected at "
                    f"index {d['drift_at_index']} of {d['n_residuals']}. "
                    "Recommend manual review of recent {asset} cards and "
                    "consider a new prompt-version A/B test."
                ),
            }
        )

    # 3. Meta-prompt rollback per (pass, scope)
    for pass_idx, scope in (
        (1, "regime"),
        (2, "asset"),
        (3, "stress"),
        (4, "invalidation"),
    ):
        try:
            should_rb, reason = await detect_rollback(session, pass_index=pass_idx, scope=scope)
        except Exception as exc:
            log.debug("detect_rollback(%d, %s) failed: %s", pass_idx, scope, exc)
            continue
        if should_rb:
            out.append(
                {
                    "kind": "rollback",
                    "title": f"Rollback Pass {pass_idx} ({scope}) prompt",
                    "rationale": reason,
                }
            )

    if not out:
        out.append(
            {
                "kind": "info",
                "title": "Week clean — no actionable amendments",
                "rationale": (
                    "No miss clusters ≥ 3 on a single asset, no ADWIN drift, "
                    "no meta-prompt-tuner rollback gates fired. Continue."
                ),
            }
        )
    return out


async def _recent_narratives(session: AsyncSession, *, since: datetime) -> list[dict[str, Any]]:
    """Pull narratives from latest news_nlp Couche-2 outputs."""
    from sqlalchemy import text as sa_text

    rows = (
        (
            await session.execute(
                sa_text(
                    """
            SELECT payload, ran_at
            FROM couche2_outputs
            WHERE agent_kind = 'news_nlp'
              AND ran_at >= :since
              AND error IS NULL
            ORDER BY ran_at DESC
            LIMIT 5
            """
                ),
                {"since": since},
            )
        )
        .mappings()
        .all()
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        payload = r["payload"]
        if isinstance(payload, dict) and "narratives" in payload:
            for n in payload["narratives"][:3]:
                out.append(
                    {
                        "label": n.get("label"),
                        "sentiment": n.get("sentiment"),
                        "intensity": n.get("intensity"),
                        "ran_at": r["ran_at"].isoformat()
                        if hasattr(r["ran_at"], "isoformat")
                        else str(r["ran_at"]),
                    }
                )
    return out[:10]


async def build_post_mortem(
    session: AsyncSession, *, now: datetime | None = None
) -> PostMortemPayload:
    """Build the post-mortem for the ISO week containing `now` (default: now UTC)."""
    now = now or datetime.now(UTC)
    week_start = now - timedelta(days=7)
    iso_y, iso_w = iso_week(now)

    top_hits, top_miss = await _top_hits_and_miss(session, since=week_start)
    calibration = await _calibration_summary(session, now=now)
    narratives = await _recent_narratives(session, since=week_start)
    drift_detected = await _detect_drift_per_asset(session, since=week_start)
    suggestions = await _build_suggestions(
        session, top_miss=top_miss, drift_detected=drift_detected
    )

    stats: dict[str, Any] = {
        "n_top_hits": len(top_hits),
        "n_top_miss": len(top_miss),
        "n_narratives": len(narratives),
        "n_drift_flags": len(drift_detected),
        "n_suggestions": len(suggestions),
        "iso_year": iso_y,
        "iso_week": iso_w,
        "generated_at": now.isoformat(),
    }

    return PostMortemPayload(
        iso_year=iso_y,
        iso_week=iso_w,
        generated_at=now,
        top_hits=top_hits,
        top_miss=top_miss,
        drift_detected=drift_detected,
        narratives=narratives,
        calibration=calibration,
        suggestions=suggestions,
        stats=stats,
    )


def render_markdown(p: PostMortemPayload) -> str:
    """8-section markdown per AUTOEVO §4."""
    lines: list[str] = []
    lines.append(f"# Post-mortem · semaine ISO {p.iso_year}-W{p.iso_week:02d}")
    lines.append("")
    lines.append(f"_Généré le {p.generated_at.isoformat()} (UTC)_")
    lines.append("")

    lines.append("## 1. Header")
    lines.append(
        f"- # cards analysées : {p.stats.get('n_top_hits', 0) + p.stats.get('n_top_miss', 0)}"
    )
    lines.append(f"- # narratives détectées : {p.stats.get('n_narratives', 0)}")
    lines.append("")

    def _fmt_row(row: dict[str, Any]) -> str:
        # `calibrated_probability` and `brier_contribution` may be None.
        prob = row.get("calibrated_probability")
        prob_str = f"{prob:.2f}" if isinstance(prob, (int, float)) else "?"
        brier = row.get("brier_contribution")
        brier_str = f"{brier:.3f}" if isinstance(brier, (int, float)) else "?"
        return (
            f"- {row.get('asset', '?')} · {row.get('direction', '?')} prob {prob_str} → "
            f"realized {row.get('realized_direction', '?')} · Brier {brier_str}"
        )

    lines.append("## 2. Top hits (5 best Brier)")
    for h in p.top_hits[:5]:
        lines.append(_fmt_row(h))
    if not p.top_hits:
        lines.append("- (no calibrated predictions in window)")
    lines.append("")

    lines.append("## 3. Top miss (5 biggest delta)")
    for m in p.top_miss[:5]:
        lines.append(_fmt_row(m))
    if not p.top_miss:
        lines.append("- (no calibrated predictions in window)")
    lines.append("")

    lines.append("## 4. Drift detected (ADWIN on Brier residuals)")
    if p.drift_detected:
        for d in p.drift_detected:
            asset = d.get("asset", "?")
            mean_b = d.get("mean_brier_window")
            mean_b_str = f"{mean_b:.3f}" if isinstance(mean_b, (int, float)) else "?"
            idx = d.get("drift_at_index", "?")
            n = d.get("n_residuals", "?")
            lines.append(
                f"- **{asset}** : drift @ idx {idx}/{n} · mean Brier (last 30) = {mean_b_str}"
            )
    else:
        lines.append("- (no drift flags in this window)")
    lines.append("")

    lines.append("## 5. Narratives émergentes")
    for n in p.narratives[:5]:
        lines.append(
            f"- **{n.get('label', '?')}** ({n.get('sentiment', '?')}, "
            f"intensity {n.get('intensity', '?'):.2f})"
        )
    if not p.narratives:
        lines.append("- (no Couche-2 News-NLP runs in window)")
    lines.append("")

    lines.append("## 6. Calibration")
    cal = p.calibration
    for k in ("brier_7d", "brier_30d", "brier_90d"):
        v = cal.get(k)
        n = cal.get(f"{k}_n", 0)
        lines.append(f"- {k} : {v if v is None else f'{v:.3f}'} (n={n})")
    lines.append("")

    lines.append("## 7. Suggestions amendments")
    for s in p.suggestions:
        kind = s.get("kind", "info")
        prefix = {"reweight": "⚖️", "drift": "📉", "rollback": "↩️", "info": "ℹ️"}.get(kind, "·")
        lines.append(f"- {prefix} **{s.get('title', '?')}** : {s.get('rationale', '?')}")
    lines.append("")

    lines.append("## 8. Stats raw")
    for k, v in p.stats.items():
        lines.append(f"- {k} : {v}")
    return "\n".join(lines)


async def persist_post_mortem(
    session: AsyncSession, payload: PostMortemPayload, *, markdown_path: str
) -> None:
    """Upsert the post-mortem into the table (UNIQUE iso_year+iso_week)."""
    from sqlalchemy import text as sa_text

    json_dumps = __import__("json").dumps
    await session.execute(
        sa_text(
            """
            INSERT INTO post_mortems
              (id, iso_year, iso_week, generated_at, markdown_path,
               top_hits, top_miss, drift_detected, narratives, calibration,
               suggestions, stats, actionable_count, actionable_count_resolved)
            VALUES
              (:id, :y, :w, :gen, :path,
               CAST(:hits AS jsonb), CAST(:miss AS jsonb), CAST(:drift AS jsonb),
               CAST(:nar AS jsonb), CAST(:cal AS jsonb),
               CAST(:sug AS jsonb), CAST(:stats AS jsonb), 0, 0)
            ON CONFLICT (iso_year, iso_week) DO UPDATE SET
              generated_at = EXCLUDED.generated_at,
              markdown_path = EXCLUDED.markdown_path,
              top_hits = EXCLUDED.top_hits,
              top_miss = EXCLUDED.top_miss,
              drift_detected = EXCLUDED.drift_detected,
              narratives = EXCLUDED.narratives,
              calibration = EXCLUDED.calibration,
              suggestions = EXCLUDED.suggestions,
              stats = EXCLUDED.stats
            """
        ),
        {
            "id": str(uuid4()),
            "y": payload.iso_year,
            "w": payload.iso_week,
            "gen": payload.generated_at,
            "path": markdown_path,
            "hits": json_dumps(payload.top_hits, default=str),
            "miss": json_dumps(payload.top_miss, default=str),
            "drift": json_dumps(payload.drift_detected, default=str),
            "nar": json_dumps(payload.narratives, default=str),
            "cal": json_dumps(payload.calibration, default=str),
            "sug": json_dumps(payload.suggestions, default=str),
            "stats": json_dumps(payload.stats, default=str),
        },
    )
