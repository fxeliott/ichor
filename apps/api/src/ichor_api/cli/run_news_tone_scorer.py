"""CLI runner for the FinBERT-tone news scorer.

Wires news_items rows where tone_label IS NULL → packages/ml/nlp/finbert_tone
→ news_items.tone_label + tone_score (signed confidence).

This activates the upstream data flow for NEWS_NEGATIVE_BURST alert
(catalog metric='news_neg_5min', threshold 0.7 above) which scans
news_items.tone_label='negative' AND tone_score < -0.5 in 5-min
windows.

Algorithm :
  1. Query news_items where tone_label IS NULL AND fetched_at >= cutoff
  2. Batch-score titles + summaries through FinBERT-tone (financial
     sentiment 3-class : positive / neutral / negative)
  3. tone_score convention :
       label='positive' → +confidence (in [0, 1])
       label='neutral'  →  0
       label='negative' → -confidence (in [-1, 0])
  4. UPDATE news_items SET tone_label, tone_score per row.

Cadence : every 15 min — aligns with the 5-min news-burst window
plus FinBERT inference latency (a few seconds for a batch of 50).

The first run is heavy (model download ~400 MB). Subsequent runs
use the cached pipeline (lru_cache + Hugging Face cache on disk).
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
from ..models import NewsItem

log = structlog.get_logger(__name__)

# Score in batches to amortize the model load.
_BATCH_SIZE = 32

# Skip rows older than this — once tone_label is NULL after a while,
# the row probably failed scoring and we don't want to retry forever.
_MAX_AGE_HOURS = 6


def _signed_score(label: str, confidence: float) -> float:
    """Map FinBERT output to a signed [-1, 1] score per news_item.tone_score."""
    if label == "positive":
        return float(confidence)
    if label == "negative":
        return -float(confidence)
    return 0.0


async def run(*, persist: bool, max_age_hours: int = _MAX_AGE_HOURS) -> int:
    sm = get_sessionmaker()
    cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)

    async with sm() as session:
        stmt = (
            select(NewsItem.id, NewsItem.fetched_at, NewsItem.title, NewsItem.summary)
            .where(
                NewsItem.tone_label.is_(None),
                NewsItem.fetched_at >= cutoff,
            )
            .limit(500)  # cap per run to bound runtime
        )
        rows = (await session.execute(stmt)).all()

    print(f"News tone scorer · {len(rows)} unlabeled items in last {max_age_hours}h")

    if not rows:
        return 0

    # Lazy import — keeps the dry-run path fast.
    try:
        from ichor_ml.nlp.finbert_tone import score_tones_batch
    except ImportError as e:
        print(f"News tone scorer · ichor_ml not importable : {e}", file=sys.stderr)
        return 1

    # Build texts : prefer summary, fall back to title.
    texts = [(str(r.summary) if r.summary else str(r.title))[:1000] for r in rows]
    try:
        scores = score_tones_batch(texts, batch_size=_BATCH_SIZE)
    except Exception as e:
        log.warning("news_tone_scorer.batch_failed", error=str(e)[:300])
        return 1

    if not persist:
        # Dry-run : show 5 random examples
        for r, s in list(zip(rows, scores, strict=False))[:5]:
            print(f"  [{s.label:8s} conf={s.confidence:.2f}] {str(r.title)[:80]!r}")
        return 0

    n_updated = 0
    async with sm() as session:
        # One UPDATE per row — small batch (≤500), Postgres handles
        # this fine without a CTE bulk-update.
        for (row_id, fetched_at, _title, _summary), score in zip(
            rows, scores, strict=False
        ):
            tone_score = _signed_score(score.label, score.confidence)
            await session.execute(
                sa_text(
                    "UPDATE news_items SET tone_label = :label, tone_score = :score "
                    "WHERE id = :id AND fetched_at = :fetched_at"
                ),
                {
                    "label": score.label,
                    "score": tone_score,
                    "id": str(row_id),
                    "fetched_at": fetched_at,
                },
            )
            n_updated += 1
        await session.commit()
    print(f"News tone scorer · updated {n_updated} rows")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_news_tone_scorer")
    parser.add_argument("--persist", action="store_true")
    parser.add_argument("--max-age-hours", type=int, default=_MAX_AGE_HOURS)
    args = parser.parse_args(argv[1:])
    try:
        return asyncio.run(run(persist=args.persist, max_age_hours=args.max_age_hours))
    finally:
        if args.persist:
            asyncio.run(get_engine().dispose())


if __name__ == "__main__":
    sys.exit(main(sys.argv))
