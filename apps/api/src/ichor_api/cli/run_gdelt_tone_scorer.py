"""CLI runner for the local GDELT tone scorer (ADR-112).

WHY THIS EXISTS: the GDELT DOC 2.0 ArtList JSON feed carries NO per-article
tone field, so `collectors/gdelt.py` persisted its parser default 0.0 on
100% of rows (prod witness 2026-06-11: 13,607/13,607 over the full 8-day
retention). Every tone consumer was silently dead or fabricated:
`_section_geopolitics` "most-negative" ranking (suspended by the PR #230
column-vitality guard), the TARIFF_SHOCK alert (`avg_tone <= -1.5` can
never fire on a flat-zero column), and `/v1/geopolitics/heatmap` mean_tone.

This worker scores the tone LOCALLY (Voie D — no external API, no LLM
call), mirroring `run_news_tone_scorer`:

  1. Query gdelt_events where tone = 0.0 AND language = 'English'
     AND seendate >= cutoff (FinBERT-tone is an English financial-text
     model — non-English rows stay at honest neutral 0.0).
  2. Batch-score titles through FinBERT-tone (3-class softmax).
  3. tone = (p_positive - p_negative) * 10.0 — a continuous signed score
     mapped onto the GDELT-like -10..+10 scale the consumers were built
     for (TARIFF_SHOCK threshold avg_tone <= -1.5 ≙ FinBERT -0.15).
     A scored row is almost never exactly 0.0, so `tone = 0.0` keeps
     meaning "not scored / non-English / exactly balanced" and the
     re-scan window stays cheap.
  4. UPDATE per row on the (id, seendate) hypertable PK; exact-zero
     scores are skipped (no-op write avoided; re-scored next tick).

Cadence: every 15 min, window 6h (pattern run_news_tone_scorer — rows
older than the window are not retried forever). First prod run should
backfill with --max-age-hours 48 to revive the 24h consumers at once.

The PR #230 guard in `_section_geopolitics` auto-disarms as soon as real
negative tones enter its candidate pool — no consumer change needed.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy import text as sa_text

from ..db import get_engine, get_sessionmaker
from ..models import GdeltEvent

log = structlog.get_logger(__name__)

# Score in batches to amortize the model load (mirrors news scorer).
_BATCH_SIZE = 32

# Re-scan window: rows older than this stay as they are (a still-0.0 row
# after 6h is non-English-mislabeled, exactly balanced, or predates the
# scorer — the 24h consumers tolerate neutral zeros; do not retry forever).
_MAX_AGE_HOURS = 6

# Per-run cap to bound runtime (≈ one 48h English backfill in one run).
_MAX_ROWS_PER_RUN = 2500

# GDELT stores the long-form language name (prod witness: 'English').
_LANGUAGE_EN = "English"

# FinBERT signed score is in [-1, 1]; consumers (TARIFF_SHOCK threshold,
# heatmap bands, most-negative ranking) were built for the GDELT-like
# -10..+10 scale documented on models/gdelt_event.py.
_GDELT_SCALE = 10.0


def tone_from_distribution(distribution: dict[str, float]) -> float:
    """Continuous signed tone on the GDELT-like scale: (p_pos - p_neg) * 10.

    Richer than label±confidence: an ambivalent headline (p_pos 0.4 /
    p_neg 0.35) lands near 0 instead of inheriting the full confidence of
    whichever class barely won. Bounded in [-10, +10] by construction.
    """
    p_pos = float(distribution.get("positive", 0.0))
    p_neg = float(distribution.get("negative", 0.0))
    return (p_pos - p_neg) * _GDELT_SCALE


async def run(
    *,
    persist: bool,
    max_age_hours: int = _MAX_AGE_HOURS,
    max_rows: int = _MAX_ROWS_PER_RUN,
) -> int:
    sm = get_sessionmaker()
    cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)

    async with sm() as session:
        stmt = (
            select(GdeltEvent.id, GdeltEvent.seendate, GdeltEvent.title)
            .where(
                GdeltEvent.tone == 0.0,
                GdeltEvent.language == _LANGUAGE_EN,
                GdeltEvent.seendate >= cutoff,
            )
            .order_by(GdeltEvent.seendate.desc())
            .limit(max_rows)
        )
        rows = (await session.execute(stmt)).all()

    print(f"GDELT tone scorer · {len(rows)} unscored English rows in last {max_age_hours}h")

    if not rows:
        return 0

    # Lazy import — keeps the dry-run path fast (pattern news scorer).
    try:
        from ichor_ml.nlp.finbert_tone import score_tones_batch
    except ImportError as e:
        print(f"GDELT tone scorer · ichor_ml not importable : {e}", file=sys.stderr)
        return 1

    texts = [str(r.title)[:1000] for r in rows]
    try:
        scores = score_tones_batch(texts, batch_size=_BATCH_SIZE)
    except Exception as e:
        log.warning("gdelt_tone_scorer.batch_failed", error=str(e)[:300])
        return 1

    if not persist:
        for r, s in list(zip(rows, scores, strict=False))[:8]:
            tone = tone_from_distribution(s.distribution)
            print(f"  [tone {tone:+.2f} · {s.label:8s}] {str(r.title)[:80]!r}")
        return 0

    n_updated = 0
    n_zero_skipped = 0
    async with sm() as session:
        for (row_id, seendate, _title), score in zip(rows, scores, strict=False):
            tone = tone_from_distribution(score.distribution)
            if tone == 0.0:
                # Exactly balanced (rare float coincidence): writing 0.0
                # would be a no-op — skip; the row re-enters the next scan.
                n_zero_skipped += 1
                continue
            await session.execute(
                sa_text(
                    "UPDATE gdelt_events SET tone = :tone WHERE id = :id AND seendate = :seendate"
                ),
                {"tone": tone, "id": str(row_id), "seendate": seendate},
            )
            n_updated += 1
        await session.commit()
    print(f"GDELT tone scorer · updated {n_updated} rows (skipped exact-zero: {n_zero_skipped})")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_gdelt_tone_scorer")
    parser.add_argument("--persist", action="store_true")
    parser.add_argument("--max-age-hours", type=int, default=_MAX_AGE_HOURS)
    parser.add_argument("--max-rows", type=int, default=_MAX_ROWS_PER_RUN)
    args = parser.parse_args(argv[1:])
    try:
        return asyncio.run(
            run(persist=args.persist, max_age_hours=args.max_age_hours, max_rows=args.max_rows)
        )
    finally:
        if args.persist:
            asyncio.run(get_engine().dispose())


if __name__ == "__main__":
    sys.exit(main(sys.argv))
