"""CLI: HY_IG_SPREAD_DIVERGENCE alert runner.

Daily 22:48 Paris (after MACRO_QUARTET 22:35, before VIX_TERM 22:45).
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from ..db import get_engine, get_sessionmaker
from ..services.hy_ig_spread_check import evaluate_hy_ig_spread_divergence


async def run(*, persist: bool = True) -> None:
    sm = get_sessionmaker()
    async with sm() as session:
        result = await evaluate_hy_ig_spread_divergence(session, persist=persist)
        print(f"hy_ig_spread · {result.note}")
        if persist:
            await session.commit()


async def _main(*, persist: bool) -> int:
    try:
        await run(persist=persist)
        return 0
    finally:
        # Event-loop-fix asyncio dispose (cf ADR-024)
        await get_engine().dispose()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="HY_IG_SPREAD_DIVERGENCE check")
    parser.add_argument(
        "--no-persist",
        dest="persist",
        action="store_false",
        help="Dry-run: don't write to alerts table",
    )
    parser.set_defaults(persist=True)
    args = parser.parse_args(argv[1:])
    return asyncio.run(_main(persist=args.persist))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
