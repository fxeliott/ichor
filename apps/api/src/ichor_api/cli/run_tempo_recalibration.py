"""r126 ADR-099 §Impl — weekly tempo threshold recalibration CLI.

Weekly Sunday 04:00 Paris cron. Recomputes the per-asset daily-range
percentile thresholds from a rolling 90-day window on `polygon_intraday`
and INSERTs one row per asset into `tempo_thresholds` (migration 0051).

The frontend `<TodaySessionPulse>` panel will consume these via a new
`/v1/tempo-thresholds` endpoint in r127 (wire split — backend ships
first, data accumulates, then frontend wires with confidence).

Mission centrale Axis-7 (auto-amélioration en autonomie) partial extension :
the r125 hardcoded `TEMPO_THRESHOLDS_BY_ASSET` becomes self-recalibrating ;
the historical-trace shape of `tempo_thresholds` lets Eliot inspect
threshold drift over time via SSH `psql`.

Gated by feature flag `tempo_recalibration_collector_enabled` (default
False — fail-closed). Round-126 ship sets to `true @ 100` at deploy time.

Pattern mirrors r34 `cli/run_ecb_estr.py`.

Usage :
  python -m ichor_api.cli.run_tempo_recalibration [--dry-run]
                                                  [--window-days N]
                                                  [--min-sample-days N]
                                                  [--assets EUR_USD,...]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

import structlog

from ..db import get_engine, get_sessionmaker
from ..services.feature_flags import is_enabled
from ..services.tempo_recalibration import (
    DEFAULT_MIN_SAMPLE_DAYS,
    DEFAULT_RECALIBRATION_ASSETS,
    DEFAULT_WINDOW_DAYS,
    recalibrate_tempo_thresholds,
)

log = structlog.get_logger(__name__)

_FEATURE_FLAG_NAME = "tempo_recalibration_collector_enabled"


def _parse_assets(s: str) -> tuple[str, ...]:
    """Parse `--assets EUR_USD,GBP_USD,...` into a tuple. Empty/whitespace
    rejected ; case is preserved (canonical underscore-uppercase per
    ADR-083 asset code convention)."""
    raw = [tok.strip() for tok in s.split(",") if tok.strip()]
    if not raw:
        raise argparse.ArgumentTypeError(
            "--assets must be a non-empty comma-separated list of asset codes "
            "(e.g. EUR_USD,GBP_USD)"
        )
    return tuple(raw)


async def _run(
    *,
    dry_run: bool,
    window_days: int,
    min_sample_days: int,
    assets: tuple[str, ...],
) -> int:
    sm = get_sessionmaker()

    # Feature flag gate — fail-closed if disabled OR not set.
    async with sm() as flag_session:
        enabled = await is_enabled(flag_session, _FEATURE_FLAG_NAME)
    if not enabled:
        print(
            f"feature flag {_FEATURE_FLAG_NAME!r} is OFF — skipping "
            "tempo threshold recalibration (set to true via UPDATE "
            "feature_flags ... once you're ready to start the weekly cron)."
        )
        return 0

    print(
        f"== tempo_recalibration · window={window_days}d · "
        f"min_sample={min_sample_days} · assets={','.join(assets)} ==",
    )

    async with sm() as session:
        try:
            results = await recalibrate_tempo_thresholds(
                session,
                assets=assets,
                window_days=window_days,
                min_sample_days=min_sample_days,
                dry_run=dry_run,
            )
        except Exception as exc:  # noqa: BLE001 — surface to journalctl
            log.warning("tempo_recalibration.failed_top", error=str(exc))
            print(f"recalibration failed : {exc}", file=sys.stderr)
            await session.rollback()
            return 1

        if dry_run:
            print("DRY-RUN : computed thresholds but skipped DB INSERT")
        else:
            await session.commit()

    n_inserted = sum(1 for r in results if r.status == "inserted")
    n_skipped = sum(1 for r in results if r.status == "skipped")

    for r in results:
        if r.status == "inserted" and r.thresholds is not None:
            t = r.thresholds
            print(
                f"  {r.asset:<12} INSERTED  "
                f"breakout={t.breakout_bp:>7.2f}  "
                f"active={t.active_bp:>7.2f}  "
                f"trending={t.trending_bp:>7.2f}  "
                f"range_bound={t.range_bound_bp:>7.2f}  "
                f"n={t.sample_size}"
            )
        else:
            print(f"  {r.asset:<12} SKIPPED   reason={r.reason}")

    log.info(
        "tempo_recalibration.complete",
        n_inserted=n_inserted,
        n_skipped=n_skipped,
        window_days=window_days,
        min_sample_days=min_sample_days,
        dry_run=dry_run,
    )
    print(
        f"OK : {n_inserted} asset(s) inserted, {n_skipped} skipped "
        f"({'DRY-RUN' if dry_run else 'committed'})"
    )
    return 0


async def _async_main(args: argparse.Namespace) -> int:
    try:
        return await _run(
            dry_run=args.dry_run,
            window_days=args.window_days,
            min_sample_days=args.min_sample_days,
            assets=args.assets,
        )
    finally:
        await get_engine().dispose()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="run_tempo_recalibration",
        description=(
            "r126 ADR-099 §Impl — recalibrate per-asset tempo threshold rows "
            "from a rolling polygon_intraday window. Gated by feature flag "
            f"{_FEATURE_FLAG_NAME!r}."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute thresholds and print but skip DB INSERT (safe verify).",
    )
    parser.add_argument(
        "--window-days",
        type=int,
        default=DEFAULT_WINDOW_DAYS,
        help=(
            f"Rolling window over polygon_intraday Paris-days (default "
            f"{DEFAULT_WINDOW_DAYS} ; DB CHECK floor = 7)."
        ),
    )
    parser.add_argument(
        "--min-sample-days",
        type=int,
        default=DEFAULT_MIN_SAMPLE_DAYS,
        help=(f"Skip asset if sample size < this (default {DEFAULT_MIN_SAMPLE_DAYS})."),
    )
    parser.add_argument(
        "--assets",
        type=_parse_assets,
        default=DEFAULT_RECALIBRATION_ASSETS,
        help=(
            "Comma-separated asset codes (default = ADR-083 5 priority "
            f"assets {','.join(DEFAULT_RECALIBRATION_ASSETS)})."
        ),
    )
    args = parser.parse_args(argv)
    return asyncio.run(_async_main(args))


def _entrypoint() -> Any:  # pragma: no cover — module CLI entrypoint
    return sys.exit(main(sys.argv[1:]))


if __name__ == "__main__":
    _entrypoint()
