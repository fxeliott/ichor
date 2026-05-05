"""Economic calendar — upcoming high-impact data + central-bank events.

Goal : surface the next 7 days of releases that historically move FX +
indices, with an estimated impact-tag per asset and the historical
release date so the brain knows "release X drops on day Y at time Z".

Sources :
  - FRED `observation_date` field on key macro series : the most-recent
    obs gives us the cadence ; we project forward by adding the typical
    inter-release delta.
  - Hard-coded calendar of central-bank meeting dates 2026 (FOMC, ECB,
    BoE, BoJ) — these are scheduled annually and rarely move so a
    static table is fine until we wire in TradingEconomics.

Output : a list[CalendarEvent] with date, label, region, expected
impact tag, and the assets it historically moves.

The calendar gets two consumer paths :
  - `render_calendar_block()` for the data_pool's brain feed
  - `/v1/calendar/upcoming` REST endpoint for the dashboard

VISION_2026 — closes the "what's coming up?" gap. Every trader morning
ritual starts with ForexFactory ; we now surface that natively.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import EconomicEvent, FredObservation

Impact = Literal["high", "medium", "low"]


# Map ForexFactory currency code → (region, list of affected_assets).
# `affected_assets` are the Phase-1 8-asset universe : 5 FX majors +
# XAU + 2 indices. A USD release moves everything ; a JPY release
# only USD/JPY ; AUD only AUD/USD ; etc.
_FF_CURRENCY_MAP: dict[str, tuple[str, list[str]]] = {
    "USD": (
        "US",
        [
            "EUR_USD",
            "GBP_USD",
            "USD_JPY",
            "AUD_USD",
            "USD_CAD",
            "XAU_USD",
            "NAS100_USD",
            "SPX500_USD",
        ],
    ),
    "EUR": ("EU", ["EUR_USD"]),
    "GBP": ("UK", ["GBP_USD"]),
    "JPY": ("JP", ["USD_JPY"]),
    "AUD": ("AU", ["AUD_USD"]),
    "CAD": ("CA", ["USD_CAD"]),
    "CHF": ("CH", []),  # not in Phase-1 universe
    "NZD": ("NZ", []),
    "CNY": ("CN", []),  # CHN releases hit AUD via terms-of-trade ; not enumerated
}


@dataclass(frozen=True)
class CalendarEvent:
    """One scheduled or projected release."""

    when: date
    """UTC date of the release. Time-of-day is best-effort (text)."""
    when_time_utc: str | None
    """e.g. "13:30" for NFP, "14:00" for FOMC. None if intra-day TBD."""
    region: str
    """US / EU / UK / JP / CA / AU / GLOBAL."""
    label: str
    """Human label : "FOMC rate decision", "US CPI YoY", "ECB"."""
    impact: Impact
    affected_assets: list[str] = field(default_factory=list)
    note: str = ""
    source: str | None = None


# ────── Static calendar : FOMC, ECB, BoE, BoJ meetings 2026 ──────
# Scheduled meeting dates published at year-start. Used as ground
# truth until we wire a real TradingEconomics feed.
_CB_MEETINGS_2026: list[tuple[date, str, str, list[str]]] = [
    # (date, region, label, affected_assets)
    (
        date(2026, 1, 28),
        "US",
        "FOMC rate decision",
        ["EUR_USD", "USD_JPY", "XAU_USD", "NAS100_USD", "SPX500_USD"],
    ),
    (date(2026, 1, 23), "JP", "BoJ MPM rate decision", ["USD_JPY"]),
    (date(2026, 1, 30), "EU", "ECB rate decision", ["EUR_USD"]),
    (date(2026, 2, 5), "UK", "BoE rate decision", ["GBP_USD"]),
    (date(2026, 2, 18), "AU", "RBA minutes", ["AUD_USD"]),
    (
        date(2026, 3, 18),
        "US",
        "FOMC rate decision + SEP",
        ["EUR_USD", "USD_JPY", "XAU_USD", "NAS100_USD", "SPX500_USD"],
    ),
    (date(2026, 3, 12), "EU", "ECB rate decision", ["EUR_USD"]),
    (date(2026, 3, 19), "UK", "BoE rate decision", ["GBP_USD"]),
    (date(2026, 3, 19), "JP", "BoJ MPM rate decision", ["USD_JPY"]),
    (
        date(2026, 4, 30),
        "US",
        "FOMC rate decision",
        ["EUR_USD", "USD_JPY", "XAU_USD", "NAS100_USD", "SPX500_USD"],
    ),
    (date(2026, 4, 16), "EU", "ECB rate decision", ["EUR_USD"]),
    (date(2026, 5, 7), "UK", "BoE rate decision", ["GBP_USD"]),
    (date(2026, 5, 1), "JP", "BoJ MPM rate decision", ["USD_JPY"]),
    (
        date(2026, 6, 17),
        "US",
        "FOMC rate decision + SEP",
        ["EUR_USD", "USD_JPY", "XAU_USD", "NAS100_USD", "SPX500_USD"],
    ),
    (date(2026, 6, 4), "EU", "ECB rate decision", ["EUR_USD"]),
    (date(2026, 6, 18), "UK", "BoE rate decision", ["GBP_USD"]),
    (date(2026, 6, 19), "JP", "BoJ MPM rate decision", ["USD_JPY"]),
    (
        date(2026, 7, 29),
        "US",
        "FOMC rate decision",
        ["EUR_USD", "USD_JPY", "XAU_USD", "NAS100_USD", "SPX500_USD"],
    ),
    (date(2026, 7, 24), "EU", "ECB rate decision", ["EUR_USD"]),
    (date(2026, 8, 6), "UK", "BoE rate decision", ["GBP_USD"]),
    (date(2026, 7, 31), "JP", "BoJ MPM rate decision", ["USD_JPY"]),
    (
        date(2026, 9, 16),
        "US",
        "FOMC rate decision + SEP",
        ["EUR_USD", "USD_JPY", "XAU_USD", "NAS100_USD", "SPX500_USD"],
    ),
    (date(2026, 9, 11), "EU", "ECB rate decision", ["EUR_USD"]),
    (date(2026, 9, 17), "UK", "BoE rate decision", ["GBP_USD"]),
    (date(2026, 9, 18), "JP", "BoJ MPM rate decision", ["USD_JPY"]),
    (
        date(2026, 10, 28),
        "US",
        "FOMC rate decision",
        ["EUR_USD", "USD_JPY", "XAU_USD", "NAS100_USD", "SPX500_USD"],
    ),
    (date(2026, 10, 30), "JP", "BoJ MPM rate decision", ["USD_JPY"]),
    (
        date(2026, 12, 16),
        "US",
        "FOMC rate decision + SEP",
        ["EUR_USD", "USD_JPY", "XAU_USD", "NAS100_USD", "SPX500_USD"],
    ),
    (date(2026, 12, 11), "EU", "ECB rate decision", ["EUR_USD"]),
    (date(2026, 12, 18), "JP", "BoJ MPM rate decision", ["USD_JPY"]),
]


# ────────── Recurring monthly data series projection ──────────
# Map FRED series_id → (display_label, region, day_of_month_typical, time_utc, impact, affected_assets)
# Day-of-month is the typical release day. We use the latest observation
# date in `fred_observations` to anchor the projection ; if it's stale we
# fall back to the typical day.
_RECURRING: list[tuple[str, str, str, int, str, Impact, list[str]]] = [
    # series_id, label, region, day_of_month, time_utc, impact, affected
    (
        "PAYEMS",
        "US Non-Farm Payrolls",
        "US",
        5,
        "13:30",
        "high",
        [
            "EUR_USD",
            "GBP_USD",
            "USD_JPY",
            "AUD_USD",
            "USD_CAD",
            "XAU_USD",
            "NAS100_USD",
            "SPX500_USD",
        ],
    ),
    (
        "CPIAUCSL",
        "US CPI YoY",
        "US",
        12,
        "13:30",
        "high",
        ["EUR_USD", "USD_JPY", "XAU_USD", "NAS100_USD", "SPX500_USD"],
    ),
    ("UNRATE", "US Unemployment Rate", "US", 5, "13:30", "medium", ["EUR_USD", "USD_JPY"]),
    (
        "GDPC1",
        "US GDP QoQ (advance)",
        "US",
        28,
        "13:30",
        "high",
        ["EUR_USD", "USD_JPY", "NAS100_USD", "SPX500_USD"],
    ),
    ("UMCSENT", "U Michigan Consumer Sentiment", "US", 14, "15:00", "medium", ["EUR_USD"]),
    ("INDPRO", "US Industrial Production", "US", 17, "14:15", "low", ["NAS100_USD"]),
    ("RSAFS", "US Retail Sales", "US", 16, "13:30", "medium", ["EUR_USD", "NAS100_USD"]),
    ("PCEPILFE", "US Core PCE", "US", 30, "13:30", "high", ["EUR_USD", "USD_JPY", "XAU_USD"]),
]


@dataclass(frozen=True)
class CalendarReport:
    generated_at: datetime
    horizon_days: int
    events: list[CalendarEvent]


def _next_recurring_date(today: date, day_of_month: int) -> date:
    """Find the next occurrence of `day_of_month` from `today`."""
    if today.day < day_of_month:
        try:
            return date(today.year, today.month, day_of_month)
        except ValueError:
            # Month doesn't have that day — fall through
            pass
    # Roll to next month
    yr, mo = today.year, today.month + 1
    if mo > 12:
        mo, yr = 1, yr + 1
    try:
        return date(yr, mo, day_of_month)
    except ValueError:
        # Day of month exceeds month length — clamp to month end
        if mo == 12:
            return date(yr, mo, 31)
        last = date(yr, mo + 1, 1) - timedelta(days=1)
        return last


async def assess_calendar(session: AsyncSession, *, horizon_days: int = 14) -> CalendarReport:
    """Build the next-`horizon_days` window of high+medium events."""
    now = datetime.now(UTC)
    today = now.date()
    end = today + timedelta(days=horizon_days)
    events: list[CalendarEvent] = []

    # 1. Static central-bank meetings
    for d, region, label, affected in _CB_MEETINGS_2026:
        if today <= d <= end:
            time_utc = (
                "18:00"
                if region == "US" and "FOMC" in label
                else "12:15"
                if region == "EU"
                else "11:00"
                if region == "UK"
                else "03:00"
                if region == "JP"
                else None
            )
            events.append(
                CalendarEvent(
                    when=d,
                    when_time_utc=time_utc,
                    region=region,
                    label=label,
                    impact="high",
                    affected_assets=list(affected),
                    note="scheduled rate decision",
                    source=f"static:cb_meetings_2026:{region}",
                )
            )

    # 2. Recurring data : project from latest observation date
    for (
        series_id,
        label,
        region,
        day_of_month,
        time_utc,
        impact,
        affected,
    ) in _RECURRING:
        latest = (
            await session.execute(
                select(FredObservation.observation_date)
                .where(FredObservation.series_id == series_id)
                .order_by(desc(FredObservation.observation_date))
                .limit(1)
            )
        ).scalar_one_or_none()

        # The next release ≈ next month's day_of_month
        if latest is None:
            projected = _next_recurring_date(today, day_of_month)
        else:
            # Project from the latest obs : add roughly one month
            yr, mo = latest.year, latest.month + 1
            if mo > 12:
                mo, yr = 1, yr + 1
            try:
                projected = date(yr, mo, day_of_month)
            except ValueError:
                projected = _next_recurring_date(today, day_of_month)
            # If the projected date is already past, push another month
            while projected <= today:
                yr2, mo2 = projected.year, projected.month + 1
                if mo2 > 12:
                    mo2, yr2 = 1, yr2 + 1
                try:
                    projected = date(yr2, mo2, day_of_month)
                except ValueError:
                    projected = _next_recurring_date(projected, day_of_month)

        if today <= projected <= end:
            note = (
                f"projected from FRED:{series_id} (latest obs {latest:%Y-%m-%d})"
                if latest
                else f"projected (no FRED obs yet for {series_id})"
            )
            events.append(
                CalendarEvent(
                    when=projected,
                    when_time_utc=time_utc,
                    region=region,
                    label=label,
                    impact=impact,
                    affected_assets=list(affected),
                    note=note,
                    source=f"FRED:{series_id}",
                )
            )

    # 3. ForexFactory persisted events (economic_events table). Falls back
    # to no-op silently if the table is empty (collector not yet running).
    cutoff_now = datetime.now(UTC)
    cutoff_end = cutoff_now + timedelta(days=horizon_days)
    ff_rows = list(
        (
            await session.execute(
                select(EconomicEvent)
                .where(
                    EconomicEvent.scheduled_at.is_not(None),
                    EconomicEvent.scheduled_at >= cutoff_now,
                    EconomicEvent.scheduled_at <= cutoff_end,
                    EconomicEvent.impact.in_(("medium", "high")),
                )
                .order_by(EconomicEvent.scheduled_at.asc())
            )
        )
        .scalars()
        .all()
    )
    seen_ff_keys: set[tuple[date, str, str]] = set()
    for r in ff_rows:
        if r.scheduled_at is None:
            continue
        region, affected = _FF_CURRENCY_MAP.get(r.currency, (r.currency, []))
        when_date = r.scheduled_at.date()
        when_time = r.scheduled_at.strftime("%H:%M") if not r.is_all_day else None
        impact: Impact = "high" if r.impact == "high" else "medium"

        # Dedup against already-emitted (date, region, label) tuples
        # (the FRED + CB sources may have already inserted the same
        # release ; FF carries the consensus + previous columns).
        key = (when_date, region, r.title.lower())
        if key in seen_ff_keys:
            continue
        seen_ff_keys.add(key)
        if any(
            e.when == when_date and e.region == region and e.label.lower() == r.title.lower()
            for e in events
        ):
            continue

        note_parts: list[str] = []
        if r.forecast:
            note_parts.append(f"forecast={r.forecast}")
        if r.previous:
            note_parts.append(f"previous={r.previous}")
        note = " · ".join(note_parts) if note_parts else "from ForexFactory feed"

        events.append(
            CalendarEvent(
                when=when_date,
                when_time_utc=when_time,
                region=region,
                label=r.title,
                impact=impact,
                affected_assets=list(affected),
                note=note,
                source="forex_factory",
            )
        )

    events.sort(key=lambda e: (e.when, e.when_time_utc or "99:99"))
    return CalendarReport(generated_at=now, horizon_days=horizon_days, events=events)


def filter_for_asset(report: CalendarReport, asset: str) -> list[CalendarEvent]:
    """Subset of events that affect `asset`."""
    return [e for e in report.events if asset in e.affected_assets]


def render_calendar_block(
    report: CalendarReport,
    *,
    asset: str | None = None,
    max_items: int = 12,
) -> tuple[str, list[str]]:
    """## Economic calendar — next 14 days of high+medium events.

    If `asset` is provided, filter to events affecting it.
    """
    events = filter_for_asset(report, asset) if asset else report.events
    events = events[:max_items]
    if not events:
        scope = f" affecting {asset}" if asset else ""
        return (
            f"## Economic calendar{' (' + asset + ')' if asset else ''}\n"
            f"- (no upcoming high/medium events{scope} in the next "
            f"{report.horizon_days} days)",
            [],
        )

    title = f"## Economic calendar{f' ({asset})' if asset else ''} "
    title += f"(next {report.horizon_days} days)"
    lines = [title]
    sources: list[str] = []
    for e in events:
        impact_tag = (
            "🔴 HIGH" if e.impact == "high" else "🟡 medium" if e.impact == "medium" else "🟢 low"
        )
        time_part = f" {e.when_time_utc} UTC" if e.when_time_utc else ""
        lines.append(f"- {e.when:%Y-%m-%d}{time_part} [{e.region}] {impact_tag} · {e.label}")
        if e.note:
            lines.append(f"  · {e.note}")
        if e.source:
            sources.append(e.source)
    return "\n".join(lines), sources
