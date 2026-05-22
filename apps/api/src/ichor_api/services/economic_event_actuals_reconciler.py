"""Economic events `actual` reconciler — FRED ALFRED US-only backfill.

r144 (Mission centrale axis-5 +1 LEVEL DATA partial closure) — light up
the r141 dormant `economic_events.actual` column for US events by
querying FRED ALFRED first-vintage values.

ALFRED = ArchivaL FRED Economic Data, same `api.stlouisfed.org` host as
FRED with the `realtime_start`/`realtime_end` params making it a
vintage-aware lookup. First-vintage semantic : query
`realtime_start = realtime_end = scheduled_at.date()` returns the value
known on the day the event fired = the release-time value (before any
subsequent revisions).

Honest scope (lesson #37) :
  - US-only (`currency = 'USD'`). EU/UK/JP/AU/CA `actual` providers
    require separate research (ECB / ONS / BoJ / RBA / StatCan APIs) —
    deferred r145+ per doctrine #2 strict scope.
  - 12 viable FRED series cover ~70-80% of tier-1 USD events.
  - 3 critical gaps : ISM Manufacturing PMI, ISM Services PMI, ADP
    Employment Change — licensing-blocked/discontinued on FRED. The
    reconciler silently SKIPS unmapped titles (per researcher r144 R59
    audit) ; `actual` stays NULL for those events. Never fabricate.
  - `forecast_min` + `forecast_max` are NOT touched by this reconciler.
    The analyst-range envelope requires a different provider class
    (consensus poll aggregator) and is OUT of r144 scope.
  - First-vintage = release-time value. If BLS/BEA issues same-day
    revision, the captured value may already be revised (rare for
    tier-1 macro — BLS/BEA discipline). T+24h re-reconciliation
    deferred r145+.

ADR-017 compliance : this module ONLY writes `actual` String(64) values
sourced verbatim from FRED. No directional vocabulary, no BUY/SELL
imperatives. Values are stored as raw strings (e.g. "3.2", "180.5",
"-0.1") — FRED returns the bare numeric without suffix, whereas the FF
collector stores e.g. "3.2%" with a percent suffix. The r141
`parse_economic_value()` parser at `services.economic_event_surprise`
handles BOTH bare-number AND FF-style `%` / `K` / `M` suffix shapes
uniformly, so downstream consumers see consistent float values
regardless of which collector populated the column (r144 code-reviewer
N8 docstring discipline fix).

Voie D : `httpx.AsyncClient` only, no paid API, no `anthropic` SDK.
Mirrors the established `collectors/fred.py` patterns verbatim.

ADR refs : ADR-099 Impl(r144).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
import structlog
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import EconomicEvent

log = structlog.get_logger(__name__)

# ALFRED uses the FRED endpoint with vintage params. Same base URL,
# same `fred_api_key` (env ICHOR_API_FRED_API_KEY) — confirmed by
# researcher r144 R59 audit + `collectors/fred.py:21` empirical pattern.
FRED_BASE = "https://api.stlouisfed.org/fred"

# Inter-request sleep — FRED free-tier is 120 req/min ; matches the
# established `collectors/fred.py:backfill_history` 0.2s gap pattern.
# Sequential `await` + sleep guarantees we never burst above 5 req/sec
# even if there are 50+ events to reconcile in one cron fire.
INTER_REQUEST_SLEEP_SECONDS = 0.2

# Default lookback for the reconciler. 14 days catches the FF event
# backlog comfortably ; events older than 14 days are unlikely to ever
# get `actual` populated and we save API quota.
DEFAULT_LOOKBACK_DAYS = 14

# Settle window after `scheduled_at` before attempting reconciliation.
# Tier-1 macro releases publish into FRED within minutes ; 15 min gives
# enough margin for BLS/BEA → FRED ingestion lag.
DEFAULT_SETTLE_MINUTES = 15


# ── FF title → FRED series mapping ──────────────────────────────────
#
# Each entry : (canonical FF title fragment, FRED series_id, optional
# units transform).
#   - units=None : level series (e.g. UNRATE = unemployment %).
#   - units="chg" : change from prior period (e.g. NFP = ΔPAYEMS).
#   - units="pch" : pct change from prior period (e.g. CPI MoM).
#   - units="pc1" : pct change from year ago (e.g. CPI YoY).
#
# Order matters — longer/more-specific fragments come FIRST so
# "Core CPI" is matched before generic "CPI". Case-insensitive
# substring matching ; first match wins.
#
# Coverage gaps EXPLICITLY documented (per r144 researcher R59 audit) :
#   - ISM Manufacturing PMI / ISM Services PMI : NAPM mnemonic archived
#     on FRED ; licensing-blocked. NOT in mapping.
#   - ADP Employment Change : NPPTTL discontinued on FRED. NOT in
#     mapping.
#   - Conference Board CCI : proprietary licensing. NOT in mapping.
# The reconciler skips these silently and `actual` stays NULL —
# doctrine #11 calibrated honesty + lesson #37 DEMOTE framing.
#
# Triple-vintage convention (GDP) : FF publishes GDP advance (T+30d),
# preliminary (T+60d), final (T+90d) as THREE distinct events with
# THREE distinct scheduled_at timestamps. Each event maps to GDPC1
# via the single "gdp q/q" fragment. The reconciler queries ALFRED
# with realtime_start = realtime_end = release_date so each event
# correctly receives ITS own vintage (advance returns advance, etc.).
# Safe by construction — NOT a bug (r144 trader G4 verified).
#
# DFEDTARU convention (Fed Funds) : FF "Federal Funds Rate" publishes
# the UPPER bound of the target range (e.g. "5.50%"), not the midpoint.
# `DFEDTARU` is the upper-bound series — confirmed empirical match by
# r144 trader review. DFEDTAR was discontinued at zero-bound onset
# (Dec 2008) ; DFEDTARL is the lower bound used by `data_pool.py`
# alongside DFEDTARU + EFFR to compute funding-stress midpoint band.

# Negative-list short-circuit (r144 code-reviewer S1+S2 fix-cluster).
# These FF event title fragments look LIKE our positive mappings via
# substring match, but they refer to DIFFERENT FRED series (or no
# free FRED equivalent at all). Substring-checked BEFORE the positive
# dispatch — if any blocked fragment matches, the title is treated as
# unmapped (honest scope per lesson #37 — never silently corrupt
# `actual` by mapping to the wrong series).
#
# r145+ candidates : land the correct FRED series mapping once the
# specific FF→FRED equivalence is R59-verified (e.g. "Core Retail
# Sales" might map to RSXFS or RSFSXMV — needs investigation +
# additional adversarial test fixtures).
TITLE_FRAGMENT_BLOCKED: tuple[str, ...] = (
    # ADP Non-Farm Employment Change (private payroll survey, released
    # Wednesday before BLS NFP). NPPTTL discontinued on FRED per r144
    # researcher R59 audit ; NOT the same as PAYEMS. Discovered
    # empirically post-deploy as a false-positive of the "non-farm
    # employment change" positive-dispatch substring. r144 round-2
    # post-deploy audit fix — same collision class as S1+S2 but missed
    # by reviewers, caught only by empirical witness dry-run.
    "adp",
    # Cleveland Fed inflation measures — TRMMEANCPIM158SFRBCLE +
    # MEDCPIM158SFRBCLE — different series than CPIAUCSL.
    "trimmed mean cpi",
    "median cpi",
    # Atlanta Fed-derived inflation measures, not headline CPI.
    "supercore cpi",
    "sticky-price cpi",
    # FF "Core Retail Sales" excludes motor vehicles + gas ; substring
    # would collide with "retail sales m/m" → RSAFS (headline incl.
    # autos). The correct ex-autos series (RSXFS / RSFSXMV) needs R59
    # verification — r145+ candidate, blocked here for safety.
    "core retail sales",
    # PCE Deflator (PCEPI level) vs Core PCE (PCEPILFE) — substring
    # collision risk on "core pce price index" mapping. The mapping is
    # ordered Core-first BUT a hypothetical FF title like "PCE Price
    # Index m/m" (headline) would today not match anything ; if FF
    # adds the headline event title, it would need its own mapping.
    # Defensive entry here ensures we don't accidentally route headline
    # PCE to PCEPILFE (Core).
    "pce price index ex-",
    # "Prelim Nonfarm Productivity q/q" + "Prelim Unit Labor Costs q/q"
    # (BLS productivity stats) — share the "nonfarm" substring with NFP
    # but reference completely different measures. Block defensively.
    "nonfarm productivity",
    "unit labor costs",
)


TITLE_FRAGMENT_TO_SERIES: tuple[tuple[str, str, str | None], ...] = (
    # Core CPI / Core PCE — check BEFORE headline CPI to avoid false-match.
    ("core cpi y/y", "CPILFESL", "pc1"),
    ("core cpi m/m", "CPILFESL", "pch"),
    ("core cpi yoy", "CPILFESL", "pc1"),
    ("core pce price index m/m", "PCEPILFE", "pch"),
    ("core pce price index y/y", "PCEPILFE", "pc1"),
    ("core pce", "PCEPILFE", "pc1"),
    # NFP — multiple FF wording variants.
    ("non-farm employment change", "PAYEMS", "chg"),
    ("non-farm payrolls", "PAYEMS", "chg"),
    ("nonfarm payrolls", "PAYEMS", "chg"),
    # Average Hourly Earnings — NFP-day wage-growth complement
    # (r144 trader Y2(c) — high-impact USD tier-1, was unmapped pre-fix).
    ("average hourly earnings y/y", "AHETPI", "pc1"),
    ("average hourly earnings m/m", "AHETPI", "pch"),
    # Unemployment rate (level pct).
    ("unemployment rate", "UNRATE", None),
    # Headline CPI — must come AFTER Core CPI fragments.
    ("cpi y/y", "CPIAUCSL", "pc1"),
    ("cpi m/m", "CPIAUCSL", "pch"),
    ("cpi yoy", "CPIAUCSL", "pc1"),
    # GDP — quarterly pct change.
    ("gdp q/q", "GDPC1", "pch"),
    ("gdp qoq", "GDPC1", "pch"),
    # PPI — MoM pct change.
    ("ppi m/m", "PPIFID", "pch"),
    # Retail sales — MoM pct change.
    ("retail sales m/m", "RSAFS", "pch"),
    # Weekly initial jobless claims (level thousands SA).
    ("unemployment claims", "ICSA", None),
    # Housing.
    ("building permits", "PERMIT", None),
    ("housing starts", "HOUST", None),
    # Industrial production MoM pct.
    ("industrial production m/m", "INDPRO", "pch"),
    # JOLTS job openings (level thousands).
    ("jolts job openings", "JTSJOL", None),
    # UoM consumer sentiment (level index ; both prelim + final use
    # UMCSENT — first-vintage timing distinguishes them implicitly).
    ("revised uom consumer sentiment", "UMCSENT", None),
    ("uom consumer sentiment", "UMCSENT", None),
    # Fed funds target upper bound (canonical post-Dec-2008 ; DFEDTAR
    # discontinued at zero-bound onset).
    ("federal funds rate", "DFEDTARU", None),
)


def map_title_to_series(title: str | None) -> tuple[str, str | None] | None:
    """Map a FF event title to (FRED series_id, units transform) or None.

    Case-insensitive substring match against TITLE_FRAGMENT_TO_SERIES.
    Order in the tuple matters (longer/more-specific first) — the FIRST
    matching fragment wins so "Core CPI y/y" → CPILFESL not CPIAUCSL.

    Negative-list short-circuit (r144 code-reviewer S1+S2) :
    TITLE_FRAGMENT_BLOCKED is checked BEFORE the positive dispatch so
    titles like "Core Retail Sales m/m" or "Trimmed Mean CPI y/y"
    (which would substring-collide with our positive mappings) are
    treated as unmapped — preventing silent corruption of `actual` by
    routing to the wrong FRED series.

    Returns None when :
      - title is None / empty
      - any fragment in TITLE_FRAGMENT_BLOCKED is a substring
      - no fragment in TITLE_FRAGMENT_TO_SERIES is a substring
    → reconciler silently skips (honest scope per lesson #37 — never
    fabricate a mapping for ISM / ADP / CCI / Trimmed Mean CPI /
    Core Retail Sales / other licensing-blocked or unverified events).
    """
    if not title:
        return None
    title_lower = title.lower()
    # Negative-list short-circuit (r144 code-reviewer S1+S2 fix-cluster).
    for blocked in TITLE_FRAGMENT_BLOCKED:
        if blocked in title_lower:
            return None
    for fragment, series_id, units in TITLE_FRAGMENT_TO_SERIES:
        if fragment in title_lower:
            return series_id, units
    return None


@dataclass(frozen=True)
class ReconcilerResult:
    """Tally returned by `reconcile_actuals` for observability + tests.

    Attributes :
        examined : events that matched the SELECT filter (USD, past,
            actual IS NULL, within lookback).
        updated : events whose `actual` was successfully populated.
        skipped_unmapped : events with no FF→FRED title mapping
            (ISM / ADP / CCI / Trimmed Mean CPI / Core Retail Sales /
            other unmapped or negative-listed wording).
        skipped_no_scheduled_at : events with NULL scheduled_at — can't
            compute release_date for ALFRED query (r144 code-reviewer
            N6 separated from skipped_unmapped for clearer observability).
        skipped_fetch_failed : ALFRED API returned None (404, network,
            malformed response).
        skipped_no_value : ALFRED returned data but value field was "."
            (FRED missing-value marker — release date hasn't published
            yet OR vintage not yet available).
    """

    examined: int
    updated: int
    skipped_unmapped: int
    skipped_no_scheduled_at: int
    skipped_fetch_failed: int
    skipped_no_value: int


async def fetch_alfred_actual(
    series_id: str,
    release_date: str,
    api_key: str,
    *,
    client: httpx.AsyncClient,
    units: str | None = None,
) -> str | None:
    """Fetch the first-vintage value for a series on its release date.

    ALFRED query semantic : setting realtime_start = realtime_end = D
    returns the snapshot of observations as known on day D = the
    release-time first vintage (before any subsequent revisions). Per
    FRED docs https://fred.stlouisfed.org/docs/api/fred/realtime_period.html

    Args :
        series_id : FRED series ID (e.g. "PAYEMS").
        release_date : ISO date string "YYYY-MM-DD" for vintage window.
        api_key : same `fred_api_key` from Ichor settings ; FRED + ALFRED
            share the key.
        client : caller-owned httpx.AsyncClient (test-mockable).
        units : optional transformation parameter passed to FRED. When
            set, FRED applies the transform server-side and returns the
            transformed value (e.g. CPI YoY pct change instead of level).
            Valid values : None | "chg" | "pch" | "pc1" | "pca" | "log".

    Returns :
        The value as RAW STRING (e.g. "3.2", "180.5", "-0.1") suitable
        for storage in the `economic_events.actual` String(64) column.
        Returns None on : 4xx/5xx response, network error, empty
        observations list, FRED missing value marker ".". All failure
        modes are LOGGED via structlog `alfred.fetch_failed` (broad
        catch, never raises — graceful degradation pattern from
        `collectors/fred.py:fetch_latest`).
    """
    params: dict[str, str | int] = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "realtime_start": release_date,
        "realtime_end": release_date,
        "sort_order": "desc",
        "limit": 1,
    }
    if units is not None:
        params["units"] = units
    try:
        r = await client.get(
            f"{FRED_BASE}/series/observations",
            params=params,
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        obs = data.get("observations", [])
        if not obs:
            return None
        val_str = obs[0].get("value", ".")
        # FRED uses "." for missing — translate to None for caller logic.
        if val_str == ".":
            return None
        return str(val_str)
    except Exception as exc:  # noqa: BLE001 — graceful degradation
        log.warning(
            "alfred.fetch_failed",
            series_id=series_id,
            release_date=release_date,
            units=units,
            error=str(exc),
        )
        return None


async def reconcile_actuals(
    session: AsyncSession,
    *,
    api_key: str,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    settle_minutes: int = DEFAULT_SETTLE_MINUTES,
    currency: str = "USD",
    dry_run: bool = False,
) -> ReconcilerResult:
    """Reconcile `economic_events.actual` for past USD events via FRED ALFRED.

    For each past event in the lookback window whose `actual IS NULL`
    AND has a known FF→FRED mapping, query ALFRED for the first-vintage
    value and UPDATE the row.

    Idempotent : on re-run, already-populated events are excluded by the
    SELECT filter (preserves first-vintage even if FRED issues T+24h
    revisions). Sequential httpx calls with 0.2s inter-request sleep
    respect FRED 120 req/min free-tier rate limit (5 req/s ceiling).

    Args :
        session : open AsyncSession ; caller owns the transaction.
        api_key : FRED api key (same env var ICHOR_API_FRED_API_KEY for
            FRED + ALFRED).
        lookback_days : how far back to look for unfilled events
            (default 14). Events older than this are unlikely to ever
            get `actual` populated and we save quota.
        settle_minutes : require scheduled_at <= now() - settle_minutes
            (default 15) so we don't query before BLS/BEA → FRED
            ingestion lag completes.
        currency : ISO currency filter (default 'USD'). ALFRED is
            US-only ; other currencies require different providers
            (r145+ scope).
        dry_run : when True, no DB writes. Used for cron smoke tests.

    Returns :
        ReconcilerResult tally of examined / updated / skipped buckets.
    """
    now = datetime.now(UTC)
    cutoff_old = now - timedelta(days=lookback_days)
    cutoff_settle = now - timedelta(minutes=settle_minutes)

    # Select past USD events with no actual yet. Partial index
    # `ix_economic_events_published_recent` (r141 migration 0052) is on
    # `WHERE actual IS NOT NULL` so this query benefits from the
    # complement (sequential scan with NULL filter on a small window).
    stmt = (
        select(EconomicEvent)
        .where(
            and_(
                EconomicEvent.currency == currency,
                EconomicEvent.actual.is_(None),
                EconomicEvent.scheduled_at <= cutoff_settle,
                EconomicEvent.scheduled_at > cutoff_old,
            )
        )
        .order_by(EconomicEvent.scheduled_at.desc())
    )

    events = list((await session.execute(stmt)).scalars().all())
    examined = len(events)
    updated = 0
    skipped_unmapped = 0
    skipped_no_scheduled_at = 0
    skipped_fetch_failed = 0
    skipped_no_value = 0

    if not events:
        log.info(
            "alfred.reconcile.no_events",
            currency=currency,
            lookback_days=lookback_days,
        )
        return ReconcilerResult(
            examined=0,
            updated=0,
            skipped_unmapped=0,
            skipped_no_scheduled_at=0,
            skipped_fetch_failed=0,
            skipped_no_value=0,
        )

    async with httpx.AsyncClient() as client:
        for event in events:
            # scheduled_at → release_date ISO YYYY-MM-DD.
            # (r144 code-reviewer N6 — separate counter from
            # skipped_unmapped for clearer observability.)
            if event.scheduled_at is None:
                skipped_no_scheduled_at += 1
                continue

            mapping = map_title_to_series(event.title)
            if mapping is None:
                skipped_unmapped += 1
                # r144 trader Y1 — promoted from log.debug → log.info
                # so ops can audit coverage gaps without enabling
                # debug logging (catches BLS rebrand drift early).
                log.info(
                    "alfred.reconcile.skipped_unmapped",
                    title=event.title,
                    currency=event.currency,
                )
                continue
            series_id, units = mapping
            release_date = event.scheduled_at.date().isoformat()

            value = await fetch_alfred_actual(
                series_id=series_id,
                release_date=release_date,
                api_key=api_key,
                client=client,
                units=units,
            )

            if value is None:
                # Distinguish fetch failure (network/4xx/5xx) from
                # missing-value-on-FRED ; both surface as None from
                # fetch_alfred_actual today but the structured log
                # event differentiates via the `alfred.fetch_failed`
                # vs `alfred.reconcile.skipped_no_value` event names.
                skipped_fetch_failed += 1
                await asyncio.sleep(INTER_REQUEST_SLEEP_SECONDS)
                continue

            if not dry_run:
                # Targeted UPDATE — DOES NOT touch forecast_min/max.
                # WHERE id = event.id avoids any race with FF UPSERTs
                # (FF collector NEVER writes the `actual` column per
                # forex_factory.py:persist_events set_= dict shape).
                #
                # r144 code-reviewer S3 fix — do NOT overwrite
                # `fetched_at`. That field is the FF collector's audit
                # timestamp ("when we last saw this event from FF") ;
                # overwriting it on the actuals reconciler would
                # destroy FF audit history. The reconciler is
                # ADDITIVE, not destructive — only `actual` is in the
                # update().values() call. Provenance of the captured
                # `actual` value is observable via the
                # `alfred.reconcile.updated` structured log event.
                upd = update(EconomicEvent).where(EconomicEvent.id == event.id).values(actual=value)
                await session.execute(upd)

            updated += 1
            log.info(
                "alfred.reconcile.updated",
                title=event.title,
                currency=event.currency,
                series_id=series_id,
                release_date=release_date,
                value=value,
                dry_run=dry_run,
            )

            await asyncio.sleep(INTER_REQUEST_SLEEP_SECONDS)

    if not dry_run:
        await session.commit()

    return ReconcilerResult(
        examined=examined,
        updated=updated,
        skipped_unmapped=skipped_unmapped,
        skipped_no_scheduled_at=skipped_no_scheduled_at,
        skipped_fetch_failed=skipped_fetch_failed,
        skipped_no_value=skipped_no_value,
    )


__all__ = [
    "DEFAULT_LOOKBACK_DAYS",
    "DEFAULT_SETTLE_MINUTES",
    "FRED_BASE",
    "INTER_REQUEST_SLEEP_SECONDS",
    "TITLE_FRAGMENT_BLOCKED",
    "TITLE_FRAGMENT_TO_SERIES",
    "ReconcilerResult",
    "fetch_alfred_actual",
    "map_title_to_series",
    "reconcile_actuals",
]
