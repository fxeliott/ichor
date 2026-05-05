"""Polygon Forex WebSocket subscriber — quote ticks for VPIN microstructure.

Streams the `wss://socket.polygon.io/forex` cluster's Quote channel for
the 6 tracked pairs (EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CAD,
XAU/USD) and persists each update into the `fx_ticks` hypertable. Runs
as a long-running systemd service (NOT a cron job — the connection is
held open with auto-reconnect).

Wire format expected per Polygon docs (subject to upstream change ; the
parser is defensive and skips malformed messages with a warning) :

    Auth   : {"action":"auth","params":"<API_KEY>"}
    Sub    : {"action":"subscribe","params":"C.EUR/USD,C.GBP/USD,..."}

    Quote  : [{"ev":"C","p":"EUR/USD","x":4,"b":1.0995,"a":1.0997,"t":1717113600000}, ...]

Each `C` event becomes one `fx_ticks` row. Mid is precomputed as
(bid + ask) / 2.

Backpressure : messages are batched (default 200 rows or 2 s window) and
flushed in one INSERT to avoid per-tick round-trips. On disconnect, a
truncated batch is flushed before reconnecting.

Resilience :
  - exponential backoff (max 60 s) on connection failures
  - per-message try/except : a single corrupt frame does not kill the
    subscriber
  - SIGTERM handled : final batch flushed cleanly before exit

ADR-022 boundary : ticks feed VPIN feature only (probability output).
Never order generation, never P&L, never broker integration.

Usage :
  python -m ichor_api.cli.run_fx_stream     # systemd ExecStart
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

import structlog

try:
    import websockets
    from websockets.exceptions import ConnectionClosed, WebSocketException
except ImportError as exc:  # pragma: no cover — websockets is a hard dep
    raise ImportError(
        "polygon_fx_stream requires `websockets>=14.0`. "
        "Add it to apps/api/pyproject.toml dependencies."
    ) from exc

POLYGON_FOREX_WS_URL = "wss://socket.polygon.io/forex"

# 6 tracked pairs from ADR-017. Polygon FX ticker uses slash format.
DEFAULT_PAIRS: tuple[str, ...] = (
    "EUR/USD",
    "GBP/USD",
    "USD/JPY",
    "AUD/USD",
    "USD/CAD",
    "XAU/USD",
)


log = structlog.get_logger(__name__)


@dataclass
class FxTickEvent:
    """Normalized quote tick parsed from a Polygon `C` event."""

    ts: datetime
    asset: str
    ticker: str
    bid: float
    ask: float
    mid: float
    bid_size: float | None = None
    ask_size: float | None = None
    exchange_id: int | None = None


@dataclass
class StreamStats:
    """Lightweight in-memory counters for /healthz/detailed surfacing."""

    connected_at: datetime | None = None
    n_ticks_total: int = 0
    n_ticks_persisted: int = 0
    n_messages_skipped: int = 0
    last_tick_at: datetime | None = None
    last_error: str | None = None
    pairs_subscribed: tuple[str, ...] = ()
    reconnects: int = 0


@dataclass
class _Batch:
    """Accumulator for batched inserts (back-pressure on the DB)."""

    events: list[FxTickEvent] = field(default_factory=list)
    flush_at: datetime | None = None


# ── Asset code derivation ────────────────────────────────────────────


def _ticker_to_asset(pair: str) -> str:
    """Map Polygon pair "EUR/USD" → asset code "EURUSD" (DB column convention)."""
    return pair.replace("/", "")


# ── Message parsing (defensive) ──────────────────────────────────────


def parse_quote_message(msg: object) -> FxTickEvent | None:
    """Parse a single Polygon C-event dict into FxTickEvent.

    Returns None for malformed / non-quote messages. Defensive : tolerates
    missing fields by skipping the message rather than raising — Polygon
    sometimes emits status / heartbeat frames mixed with C events.
    """
    if not isinstance(msg, dict):
        return None
    if msg.get("ev") != "C":
        return None
    pair = msg.get("p")
    bid = msg.get("b")
    ask = msg.get("a")
    ts_ms = msg.get("t")
    if not isinstance(pair, str) or not pair:
        return None
    if not isinstance(bid, (int, float)) or not isinstance(ask, (int, float)):
        return None
    if not isinstance(ts_ms, (int, float)) or ts_ms <= 0:
        return None
    if bid <= 0 or ask <= 0:
        return None
    mid = (float(bid) + float(ask)) / 2.0
    # Exchange ID per Polygon docs is sometimes a string ("44") and
    # sometimes an int (44). Coerce defensively to int when possible,
    # else None (column is nullable).
    raw_x = msg.get("x")
    exchange_id: int | None = None
    if isinstance(raw_x, (int, float)):
        exchange_id = int(raw_x)
    elif isinstance(raw_x, str) and raw_x.lstrip("-").isdigit():
        exchange_id = int(raw_x)

    return FxTickEvent(
        ts=datetime.fromtimestamp(ts_ms / 1000.0, tz=UTC),
        asset=_ticker_to_asset(pair),
        ticker=f"C:{pair}",
        bid=float(bid),
        ask=float(ask),
        mid=mid,
        bid_size=float(msg["bs"]) if isinstance(msg.get("bs"), (int, float)) else None,
        ask_size=float(msg["as"]) if isinstance(msg.get("as"), (int, float)) else None,
        exchange_id=exchange_id,
    )


def parse_frame(frame: str) -> list[FxTickEvent]:
    """Parse a raw WebSocket frame ; returns the list of valid quote events."""
    try:
        payload = json.loads(frame)
    except json.JSONDecodeError:
        return []
    items: Iterable[object] = payload if isinstance(payload, list) else [payload]
    out: list[FxTickEvent] = []
    for item in items:
        ev = parse_quote_message(item)
        if ev is not None:
            out.append(ev)
    return out


# ── Persistence (batched) ────────────────────────────────────────────


async def persist_batch(
    session_factory,  # type: ignore[no-untyped-def]
    events: list[FxTickEvent],
) -> int:
    """Bulk-insert a batch into fx_ticks. Returns rows written.

    Idempotency : ticks have no natural unique key (millisecond timestamps
    can collide across exchanges), so we simply insert with a fresh UUID
    per row. Rare duplicates from upstream re-broadcast are absorbed as
    near-zero noise in the VPIN aggregation.
    """
    if not events:
        return 0
    from ..models import FxTick

    now = datetime.now(UTC)
    rows = [
        FxTick(
            id=uuid4(),
            ts=ev.ts,
            created_at=now,
            asset=ev.asset,
            ticker=ev.ticker,
            bid=ev.bid,
            ask=ev.ask,
            mid=ev.mid,
            bid_size=ev.bid_size,
            ask_size=ev.ask_size,
            exchange_id=ev.exchange_id,
        )
        for ev in events
    ]
    async with session_factory() as session:
        session.add_all(rows)
        await session.commit()
    return len(rows)


# ── Stream loop ──────────────────────────────────────────────────────


async def stream_forever(
    api_key: str,
    pairs: tuple[str, ...] = DEFAULT_PAIRS,
    *,
    session_factory=None,  # type: ignore[no-untyped-def]
    batch_size: int = 200,
    batch_window_ms: int = 2000,
    initial_backoff_s: float = 1.0,
    max_backoff_s: float = 60.0,
    stop_event: asyncio.Event | None = None,
    stats: StreamStats | None = None,
) -> None:
    """Run the FX quote subscriber forever (with reconnect).

    Args:
        api_key: Polygon Massive Currencies key.
        pairs: ticker pairs to subscribe to.
        session_factory: async sessionmaker for DB inserts. If None, a
            singleton is fetched lazily via `db.get_sessionmaker`.
        batch_size: flush after this many ticks accumulate.
        batch_window_ms: flush after this many ms even if batch not full.
        initial_backoff_s / max_backoff_s: exponential reconnect backoff.
        stop_event: optional asyncio.Event ; set it to request graceful exit.
        stats: optional StreamStats — populated in place for /healthz.
    """
    if session_factory is None:
        from ..db import get_sessionmaker

        session_factory = get_sessionmaker()
    if stats is None:
        stats = StreamStats()
    stats.pairs_subscribed = tuple(pairs)

    backoff = initial_backoff_s
    sub_params = ",".join(f"C.{p}" for p in pairs)

    while True:
        if stop_event is not None and stop_event.is_set():
            log.info("polygon_fx_stream.stop_requested")
            return
        try:
            async with websockets.connect(
                POLYGON_FOREX_WS_URL, ping_interval=20, ping_timeout=20, close_timeout=5
            ) as ws:
                stats.connected_at = datetime.now(UTC)
                backoff = initial_backoff_s
                # Auth
                await ws.send(json.dumps({"action": "auth", "params": api_key}))
                # Subscribe
                await ws.send(json.dumps({"action": "subscribe", "params": sub_params}))
                log.info(
                    "polygon_fx_stream.subscribed",
                    pairs=list(pairs),
                    url=POLYGON_FOREX_WS_URL,
                )

                batch: list[FxTickEvent] = []
                last_flush = datetime.now(UTC).timestamp()

                async for raw in ws:
                    if stop_event is not None and stop_event.is_set():
                        break
                    if not isinstance(raw, str):
                        # Polygon never sends bytes frames in normal operation
                        continue
                    events = parse_frame(raw)
                    if not events:
                        # auth / status / unknown frame — skip, do not log noisily
                        if '"ev":' not in raw:
                            stats.n_messages_skipped += 1
                        continue
                    batch.extend(events)
                    stats.n_ticks_total += len(events)
                    stats.last_tick_at = events[-1].ts

                    now_ts = datetime.now(UTC).timestamp()
                    if (
                        len(batch) >= batch_size
                        or (now_ts - last_flush) * 1000 >= batch_window_ms
                    ):
                        try:
                            written = await persist_batch(session_factory, batch)
                            stats.n_ticks_persisted += written
                        except Exception as exc:
                            log.warning(
                                "polygon_fx_stream.persist_failed", error=str(exc)
                            )
                            stats.last_error = str(exc)
                        batch.clear()
                        last_flush = now_ts

                # Final flush before reconnect / clean exit
                if batch:
                    try:
                        written = await persist_batch(session_factory, batch)
                        stats.n_ticks_persisted += written
                    except Exception as exc:
                        log.warning(
                            "polygon_fx_stream.final_flush_failed", error=str(exc)
                        )
                        stats.last_error = str(exc)
                    batch.clear()

                if stop_event is not None and stop_event.is_set():
                    return

        except (ConnectionClosed, WebSocketException, OSError, asyncio.TimeoutError) as exc:
            stats.last_error = f"{type(exc).__name__}: {exc}"
            stats.reconnects += 1
            log.warning(
                "polygon_fx_stream.disconnect", error=stats.last_error, backoff=backoff
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff_s)
        except Exception as exc:  # noqa: BLE001 — long-running supervisor
            stats.last_error = f"unexpected: {type(exc).__name__}: {exc}"
            stats.reconnects += 1
            log.error("polygon_fx_stream.unexpected", error=stats.last_error)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff_s)


# ── CLI entry ────────────────────────────────────────────────────────


async def _main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ]
    )
    api_key = os.environ.get("ICHOR_API_POLYGON_API_KEY", "").strip()
    if not api_key:
        log.error(
            "polygon_fx_stream.no_api_key",
            hint="Set ICHOR_API_POLYGON_API_KEY in /etc/ichor/api.env",
        )
        return 2

    raw_pairs = os.environ.get("ICHOR_API_POLYGON_FX_PAIRS", "").strip()
    pairs: tuple[str, ...] = (
        tuple(p.strip() for p in raw_pairs.split(",") if p.strip())
        if raw_pairs
        else DEFAULT_PAIRS
    )

    stop = asyncio.Event()

    def _shutdown(signame: str) -> None:
        log.info("polygon_fx_stream.signal", signame=signame)
        stop.set()

    loop = asyncio.get_running_loop()
    try:
        # SIGTERM/SIGINT handlers — Linux only ; on Windows we rely on
        # KeyboardInterrupt percolating up.
        import signal

        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, _shutdown, sig.name)
            except NotImplementedError:
                pass
    except ImportError:
        pass

    await stream_forever(api_key=api_key, pairs=pairs, stop_event=stop)
    return 0


if __name__ == "__main__":
    import sys

    # logging fallback if structlog isn't initialized
    logging.basicConfig(level=logging.INFO)
    sys.exit(asyncio.run(_main()))
