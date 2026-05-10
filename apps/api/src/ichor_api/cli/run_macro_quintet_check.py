"""CLI: MACRO_QUINTET_STRESS alert runner. Daily 22:37 Paris."""

from __future__ import annotations

import argparse
import asyncio
import sys

from ..db import get_engine, get_sessionmaker
from ..services.macro_quintet_check import evaluate_macro_quintet


async def run(*, persist: bool = True) -> None:
    sm = get_sessionmaker()
    async with sm() as session:
        result = await evaluate_macro_quintet(session, persist=persist)
        print(f"macro_quintet · {result.note}")
        if persist:
            await session.commit()


async def _main(*, persist: bool) -> int:
    try:
        await run(persist=persist)
        return 0
    finally:
        await get_engine().dispose()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="MACRO_QUINTET_STRESS check")
    parser.add_argument(
        "--persist",
        dest="persist",
        action="store_true",
        help="Write to alerts table (default behavior)",
    )
    parser.add_argument(
        "--no-persist", dest="persist", action="store_false", help="Dry-run: don't write"
    )
    parser.set_defaults(persist=True)
    args = parser.parse_args(argv[1:])
    return asyncio.run(_main(persist=args.persist))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
