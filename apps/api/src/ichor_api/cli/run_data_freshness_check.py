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
from typing import Any

import structlog
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from ..collectors.fred_extended import merged_series
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
_RSS_SLOW_FEEDS: frozenset[str] = frozenset({"boc_press", "crisisgroup"})
_RSS_SLOW_WINDOW = timedelta(days=8)

# Per-series FRED freshness (S02 socle audit 2026-06-18). `fred_observations`
# holds dozens of series; the global `fred` FreshnessSpec checks only the
# whole-table MAX(fetched_at), which VIX_LIVE (5-min poll) keeps perpetually
# fresh — so a daily series that silently dies (DGS2, a Treasury yield, an FX
# pair…) is INVISIBLE to it. We sweep the DAILY business-day series per-series.
#
# The daily set is an EXPLICIT curated allowlist intersected with the actually-
# collected series (`merged_series()`). We do NOT derive it as "everything minus
# the slow-age registry": that registry is INCOMPLETE (e.g. CPIAUCSL, a MONTHLY
# series, is absent from it), so the subtraction would wrongly classify monthly
# series as daily and false-positive every month between prints. The allowlist
# only holds series whose publication cadence is genuinely daily-business-day
# (Treasury yields, TIPS, breakevens, credit OAS, policy rates, the broad-dollar
# index, vol indices, energy spot, FX rates, daily EPU). The intersection drops
# any that this deployment doesn't collect (→ no false "absent").
#
# The 5-day window absorbs weekend + back-to-back US holidays: `fetched_at` only
# advances when a NEW observation_date prints (persist dedup), so it legitimately
# freezes over a long weekend even on a healthy daily series — a tighter window
# would false-positive every Monday. The aggregated `fred` spec still catches a
# TOTAL collector outage; this per-series sweep is the additive warning tier.
_FRED_SERIES_WINDOW = timedelta(days=5)
_FRED_DAILY_CANDIDATES: frozenset[str] = frozenset(
    {
        # Treasury nominal constant-maturity yields (daily BD)
        "DGS1MO",
        "DGS3MO",
        "DGS6MO",
        "DGS1",
        "DGS2",
        "DGS3",
        "DGS5",
        "DGS7",
        "DGS10",
        "DGS20",
        "DGS30",
        # Treasury spreads / curve
        "T10Y2Y",
        "T10Y3M",
        "T10YFF",
        # TIPS real yields + term premium + breakevens
        "DFII5",
        "DFII10",
        "DFII30",
        "THREEFYTP10",
        "T5YIE",
        "T10YIE",
        "T5YIFR",
        # Credit OAS
        "BAMLH0A0HYM2",
        "BAMLC0A0CM",
        # Policy / overnight rates
        "SOFR",
        "DFF",
        "EFFR",
        "OBFR",
        # Fed liquidity / overnight RRP (daily BD) — sole RRP input to the
        # liquidity proxy (liq_proxy_d). WTREGEN (TGA) is deliberately NOT here:
        # FRED publishes it weekly (week-ending Wednesday) so a daily window
        # would false-positive every day between prints.
        "RRPONTSYD",
        # Broad-dollar indices
        "DTWEXBGS",
        "DTWEXAFEGS",
        # Volatility indices (CBOE, daily BD)
        "VIXCLS",
        "VXVCLS",
        "GVZCLS",
        "OVXCLS",
        "RVXCLS",
        # Energy spot
        "DCOILWTICO",
        "DCOILBRENTEU",
        "DHHNGSP",
        # FX spot rates
        "DEXJPUS",
        "DEXUSEU",
        "DEXCHUS",
        "DEXCAUS",
        "DEXSZUS",
        "DEXUSAL",
        "DEXUSNZ",
        "DEXHKUS",
        "DEXKOUS",
        "DEXSDUS",
        # Daily economic-policy-uncertainty
        "USEPUINDXD",
    }
)
# Only monitor series this deployment actually collects (avoids a false "absent"
# on a candidate that is not in the collector's series list).
_FRED_DAILY_SERIES: tuple[str, ...] = tuple(
    s for s in merged_series() if s in _FRED_DAILY_CANDIDATES
)
# Defensive: a per-series alert key would land in alerts.asset VARCHAR(16) if we
# ever switch from the aggregated asset=None payload to per-series rows.
assert all(len(s) <= 16 for s in _FRED_DAILY_SERIES), "FRED series_id exceeds 16 chars"

