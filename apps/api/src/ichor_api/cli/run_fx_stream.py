"""systemd entry-point for the Polygon FX WebSocket subscriber.

Run :
    python -m ichor_api.cli.run_fx_stream

Reads `ICHOR_API_POLYGON_API_KEY` and (optional)
`ICHOR_API_POLYGON_FX_PAIRS` (comma-separated) from the environment,
opens a single WebSocket to `wss://socket.polygon.io/forex`, and
streams quote ticks into the `fx_ticks` hypertable. Auto-reconnects on
disconnect with exponential backoff.

Designed to live in systemd as a `Type=simple` service (NOT a oneshot
timer) — the connection is held open continuously. See
`scripts/hetzner/register-fx-stream.sh` for the unit template.
"""

from __future__ import annotations

import asyncio
import sys

from ..collectors.polygon_fx_stream import _main


def main() -> int:
    return asyncio.run(_main())


if __name__ == "__main__":
    sys.exit(main())
