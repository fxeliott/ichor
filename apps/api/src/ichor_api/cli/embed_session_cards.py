"""Bulk-embed historical `session_card_audit` rows into `rag_chunks_index`.

W110c — ADR-086 Phase C ingestion runner. Renders each session card to a
compact text representation, embeds it via `services.rag_embeddings.embed_text`
(bge-small-en-v1.5 ONNX CPU, Voie D Invariant 2), and inserts a single
`rag_chunks_index` row per card (whole-card granularity ; per-Pass
sub-chunking deferred to W120).

Idempotent : a card is skipped if a chunk already exists with the same
`(source_type='session_card', source_id=card.id)` pair. Re-running the
job is safe — only NEW cards get embedded.

Usage examples
==============

  # Embed all eligible cards (no time filter), commit in batches of 50
  python -m ichor_api.cli.embed_session_cards

  # Embed only cards generated since 2026-01-01
  python -m ichor_api.cli.embed_session_cards --since 2026-01-01

  # Embed only EUR_USD, max 500 cards, dry-run preview
  python -m ichor_api.cli.embed_session_cards --asset EUR_USD --limit 500 --dry-run

  # Tighter batch (smaller commit windows = lower memory ; useful on Win11)
  python -m ichor_api.cli.embed_session_cards --batch-size 20

Run on Hetzner via :

  cd /opt/ichor/api && .venv/bin/python -m ichor_api.cli.embed_session_cards \\
      --since 2024-01-01 --batch-size 100

ADR-086 invariants preserved by construction :
  * Past-only retrieval at the *service* layer — this runner is a writer,
    so the embargo applies only when `retrieve_analogues()` queries back.
  * Voie D — `embed_text()` loads a self-hosted ONNX model, no paid API.
  * Cap5 exclusion — `rag_chunks_index` is NOT in
    `services.tool_query_db.ALLOWED_TABLES` (W83 CI guard).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_engine, get_sessionmaker
from ..models.session_card_audit import SessionCardAudit
from ..services.rag_embeddings import (
    EMBEDDING_DIM,
    _format_vector_for_pgvector,
    embed_text,
)

log = structlog.get_logger(__name__)

# Per-batch commit window. 50 is a reasonable default :
#   * each embed takes ~30-50ms CPU on Hetzner per round-10 web review
#   * one whole-card chunk is ~2-4 KB on average
#   * 50 rows × ~3 KB = ~150 KB per transaction
_DEFAULT_BATCH_SIZE = 50

# Hard cap : embedding cost is linear in card count. 50k is a sanity check
# on accidental missing filters, not a hard product requirement.
_DEFAULT_LIMIT = 100_000


def _render_card_content(card: SessionCardAudit) -> str:
    """Render a session-card row to the compact text form that will be
    embedded.

    The format is intentionally descriptive (past state + outcome),
    never prescriptive (no BUY/SELL phrasing). It mirrors the
    information set a discretionary trader would skim when looking
    for past analogues.

    Structure (one paragraph per logical group, double-newline
    separators preserve embedding semantic locality) :

      asset / session / generated_at / regime
      bias_direction + conviction + magnitude range
      mechanisms (top-3 from JSONB)
      invalidations (top-3 from JSONB)
      catalysts (top-3 from JSONB)
      Pass-6 scenarios — buckets with p>0
    """
    parts: list[str] = []

    header = (
        f"asset={card.asset}  session={card.session_type}  "
        f"date={card.generated_at.date().isoformat()}  "
        f"regime={card.regime_quadrant or 'unknown'}"
    )
    parts.append(header)

    mag = ""
    if card.magnitude_pips_low is not None and card.magnitude_pips_high is not None:
        mag = f" magnitude_pips=[{card.magnitude_pips_low:.0f},{card.magnitude_pips_high:.0f}]"
    bias = f"bias={card.bias_direction}  conviction={card.conviction_pct:.0f}%{mag}"
    parts.append(bias)

    mech_lines = _render_jsonb_list("Mechanisms", card.mechanisms, max_items=3)
    if mech_lines:
        parts.append(mech_lines)

    inv_lines = _render_jsonb_list("Invalidations", card.invalidations, max_items=3)
    if inv_lines:
        parts.append(inv_lines)

    cat_lines = _render_jsonb_list("Catalysts", card.catalysts, max_items=3)
    if cat_lines:
        parts.append(cat_lines)

    scen_lines = _render_scenarios(card.scenarios)
    if scen_lines:
        parts.append(scen_lines)

    return "\n\n".join(parts)


def _render_jsonb_list(label: str, raw: Any, *, max_items: int) -> str:
    """Render a JSONB list as a labelled bullet block.

    Accepts the variations we have in the wild :
      * list[str]            → bullets are the strings themselves
      * list[dict[...]]      → tries common keys (`description`, `text`,
                               `name`, `mechanism`) ; falls back to repr
      * None / [] / non-list → returns empty string
    """
    if not raw or not isinstance(raw, list):
        return ""
    out: list[str] = []
    for item in raw[:max_items]:
        if isinstance(item, str):
            text_val = item
        elif isinstance(item, dict):
            text_val = (
                item.get("description")
                or item.get("text")
                or item.get("name")
                or item.get("mechanism")
                or str(item)
            )
        else:
            text_val = str(item)
        text_val = text_val.replace("\n", " ").strip()
        if text_val:
            out.append(f"  - {text_val}")
    if not out:
        return ""
    return f"{label}:\n" + "\n".join(out)


def _render_scenarios(raw: Any) -> str:
    """Render Pass-6 scenarios JSONB list (W105a/c ADR-085) as a block.

    Shape :
        [{"label": str, "p": float, "magnitude_pips": [low, high],
          "mechanism": str}, ...]
    """
    if not raw or not isinstance(raw, list):
        return ""
    rows: list[str] = []
    for s in raw:
        if not isinstance(s, dict):
            continue
        p = s.get("p")
        label = s.get("label")
        if not isinstance(p, int | float) or not isinstance(label, str):
            continue
        if p <= 0:
            continue  # buckets with zero probability are noise
        mag = s.get("magnitude_pips") or [None, None]
        mag_str = ""
        if isinstance(mag, list) and len(mag) == 2 and all(isinstance(v, int | float) for v in mag):
            mag_str = f"  [{mag[0]:.0f},{mag[1]:.0f}]"
        rows.append(f"  - {label:12s} p={p:.2f}{mag_str}")
    if not rows:
        return ""
    return "Scenarios (Pass-6, 7-bucket):\n" + "\n".join(rows)


async def _existing_chunk_ids(session: AsyncSession, source_ids: Iterable[UUID]) -> set[UUID]:
    """Return the subset of `source_ids` already present in
    `rag_chunks_index` for source_type='session_card'."""
    ids_list = list(source_ids)
    if not ids_list:
        return set()
    rows = await session.execute(
        text(
            "SELECT source_id FROM rag_chunks_index "
            "WHERE source_type = 'session_card' AND source_id = ANY(:ids)"
        ),
        {"ids": ids_list},
    )
    return {r[0] for r in rows.all()}


async def _insert_chunk(
    session: AsyncSession, *, card: SessionCardAudit, content: str, embedding: list[float]
) -> None:
    """Insert a single rag_chunks_index row using raw SQL because
    `embedding vector(384)` is not mapped in the ORM (see
    models/rag_chunk_index.py docstring)."""
    if len(embedding) != EMBEDDING_DIM:
        raise ValueError(
            f"embedding has {len(embedding)} dims, expected {EMBEDDING_DIM} "
            "(bge-small-en-v1.5 mismatch)"
        )
    await session.execute(
        text(
            """
            INSERT INTO rag_chunks_index (
                source_type, source_id, asset, regime, section,
                content, embedding, metadata, created_at, indexed_at
            ) VALUES (
                'session_card', :source_id, :asset, :regime, NULL,
                :content, CAST(:embedding AS vector),
                CAST(:metadata AS jsonb),
                :created_at, now()
            )
            """
        ),
        {
            "source_id": card.id,
            "asset": card.asset,
            "regime": card.regime_quadrant,
            "content": content,
            "embedding": _format_vector_for_pgvector(embedding),
            "metadata": _metadata_json(card),
            # `generated_at` is the time the chunk content REPRESENTS —
            # the embargo key (ADR-086 Invariant 1).
            "created_at": card.generated_at,
        },
    )


def _metadata_json(card: SessionCardAudit) -> str:
    """Minimal metadata for retrieval-time filtering (no PII)."""
    import json

    payload = {
        "session_type": card.session_type,
        "bias_direction": card.bias_direction,
        "conviction_pct": card.conviction_pct,
        "model_id": card.model_id,
    }
    return json.dumps(payload, sort_keys=True)


async def _select_cards(
    session: AsyncSession,
    *,
    since: datetime | None,
    asset: str | None,
    limit: int,
) -> list[SessionCardAudit]:
    """Pull eligible session_card_audit rows in ascending generated_at."""
    stmt = select(SessionCardAudit).order_by(SessionCardAudit.generated_at.asc()).limit(limit)
    if since is not None:
        stmt = stmt.where(SessionCardAudit.generated_at >= since)
    if asset is not None:
        stmt = stmt.where(SessionCardAudit.asset == asset.upper())
    rows = await session.execute(stmt)
    return list(rows.scalars().all())


async def _run(
    *,
    since: datetime | None,
    asset: str | None,
    limit: int,
    batch_size: int,
    dry_run: bool,
) -> int:
    sm = get_sessionmaker()
    n_seen = 0
    n_skipped_existing = 0
    n_skipped_empty = 0
    n_embedded = 0
    n_errors = 0

    async with sm() as session:
        cards = await _select_cards(session, since=since, asset=asset, limit=limit)
        n_seen = len(cards)
        if not cards:
            print("No eligible session_card_audit rows for the given filters.")
            return 0

        existing = await _existing_chunk_ids(session, [c.id for c in cards])
        to_process = [c for c in cards if c.id not in existing]
        n_skipped_existing = n_seen - len(to_process)

        print(
            f"Eligible cards: {n_seen}  "
            f"already embedded: {n_skipped_existing}  "
            f"new: {len(to_process)}  "
            f"batch_size: {batch_size}  "
            f"dry_run: {dry_run}"
        )

        for i, card in enumerate(to_process, start=1):
            content = _render_card_content(card)
            if not content.strip():
                n_skipped_empty += 1
                continue
            if dry_run:
                if i <= 3:  # preview first 3 only
                    print(
                        f"\n--- preview {i} : "
                        f"{card.asset} {card.session_type} "
                        f"{card.generated_at.date().isoformat()} ---\n"
                        f"{content[:600]}{'…' if len(content) > 600 else ''}"
                    )
                n_embedded += 1
                continue
            try:
                vec = embed_text(content)
                await _insert_chunk(session, card=card, content=content, embedding=vec)
                n_embedded += 1
            except Exception as e:  # noqa: BLE001 — per-card resilience
                n_errors += 1
                log.warning(
                    "embed_session_cards.row_failed",
                    card_id=str(card.id),
                    asset=card.asset,
                    generated_at=card.generated_at.isoformat(),
                    error=str(e),
                )
                print(
                    f"  ! row {i} failed ({card.asset} "
                    f"{card.generated_at.date().isoformat()}): {e}",
                    file=sys.stderr,
                )

            if n_embedded % batch_size == 0:
                await session.commit()
                print(
                    f"  committed batch — running totals : embedded={n_embedded}  errors={n_errors}"
                )

        if not dry_run:
            await session.commit()

    print(
        f"\nDone. seen={n_seen}  already_embedded={n_skipped_existing}  "
        f"empty={n_skipped_empty}  embedded={n_embedded}  errors={n_errors}"
        + ("  (DRY-RUN)" if dry_run else "")
    )
    return 0 if n_errors == 0 else 1


def _parse_date(raw: str) -> datetime:
    """Accept YYYY-MM-DD ; force UTC midnight."""
    try:
        d = datetime.fromisoformat(raw)
    except ValueError as e:
        raise argparse.ArgumentTypeError(
            f"--since must be ISO date (YYYY-MM-DD) — got {raw!r}"
        ) from e
    if d.tzinfo is None:
        d = d.replace(tzinfo=UTC)
    return d


async def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="embed_session_cards",
        description=(
            "Bulk-embed historical session_card_audit rows into "
            "rag_chunks_index (W110c ADR-086 Phase C). Idempotent."
        ),
    )
    parser.add_argument(
        "--since",
        type=_parse_date,
        default=None,
        help="ISO date (YYYY-MM-DD) — only embed cards with generated_at >= since.",
    )
    parser.add_argument(
        "--asset",
        type=str,
        default=None,
        help="Restrict to one asset (e.g. EUR_USD). Case-insensitive.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=_DEFAULT_LIMIT,
        help=f"Max cards to scan (default {_DEFAULT_LIMIT}).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=_DEFAULT_BATCH_SIZE,
        help=f"Commit window in rows (default {_DEFAULT_BATCH_SIZE}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview rendering for the first 3 cards ; no DB writes.",
    )
    args = parser.parse_args(argv)
    if args.batch_size < 1:
        parser.error("--batch-size must be >= 1")
    if args.limit < 1:
        parser.error("--limit must be >= 1")

    try:
        return await _run(
            since=args.since,
            asset=args.asset,
            limit=args.limit,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
        )
    finally:
        await get_engine().dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
