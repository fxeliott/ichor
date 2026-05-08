"""CLI: TERM_PREMIUM_INTRADAY_30D alert runner. Daily 22:25 Paris."""

from __future__ import annotations

import argparse
import asyncio
import sys

from ..db import get_engine, get_sessionmaker
from ..services.term_premium_intraday_check import evaluate_term_premium_intraday


async def run(*, persist: bool = True) -> None:
    sm = get_sessionmaker()
    async with sm() as session:
        result = await evaluate_term_premium_intraday(session, persist=persist)
        print(result.note)
        if persist:
            await session.commit()


async def _main(*, persist: bool) -> int:
    try:
        await run(persist=persist)
        return 0
    finally:
        await get_engine().dispose()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="TERM_PREMIUM_INTRADAY_30D check")
    parser.add_argument("--persist", dest="persist", action="store_true", help="Write to alerts table (default)")
    parser.add_argument("--no-persist", dest="persist", action="store_false", help="Dry-run")
    parser.set_defaults(persist=True)
    args = parser.parse_args(argv[1:])
    return asyncio.run(_main(persist=args.persist))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
