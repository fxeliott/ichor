"""CLI runner for the weekly post-mortem.

Wires the previously-DORMANT services/post_mortem.py into a cron
target. Runs Sundays 19:00 Paris (after the weekly briefing at 18:00),
covers the ISO week ending that Sunday, persists into post_mortems
table + writes the rendered markdown to /var/lib/ichor/post-mortems/.

8 sections per AUTOEVO §4 :
  1. Top hits (highest-conviction calls that landed)
  2. Top misses (highest-conviction calls that didn't)
  3. Calibration summary (Brier per regime/asset)
  4. Drift detected (ADWIN per asset)
  5. Recent narratives (cluster + intensity)
  6. Couche-2 outputs review
  7. Suggestions (config / prompt / weight changes)
  8. Stats footer

Usage:
    python -m ichor_api.cli.run_post_mortem            # dry-run
    python -m ichor_api.cli.run_post_mortem --persist
    python -m ichor_api.cli.run_post_mortem --persist --output-dir /var/lib/ichor/post-mortems
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import structlog

from ..db import get_engine, get_sessionmaker
from ..services.post_mortem import (
    build_post_mortem,
    persist_post_mortem,
    render_markdown,
)

log = structlog.get_logger(__name__)

DEFAULT_OUTPUT_DIR = "/var/lib/ichor/post-mortems"


async def run(*, persist: bool, output_dir: str) -> int:
    sm = get_sessionmaker()
    now = datetime.now(UTC)

    async with sm() as session:
        payload = await build_post_mortem(session, now=now)

    md = render_markdown(payload)
    print(
        f"Post-mortem · ISO {payload.iso_year}-W{payload.iso_week:02d}  "
        f"hits={len(payload.top_hits)} miss={len(payload.top_miss)} "
        f"drift={len(payload.drift_detected)} suggestions={len(payload.suggestions)}"
    )

    # File path : {output_dir}/{iso_year}-W{iso_week:02d}.md
    md_filename = f"{payload.iso_year}-W{payload.iso_week:02d}.md"
    md_full_path = str(Path(output_dir) / md_filename)

    if persist:
        try:
            os.makedirs(output_dir, exist_ok=True)
            with open(md_full_path, "w", encoding="utf-8") as f:
                f.write(md)
            print(f"Post-mortem · markdown written to {md_full_path}")
        except OSError as e:
            log.warning(
                "post_mortem.markdown_write_failed",
                path=md_full_path,
                error=str(e),
            )
            md_full_path = ""  # don't store an unwritten path

        async with sm() as session:
            await persist_post_mortem(session, payload, markdown_path=md_full_path)
            await session.commit()
        print("Post-mortem · persisted to post_mortems table")
    else:
        # Dry-run : print the first 800 chars so we can sanity-check
        print("\n--- Markdown preview (first 800 chars) ---")
        print(md[:800])

    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_post_mortem")
    parser.add_argument("--persist", action="store_true")
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Where to write the rendered markdown (default: {DEFAULT_OUTPUT_DIR})",
    )
    args = parser.parse_args(argv[1:])
    try:
        return asyncio.run(run(persist=args.persist, output_dir=args.output_dir))
    finally:
        if args.persist:
            asyncio.run(get_engine().dispose())


if __name__ == "__main__":
    sys.exit(main(sys.argv))
