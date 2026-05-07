"""Central-bank tone z-score wiring for FOMC_TONE_SHIFT + ECB_TONE_SHIFT.

Wires the previously DORMANT alerts :
  - `FOMC_TONE_SHIFT` (catalog metric `fomc_tone_z`, threshold ≥ 1.5)
  - `ECB_TONE_SHIFT` (catalog metric `ecb_tone_z`, threshold ≥ 1.5)

The pipeline :
  1. Pull recent CbSpeech rows for the target CB (last `lookback_hours`,
     default 24 h — long enough to catch a press conference + minutes
     window, short enough to stay reactive).
  2. Score each speech with FOMC-Roberta (gtfintechlab) — 3-class
     HAWKISH/DOVISH/NEUTRAL with softmax. The model is FED-trained
     but transfers cleanly to ECB / BoE / BoJ vocabulary (standard
     transfer learning practice on CB rhetoric ; the underlying
     hawkish/dovish dictionary is shared across G7 CBs).
  3. Aggregate to a single `net_hawkish ∈ [-1, +1]` (mean across
     speeches and chunks).
  4. Persist into `fred_observations` with `series_id = "{cb}_TONE_NET"`.
  5. Compute the rolling z-score over the last 90 days, excluding
     today's value.
  6. Fire `{cb_lower}_tone_z` against the catalog. A 1.5-sigma move
     reflects a meaningful regime shift in CB rhetoric.

Pure module : no LLM call, no network. The FOMC-Roberta scorer is
lazy-imported inside `evaluate_cb_tone` so unit tests can mock it
without paying the 1.4 GB download cost.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import CbSpeech, FredObservation
from .alerts_runner import check_metric

# Map catalog metric → CB code in cb_speeches.central_bank.
# Note : the collector stores mixed-case values (`'Fed'`, `'BoE'`,
# `'BoJ'`, `'ECB'`) but this map uses upper-case keys for case-stable
# CLI args. The DB query uses `func.upper()` for case-insensitive
# matching (see _read_recent_speeches) so collector storage variation
# is transparent.
CB_TO_METRIC: dict[str, str] = {
    "FED": "fomc_tone_z",
    "ECB": "ecb_tone_z",
    "BOE": "boe_tone_z",
    "BOJ": "boj_tone_z",
}

_MIN_HISTORY = 30  # ≥ 30 d before z is statistically meaningful
_LOOKBACK_DAYS = 90


@dataclass(frozen=True)
class CbToneResult:
    cb: str
    series_id: str
    n_speeches: int
    net_hawkish: float | None
    """Mean net hawkish ∈ [-1, +1] across all chunks of all speeches.
    None when no speech in the lookback window."""

    n_history: int
    z_score: float | None
    note: str = ""


def _zscore(values: list[float], current: float) -> float | None:
    n = len(values)
    if n < _MIN_HISTORY:
        return None
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / n
    std = math.sqrt(var)
    if std == 0:
        return None
    return (current - mean) / std


async def _read_recent_speeches(
    session: AsyncSession, *, cb: str, lookback_hours: int
) -> list[CbSpeech]:
    """Case-insensitive read of recent speeches for a CB code.

    The collector stores mixed-case values (`'Fed'`, `'BoE'`, `'BoJ'`,
    `'ECB'`) but service callers pass upper-case (`'FED'`, `'BOE'`,
    `'BOJ'`, `'ECB'`). We normalize on read with `func.upper()` so the
    query is robust to collector schema drift.

    Pre-2026-05-07 fix : the query used `==` directly which caused a
    silent zero-row return when collector vs caller case mismatched
    (FOMC_TONE_SHIFT was firing 'no FED speech' for weeks despite
    actual data in DB). Hotfix in PR #32 (Phase D.5.d).
    """
    cutoff = datetime.now(UTC) - timedelta(hours=lookback_hours)
    cb_upper = cb.upper()
    rows = (
        await session.execute(
            select(CbSpeech)
            .where(
                func.upper(CbSpeech.central_bank) == cb_upper,
                CbSpeech.published_at >= cutoff,
            )
            .order_by(desc(CbSpeech.published_at))
        )
    ).scalars().all()
    return list(rows)


async def _persist_tone(
    session: AsyncSession, *, series_id: str, value: float
) -> None:
    """Idempotent insert keyed on (series_id, observation_date).
    Same pattern as risk_reversal_check : update-in-place when the
    runner is invoked twice in the same day."""
    today = datetime.now(UTC).date()
    existing = await session.execute(
        select(FredObservation.id)
        .where(
            FredObservation.series_id == series_id,
            FredObservation.observation_date == today,
        )
        .limit(1)
    )
    if existing.scalar_one_or_none() is not None:
        from sqlalchemy import update

        await session.execute(
            update(FredObservation)
            .where(
                FredObservation.series_id == series_id,
                FredObservation.observation_date == today,
            )
            .values(value=value, fetched_at=datetime.now(UTC))
        )
        return
    now = datetime.now(UTC)
    session.add(
        FredObservation(
            id=uuid4(),
            created_at=now,
            series_id=series_id,
            observation_date=today,
            value=value,
            fetched_at=now,
        )
    )


async def _read_history(
    session: AsyncSession, *, series_id: str
) -> list[float]:
    cutoff = datetime.now(UTC).date() - timedelta(days=_LOOKBACK_DAYS)
    rows = (
        await session.execute(
            select(FredObservation.value)
            .where(
                FredObservation.series_id == series_id,
                FredObservation.observation_date >= cutoff,
                FredObservation.value.is_not(None),
            )
            .order_by(FredObservation.observation_date.asc())
        )
    ).all()
    return [float(r[0]) for r in rows]


async def evaluate_cb_tone(
    session: AsyncSession,
    *,
    cb: str,
    lookback_hours: int = 24,
    scorer: Callable[[str], float] | None = None,
    persist: bool = True,
) -> CbToneResult:
    """Score recent speeches for `cb`, persist net_hawkish, fire alert.

    Args:
        cb: 'FED' | 'ECB'. Other CB codes are accepted but won't
            map to a catalog metric (just persist + skip alert).
        lookback_hours: how far back to look for new speeches.
        scorer: optional injection for testing — `(text) -> float
            in [-1, +1]`. When None, lazy-loads FOMC-Roberta and
            uses `aggregate_fomc_chunks(score_long_fomc_text(text))`.
        persist: dry-run when False.
    """
    cb_norm = cb.upper()
    series_id = f"{cb_norm}_TONE_NET"

    speeches = await _read_recent_speeches(
        session, cb=cb_norm, lookback_hours=lookback_hours
    )
    if not speeches:
        return CbToneResult(
            cb=cb_norm,
            series_id=series_id,
            n_speeches=0,
            net_hawkish=None,
            n_history=0,
            z_score=None,
            note=f"no {cb_norm} speech in last {lookback_hours} h",
        )

    if scorer is None:
        # Lazy-import the model wrapper. This is the only place the
        # ML stack is touched at runtime ; tests pass a mock scorer.
        from ichor_ml.nlp.fomc_roberta import (
            aggregate_fomc_chunks,
            score_long_fomc_text,
        )

        def scorer(text: str) -> float:  # noqa: PLR0912
            scores = score_long_fomc_text(text)
            return float(aggregate_fomc_chunks(scores)["net_hawkish"])

    # Pick the most informative text per speech : prefer summary,
    # fall back to title. The collector pulls summaries when feeds
    # carry them ; titles are the lowest-bound fallback.
    texts = [(s.summary or s.title or "").strip() for s in speeches]
    texts = [t for t in texts if t]
    if not texts:
        return CbToneResult(
            cb=cb_norm,
            series_id=series_id,
            n_speeches=len(speeches),
            net_hawkish=None,
            n_history=0,
            z_score=None,
            note=f"{cb_norm}: {len(speeches)} speeches but no usable text",
        )

    per_text_scores = [scorer(t) for t in texts]
    net_hawkish = sum(per_text_scores) / len(per_text_scores)

    if persist:
        await _persist_tone(session, series_id=series_id, value=net_hawkish)
        await session.flush()

    history = await _read_history(session, series_id=series_id)
    history_excl_today = history[:-1] if len(history) >= 1 else []
    z = _zscore(history_excl_today, net_hawkish)

    note = (
        f"{cb_norm}: {len(speeches)} speeches → net_hawkish={net_hawkish:+.3f} "
        f"({len(history_excl_today)} d hist, z={z:+.2f})"
        if z is not None
        else f"{cb_norm}: net_hawkish={net_hawkish:+.3f} "
        f"(insufficient history {len(history_excl_today)} d)"
    )

    if z is not None and persist and cb_norm in CB_TO_METRIC:
        await check_metric(
            session,
            metric_name=CB_TO_METRIC[cb_norm],
            current_value=z,
            extra_payload={
                "net_hawkish": net_hawkish,
                "n_speeches": len(speeches),
                "n_history": len(history_excl_today),
            },
        )

    return CbToneResult(
        cb=cb_norm,
        series_id=series_id,
        n_speeches=len(speeches),
        net_hawkish=net_hawkish,
        n_history=len(history_excl_today),
        z_score=z,
        note=note,
    )
