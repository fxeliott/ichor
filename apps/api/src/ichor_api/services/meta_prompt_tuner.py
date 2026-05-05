"""Meta-prompt tuner — DSPy MIPROv2 wrapper.

Per ADR-021 + AUTOEVO §3 + research 2026-05-04:
  - Workflow: BootstrapFewShot → MIPROv2 → BootstrapFinetune → Ensemble.
  - Auto modes: light (dev) / medium (pre-prod) / heavy (prod).
  - Eval pre-merge: run on devset (50-100 Eliot-labelled cards), require
    new ≥ baseline on ALL metrics + >2pts on ≥1.
  - Rollback auto J+7 if Brier delta > +0.01 sustained.
  - Storage: track_stats=True + log_dir → save("optimized.json") versions.

Cron schedule: 1er + 15 du mois 03h Paris (Win11 runner).

This V0 is a scaffold — the heavy lifting (BootstrapFewShot signature
construction, dspy.Evaluate over the devset, A/B comparison) needs the
DSPy library installed (`dspy-ai`) and the eval devset built. The
service exposes the API surface that the cron CLI calls.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class PromptCandidate:
    """One candidate prompt produced by MIPROv2."""

    pass_index: int
    scope: str  # 'regime' | 'asset' | 'stress' | 'invalidation'
    body: str
    parent_id: UUID | None
    rationale: str | None = None


@dataclass(frozen=True)
class EvalResult:
    """Outcome of running a candidate against the devset."""

    approval_rate: float | None
    faithfulness: float | None
    brier_proj: float | None
    ece: float | None
    hallucination_rate: float | None
    extra: dict[str, Any] = field(default_factory=dict)


def passes_promotion_gate(new: EvalResult, baseline: EvalResult) -> tuple[bool, str]:
    """Promotion criteria per AUTOEVO §3.

    Returns (ok, reason).
    """
    metrics = ("approval_rate", "faithfulness", "brier_proj", "ece", "hallucination_rate")
    deltas: dict[str, float] = {}
    for m in metrics:
        a = getattr(new, m)
        b = getattr(baseline, m)
        if a is None or b is None:
            continue
        # Brier + ECE + hallucination_rate: lower is better → invert sign.
        sign = -1.0 if m in ("brier_proj", "ece", "hallucination_rate") else 1.0
        deltas[m] = sign * (a - b)
    if not deltas:
        return False, "no comparable metrics"
    # Must not regress on any.
    regressions = {k: v for k, v in deltas.items() if v < 0}
    if regressions:
        return False, f"regressed on: {regressions}"
    # Must improve >2pts on at least one (positive delta = improvement after
    # the per-metric sign correction above; abs() would mask near-zero deltas
    # that weren't strictly improvements).
    significant = [v for v in deltas.values() if v > 0.02]
    if not significant:
        max_delta = max(deltas.values()) if deltas else 0.0
        return False, f"no significant improvement (max delta {max_delta:.3f})"
    return True, f"improved on {len(significant)} metric(s)"


async def persist_candidate(
    session: AsyncSession,
    candidate: PromptCandidate,
    *,
    source: str = "meta_prompt_tuner_auto",
) -> UUID:
    """Insert into prompt_versions. Returns the new version UUID."""
    version_id = uuid4()
    await session.execute(
        text(
            """
            INSERT INTO prompt_versions
                (id, pass_index, scope, body, parent_id, created_at, source, rationale)
            VALUES
                (:id, :pi, :scope, :body, :pid, :created, :source, :rat)
            """
        ),
        {
            "id": str(version_id),
            "pi": candidate.pass_index,
            "scope": candidate.scope,
            "body": candidate.body,
            "pid": str(candidate.parent_id) if candidate.parent_id else None,
            "created": datetime.now(UTC),
            "source": source,
            "rat": candidate.rationale,
        },
    )
    return version_id


async def persist_eval(
    session: AsyncSession,
    *,
    prompt_version_id: UUID,
    devset_id: str,
    result: EvalResult,
) -> UUID:
    """Insert one row in prompt_evals."""
    eval_id = uuid4()
    await session.execute(
        text(
            """
            INSERT INTO prompt_evals
                (id, prompt_version_id, devset_id, approval_rate, faithfulness,
                 brier_proj, ece, hallucination_rate, ran_at, metrics_extra)
            VALUES
                (:id, :pvid, :devset, :ar, :fa, :bp, :ece, :hr, :ran, CAST(:extra AS jsonb))
            """
        ),
        {
            "id": str(eval_id),
            "pvid": str(prompt_version_id),
            "devset": devset_id,
            "ar": result.approval_rate,
            "fa": result.faithfulness,
            "bp": result.brier_proj,
            "ece": result.ece,
            "hr": result.hallucination_rate,
            "ran": datetime.now(UTC),
            "extra": json.dumps(result.extra),
        },
    )
    return eval_id


async def latest_baseline(
    session: AsyncSession, *, pass_index: int, scope: str
) -> tuple[UUID, EvalResult] | None:
    """Pull the most recent eval result for the active version of a (pass, scope)."""
    row = (
        (
            await session.execute(
                text(
                    """
            SELECT pe.prompt_version_id, pe.approval_rate, pe.faithfulness,
                   pe.brier_proj, pe.ece, pe.hallucination_rate, pe.metrics_extra
            FROM prompt_evals pe
            JOIN prompt_versions pv ON pv.id = pe.prompt_version_id
            WHERE pv.pass_index = :pi AND pv.scope = :scope
            ORDER BY pe.ran_at DESC
            LIMIT 1
            """
                ),
                {"pi": pass_index, "scope": scope},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    extra_raw = row.get("metrics_extra") or {}
    if isinstance(extra_raw, str):
        try:
            extra_raw = json.loads(extra_raw)
        except json.JSONDecodeError:
            extra_raw = {}
    return UUID(str(row["prompt_version_id"])), EvalResult(
        approval_rate=float(row["approval_rate"]) if row["approval_rate"] is not None else None,
        faithfulness=float(row["faithfulness"]) if row["faithfulness"] is not None else None,
        brier_proj=float(row["brier_proj"]) if row["brier_proj"] is not None else None,
        ece=float(row["ece"]) if row["ece"] is not None else None,
        hallucination_rate=(
            float(row["hallucination_rate"]) if row["hallucination_rate"] is not None else None
        ),
        extra=dict(extra_raw),
    )


async def detect_rollback(
    session: AsyncSession, *, pass_index: int, scope: str
) -> tuple[bool, str]:
    """Auto-rollback gate per AUTOEVO §3: if the current active version's
    Brier degraded by >+0.01 vs its predecessor over the last 7 days,
    flag rollback.

    Returns (should_rollback, reason).
    """
    rows = (
        (
            await session.execute(
                text(
                    """
            SELECT pv.id, pv.created_at, AVG(pe.brier_proj) AS avg_brier
            FROM prompt_versions pv
            JOIN prompt_evals pe ON pe.prompt_version_id = pv.id
            WHERE pv.pass_index = :pi AND pv.scope = :scope
              AND pe.ran_at >= :since
            GROUP BY pv.id, pv.created_at
            ORDER BY pv.created_at DESC
            LIMIT 2
            """
                ),
                {
                    "pi": pass_index,
                    "scope": scope,
                    "since": datetime.now(UTC) - timedelta(days=7),
                },
            )
        )
        .mappings()
        .all()
    )
    if len(rows) < 2:
        return False, "insufficient eval history"
    current = float(rows[0]["avg_brier"]) if rows[0]["avg_brier"] is not None else None
    prev = float(rows[1]["avg_brier"]) if rows[1]["avg_brier"] is not None else None
    if current is None or prev is None:
        return False, "missing brier values"
    delta = current - prev
    if delta > 0.01:
        return (
            True,
            f"Brier degraded by {delta:.4f} on 7d window (current={current:.4f}, prev={prev:.4f})",
        )
    return False, f"Brier delta {delta:.4f} within tolerance"


def save_dspy_program(program_obj: Any, *, log_dir: str, label: str) -> Path:
    """Save a DSPy compiled program to disk. Returns the artifact path.

    Convention: `{log_dir}/{label}-{ISO_DATE}.json` so artifacts are
    version-controlled and rollback is `Module.load(path)`.
    """
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    iso = datetime.now(UTC).date().isoformat()
    path = Path(log_dir) / f"{label}-{iso}.json"
    # The DSPy `Module.save()` is the canonical persistence — call it if
    # available, otherwise fall back to dataclass-style serialization.
    if hasattr(program_obj, "save"):
        program_obj.save(str(path))  # type: ignore[no-untyped-call]
    else:
        with path.open("w", encoding="utf-8") as f:
            json.dump({"repr": repr(program_obj), "saved_at": iso}, f)
    return path


def list_dspy_artifacts(log_dir: str) -> list[Path]:
    """List artifacts under log_dir, newest first."""
    p = Path(log_dir)
    if not p.exists():
        return []
    return sorted(p.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)


def reload_previous_artifact(log_dir: str, *, skip: int = 0) -> Path | None:
    """Pick the (skip+1)-th most-recent artifact for rollback. None if missing."""
    artifacts = list_dspy_artifacts(log_dir)
    return artifacts[skip] if len(artifacts) > skip else None