# Per-SOURCE synthetic-series sweep (S02 socle round 5 audit). ~10 collectors
# write into fred_observations under SYNTHETIC (non-FRED) series_id prefixes —
# BLS_*, ECB_*, ZQ_*, AAII_*, BOE_*, WIKI_PV_*, TREASURY_AUC_*, DTS_TGA_CLOSE.
# The global `fred` spec only MAX()es the whole table (kept fresh by VIX_LIVE),
# and _FRED_DAILY_CANDIDATES holds ONLY genuine FRED codes — so any of these
# synthetic sources can silently die for weeks and NOTHING alerts (the exact
# dead-collector class collector_freshness exists to kill). We sweep each
# scheduled synthetic source by its series_id PREFIX (LIKE) with a window sized
# to its real publication cadence + a missed-runs grace.
#
# DELIBERATELY EXCLUDED: DEFILLAMA_*, CRYPTO_FNG, BINANCE_FUNDING_* — these
# collectors have NO systemd timer in scripts/hetzner/register-cron-*.sh (only
# reachable via an `all` run that is itself unscheduled), so monitoring them
# would emit a PERMANENT false "silent" alert. If they get scheduled, add them
# here. Windows honour publication lag (a tighter window false-positives between
# legitimately-spaced prints — fetched_at only advances on a NEW observation).
_FRED_SYNTHETIC_TIERS: tuple[tuple[str, str, timedelta], ...] = (
    # (label, series_id LIKE pattern, max_age)
    ("bls", "BLS_%", timedelta(days=45)),  # monthly employment/ECI
    ("ecb_sdmx", "ECB_%", timedelta(days=45)),  # monthly HICP/M3 + event MRO
    ("dts_treasury", "DTS_TGA_CLOSE", timedelta(days=5)),  # daily business day
    ("cme_zq", "ZQ_%", timedelta(days=5)),  # daily fed-funds futures settle
    ("aaii", "AAII_%", timedelta(days=10)),  # weekly Thursday sentiment
    ("boe_iadb", "BOE_%", timedelta(days=10)),  # mixed daily/monthly UK rates
    ("wiki_pv", "WIKI_PV_%", timedelta(days=5)),  # daily Wikimedia pageviews
    ("treasury_auc", "TREASURY_AUC_%", timedelta(days=12)),  # event-driven auctions
)


def _fmt_age(age: timedelta | None) -> str:
    if age is None:
        return "n/a"
    hours = age.total_seconds() / 3600
    return f"{hours:.1f}h"


async def _sweep_registry(session: AsyncSession, *, now: datetime) -> list[FreshnessResult]:
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


async def _emit_alerts(session: AsyncSession, results: list[FreshnessResult]) -> int:
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
        if r.status == "absent" or r.age is None:
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


async def _sweep_rss_feeds(session: AsyncSession, *, now: datetime) -> tuple[list[str], int]:
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
    latest_by_feed: dict[str, datetime | None] = {
        str(source): latest for source, latest in rows.all()
    }
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


async def _sweep_fred_series(session: AsyncSession, *, now: datetime) -> tuple[list[str], int]:
    """Per-series FRED silent sweep (S02 socle audit) — mirror of
    ``_sweep_rss_feeds``. The whole-table ``MAX(fetched_at)`` (global ``fred``
    spec) stays fresh on VIX_LIVE while a daily series can die unseen ; this
    GROUP-BYs the DAILY series and flags any that stopped advancing past the
    5-day window. WHERE-filtered to ``_FRED_DAILY_SERIES`` so the table's
    synthetic non-FRED keys (VIX_LIVE, BLS_*, EIA_*…) are never evaluated with a
    daily threshold. Returns (silent_series, n_alerts)."""
    names = list(_FRED_DAILY_SERIES)
    rows = await session.execute(
        sa_text(
            "SELECT series_id, max(fetched_at) FROM fred_observations "
            "WHERE series_id = ANY(:names) GROUP BY series_id"
        ),
        {"names": names},
    )
    latest_by_series: dict[str, datetime | None] = {
        str(series_id): latest for series_id, latest in rows.all()
    }
    silent: list[str] = []
    for name in names:
        latest = latest_by_series.get(name)
        if latest is not None and latest.tzinfo is None:
            latest = latest.replace(tzinfo=UTC)
        if latest is None or (now - latest) > _FRED_SERIES_WINDOW:
            silent.append(name)
    n_alerts = 0
    if silent:
        hits = await check_metric(
            session,
            metric_name="fred_series_silent",
            current_value=float(len(silent)),
            asset=None,
            extra_payload={"silent_series": ", ".join(sorted(silent))},
        )
        n_alerts = len(hits)
    return silent, n_alerts


