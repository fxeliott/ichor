"""One-shot smoke for the rich context builder.

Run on Hetzner :
  sudo -u ichor bash -c '
    cd /opt/ichor/api/src && \
    source /opt/ichor/api/.venv/bin/activate && \
    set -a && source /etc/ichor/api.env && set +a && \
    python /tmp/smoke_rich_context.py
  '

Prints chars + token estimate + first 1500 chars of the assembled context.
Does NOT call Claude. Read-only DB query.
"""

from __future__ import annotations

import asyncio

from ichor_api.briefing.context_builder import build_rich_context
from ichor_api.db import get_engine, get_sessionmaker


async def main() -> None:
    sm = get_sessionmaker()
    async with sm() as session:
        md, tok = await build_rich_context(
            session,
            "pre_londres",
            ["EUR_USD", "XAU_USD", "NAS100_USD", "USD_JPY", "SPX500_USD"],
        )
    print(f"CHARS={len(md)}  TOKENS_EST={tok}")
    print("=" * 80)
    print(md[:2000])
    print("=" * 80)
    print("[truncated]" if len(md) > 2000 else "[full above]")
    await get_engine().dispose()


if __name__ == "__main__":
    asyncio.run(main())
