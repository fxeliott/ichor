"""S03 Chantier D — proactive data-freshness monitor cron CLI.

MAX()es every monitored collect table against the
``collector_freshness.FRESHNESS_REGISTRY`` expectation, classifies
fresh|stale|absent (minute-granular), emits ``COLLECTOR_STALE`` /
``COLLECTOR_ABSENT`` alerts through the canonical pipeline (2h dedup per
source via ``asset=source_key``), sweeps the per-feed RSS surface
(``RSS_FEED_SILENT``), and exits 2 on the healthy→degraded TRANSITION so
the systemd ``OnFailure=ichor-notify@`` path fires (state file mirrors
``ichor-runner-health-check``, re-notify every 2h while degraded).

Closes the Chantier D gate "a deliberately-killed collector fires an
alert < 15 min": 5-min timer + 10-15 min fast-tier max_age ⇒ worst-case
detection ≤ 15 min while the market is open.

Usage :

    python -m ichor_api.cli.run_data_freshness_check [--dry-run]
                                                     [--state-file PATH]

Exit codes :

    0 : healthy, OR degraded-but-already-notified (steady state)
    2 : critical-tier degradation TRANSITION (or 2h re-notify) —
        systemd Result=failed → OnFailure=ichor-notify@ fires
    3 : DB connection failure — cron infra issue (retry next tick)

Voie D : zero LLM call — pure SQL MAX() + catalog evaluation.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog
from sqlalchemy import text as sa_text

from ..collectors.rss import DEFAULT_FEEDS
from ..db import get_engine, get_sessionmaker
from ..services.alerts_runner import check_metric
from ..services.collector_freshness import (
    FRESHNESS_REGISTRY,
    FreshnessResult,
    decide_exit,
    evaluate_freshness,
    should_check,
)
from ..services.market_session import compute_session_status

log = structlog.get_logger(__name__)

DEFAULT_STATE_FILE = "/var/lib/ichor/data-freshness.state.json"

# A feed with zero items over this window is "silent" (dead URL, WAF
# block, format drift). 48h tolerates slow institutional feeds (BoC
# publishes ~2x/week) while still catching the BoE-403 class same-week.
_RSS_SILENT_WINDOW = timedelta(hours=48)
# Slow feeds whose legitimate publication gaps exceed 48h would
# permanently pollute the silent list — they get a wider window.
_RSS_SLOW_FEEDS: frozenset[str] = frozenset({"boc_press", "nfib", "crisisgroup"})
_RSS_SLOW_WINDOW = timedelta(days=8)


def _fmt_age(age: timedelta | None) -> str:
    if age is None:
        return "n/a"
    hours = age.total_seconds() / 3600
    return f"{hours:.1f}h"


async def _sweep_registry(session, *, now: datetime) -> list[FreshnessResult]:
    status_now = compute_session_status(now)
    results: list[FreshnessResult] = []
    for spec in FRESHNESS_REGISTRY:
        status_window_start = compute_session_status(now - spec.max_age)
        if not should_check(spec, status_now=status_now, status_window_start=status_window_start):
            results.append(FreshnessResult(spec, "skipped_market_closed", None, None))
            continue
        # Identifiers come from the code-owned registry and are shape-pinned
        # by FreshnessSpec.__post_init__ — not user input.
        row = await session.execute(
            sa_text(f"SELECT max({spec.ts_column}) FROM {spec.table}")  # noqa: S608
        )
        latest = row.scalar_one_or_none()
        results.append(evaluate_freshness(spec, latest, now=now))
    return results


async def _emit_alerts(session, results: list[FreshnessResult]) -> int:
    n = 0
    for r in results:
        if not r.is_degraded:
            continue
        payload = {
            "source_key": r.spec.source_key,
            "table": r.spec.table,
            "age_hours": round(r.age.total_seconds() / 3600, 1) if r.age else None,
            "max_age_hours": round(r.spec.max_age.total_seconds() / 3600, 1),
            "criticality": r.spec.criticality,
            "note": r.spec.note,
        }
        if r.status == "absent":
            hits = await check_metric(
                session,
                metric_name="collector_absent",
                current_value=1.0,
                asset=r.spec.source_key,
                extra_payload=payload,
            )
        else:
            ratio = r.age.total_seconds() / max(1.0, r.spec.max_age.total_seconds())
            hits = await check_metric(
                session,
                metric_name="collector_age_ratio",
                current_value=round(ratio, 2),
                asset=r.spec.source_key,
                extra_payload=payload,
            )
        n += len(hits)
    return n


async def _sweep_rss_feeds(session, *, now: datetime) -> tuple[list[str], int]:
    """Per-feed silent sweep — the aggregate news_items flow can stay
    fresh while individual feeds die. Returns (silent_feeds, n_alerts)."""
    feed_names = [f.name for f in DEFAULT_FEEDS]
    rows = await session.execute(
        sa_text(
            "SELECT source, max(fetched_at) FROM news_items "
            "WHERE source = ANY(:names) GROUP BY source"
        ),
        {"names": feed_names},
    )
    latest_by_feed = dict(rows.all())
    silent: list[str] = []
    for name in feed_names:
        window = _RSS_SLOW_WINDOW if name in _RSS_SLOW_FEEDS else _RSS_SILENT_WINDOW
        latest = latest_by_feed.get(name)
        if latest is not None and latest.tzinfo is None:
            latest = latest.replace(tzinfo=UTC)
        if latest is None or (now - latest) > window:
            silent.append(name)
    n_alerts = 0
    if silent:
        hits = await check_metric(
            session,
            metric_name="rss_silent_feeds",
            current_value=float(len(silent)),
            asset=None,
            extra_payload={"silent_feeds": ", ".join(sorted(silent))},
        )
        n_alerts = len(hits)
    return silent, n_alerts


def _load_state(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _save_state(path: Path, state: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state), encoding="utf-8")
    except OSError:
        log.warning("data_freshness.state_write_failed", path=str(path))


async def _run(*, dry_run: bool, state_file: Path) -> int:
    now = datetime.now(UTC)
    sm = get_sessionmaker()

    try:
        async with sm() as session:
            results = await _sweep_registry(session, now=now)
            if dry_run:
                n_alerts, silent = 0, []
                for r in results:
                    print(
                        f"  [{r.spec.source_key:18s}] {r.status:22s} "
                        f"age={_fmt_age(r.age)} max={_fmt_age(r.spec.max_age)} "
                        f"tier={r.spec.criticality}"
                    )
                silent, _ = await _sweep_rss_feeds(session, now=now)
                await session.rollback()
            else:
                n_alerts = await _emit_alerts(session, results)
                silent, n_rss = await _sweep_rss_feeds(session, now=now)
                n_alerts += n_rss
                await session.commit()
    except Exception as exc:
        print(f"DB failure during freshness sweep : {exc!s}. Cron will retry next tick.")
        return 3

    degraded = [r for r in results if r.is_degraded]
    critical = [r for r in degraded if r.spec.criticality == "critical"]
    skipped = [r for r in results if r.status == "skipped_market_closed"]

    print(
        f"freshness · {len(results)} sources checked · "
        f"{len(degraded)} degraded ({len(critical)} critical) · "
        f"{len(skipped)} skipped (market closed) · "
        f"{len(silent)} silent feeds · {n_alerts} alerts emitted"
    )
    for r in degraded:
        print(
            f"  DEGRADED [{r.spec.criticality}] {r.spec.source_key}: {r.status} "
            f"age={_fmt_age(r.age)} (max {_fmt_age(r.spec.max_age)})"
        )
    if silent:
        print(f"  SILENT FEEDS (48h+): {', '.join(sorted(silent))}")

    log.info(
        "data_freshness.complete",
        n_sources=len(results),
        degraded=[r.spec.source_key for r in degraded],
        critical=[r.spec.source_key for r in critical],
        silent_feeds=silent,
        n_alerts=n_alerts,
        dry_run=dry_run,
    )

    if dry_run:
        return 0

    prev = _load_state(state_file)
    code, new_state = decide_exit(
        prev, critical_degraded=bool(critical), now_epoch=int(now.timestamp())
    )
    _save_state(state_file, new_state)
    if code == 2:
        # Goes to stderr so notify-failure.sh's journal tail carries the cause.
        print(
            "freshness: TRANSITION/renotify — critical sources degraded: "
            + ", ".join(r.spec.source_key for r in critical),
            file=sys.stderr,
        )
    return code


async def _async_main(args: argparse.Namespace) -> int:
    try:
        return await _run(dry_run=args.dry_run, state_file=Path(args.state_file))
    finally:
        await get_engine().dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Proactive data-freshness monitor — MAX() every monitored collect "
            "table vs its expected window, alert on stale/absent, exit 2 on "
            "the critical degradation transition (OnFailure notify path)."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the full freshness table, persist nothing, always exit 0.",
    )
    parser.add_argument(
        "--state-file",
        default=DEFAULT_STATE_FILE,
        help=f"Transition-state JSON path (default {DEFAULT_STATE_FILE}).",
    )
    args = parser.parse_args(argv)
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    sys.exit(main())