async def _sweep_fred_synthetic_sources(
    session: AsyncSession, *, now: datetime
) -> tuple[list[str], int]:
    """Per-SOURCE synthetic-series silent sweep (S02 socle round 5). The
    synthetic collectors (BLS_/ECB_/ZQ_/AAII_/BOE_/WIKI_PV_/TREASURY_AUC_/DTS_)
    write into fred_observations but are covered by NEITHER the global ``fred``
    spec (whole-table MAX, kept fresh by VIX_LIVE) NOR ``_sweep_fred_series``
    (genuine FRED codes only). MAX(fetched_at) per prefix vs its cadence window;
    flag absent/stale. Returns (silent_labels, n_alerts)."""
    silent: list[str] = []
    for label, pattern, window in _FRED_SYNTHETIC_TIERS:
        row = await session.execute(
            sa_text("SELECT max(fetched_at) FROM fred_observations WHERE series_id LIKE :pat"),
            {"pat": pattern},
        )
        latest = row.scalar_one_or_none()
        if latest is not None and latest.tzinfo is None:
            latest = latest.replace(tzinfo=UTC)
        if latest is None or (now - latest) > window:
            silent.append(label)
    n_alerts = 0
    if silent:
        hits = await check_metric(
            session,
            metric_name="fred_synthetic_silent",
            current_value=float(len(silent)),
            asset=None,
            extra_payload={"silent_sources": ", ".join(sorted(silent))},
        )
        n_alerts = len(hits)
    return silent, n_alerts


def _load_state(path: Path) -> dict[str, Any] | None:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _save_state(path: Path, state: dict[str, Any]) -> None:
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
            silent: list[str] = []
            fred_silent: list[str] = []
            synth_silent: list[str] = []
            if dry_run:
                n_alerts = 0
                for r in results:
                    print(
                        f"  [{r.spec.source_key:18s}] {r.status:22s} "
                        f"age={_fmt_age(r.age)} max={_fmt_age(r.spec.max_age)} "
                        f"tier={r.spec.criticality}"
                    )
                silent, _ = await _sweep_rss_feeds(session, now=now)
                fred_silent, _ = await _sweep_fred_series(session, now=now)
                synth_silent, _ = await _sweep_fred_synthetic_sources(session, now=now)
                await session.rollback()
            else:
                n_alerts = await _emit_alerts(session, results)
                silent, n_rss = await _sweep_rss_feeds(session, now=now)
                n_alerts += n_rss
                fred_silent, n_fred = await _sweep_fred_series(session, now=now)
                n_alerts += n_fred
                synth_silent, n_synth = await _sweep_fred_synthetic_sources(session, now=now)
                n_alerts += n_synth
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
        f"{len(silent)} silent feeds · {len(fred_silent)} silent FRED series · "
        f"{len(synth_silent)} silent synthetic sources · "
        f"{n_alerts} alerts emitted"
    )
    for r in degraded:
        print(
            f"  DEGRADED [{r.spec.criticality}] {r.spec.source_key}: {r.status} "
            f"age={_fmt_age(r.age)} (max {_fmt_age(r.spec.max_age)})"
        )
    if silent:
        print(f"  SILENT FEEDS (48h+): {', '.join(sorted(silent))}")
    if fred_silent:
        print(f"  SILENT FRED SERIES (5d+): {', '.join(sorted(fred_silent))}")
    if synth_silent:
        print(f"  SILENT SYNTHETIC SOURCES: {', '.join(sorted(synth_silent))}")

    log.info(
        "data_freshness.complete",
        n_sources=len(results),
        degraded=[r.spec.source_key for r in degraded],
        critical=[r.spec.source_key for r in critical],
        silent_feeds=silent,
        silent_fred_series=fred_silent,
        silent_synthetic_sources=synth_silent,
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
