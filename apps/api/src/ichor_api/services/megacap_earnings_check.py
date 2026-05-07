"""MEGACAP_EARNINGS_T-1 alert wiring (Phase D.5.f).

The Magnificent 7 (AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA) account for
~27% of S&P 500 earnings power in 2026 (per Zacks Director of Research
Sheraz Mian). On the day before any one of them reports, the entire
US equity complex repositions :

  - Vol skew steepens on SPX/NDX
  - Cross-asset hedges adjust (USD haven bid if expected miss, NDX
    futures sell-off if guidance soft)
  - Dealer gamma can flip near earnings expirations
  - Trader needs explicit T-1 advance warning to avoid being caught
    on the wrong side of a binary catalyst

This service queries `yfinance` live for each Mag-7 ticker's next
confirmed earnings date and fires `MEGACAP_EARNINGS_T-1` when any
ticker has earnings within `EARNINGS_PROXIMITY_FLOOR = 1` business
day (i.e. tomorrow or today).

Architecture choices :
  - Live yfinance call rather than hardcoded calendar : earnings
    confirmations move within a 1-week window even when announced
    in advance (companies sometimes shift dates for earnings transcripts
    timing). Live fetch ensures we use the company-confirmed date when
    available.
  - Defensive try/except : yfinance can fail (Yahoo rate limits, network
    glitches). On failure for a ticker, that ticker is silently skipped
    (logged WARNING) — the alert still fires for any other ticker that
    has a fresh date. Multi-failure detection is left to ops monitoring
    (`/metrics` Prometheus + journald).

Source-stamping (ADR-017) :
  - extra_payload.source = "yfinance:earnings_calendar"
  - extra_payload includes the ticker, its earnings_date, days_to_event,
    and the timestamp of the yfinance fetch for audit drill-back.

Cron : daily 14h Paris (post US pre-market data, before US session
opens at 15h30 Paris).

ROADMAP D.5.f. ADR-038.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from .alerts_runner import check_metric

log = structlog.get_logger(__name__)

# The Magnificent 7 — top US mega-caps by earnings impact on S&P 500.
# Order matters for output stability ; sorted by typical Q-end reporting
# date (Tesla earliest, NVDA latest).
MEGACAP_TICKERS: tuple[str, ...] = (
    "TSLA",
    "GOOGL",
    "MSFT",
    "META",
    "AAPL",
    "AMZN",
    "NVDA",
)

# Threshold mirrors the catalog default (`MEGACAP_EARNINGS_T-1`
# AlertDef default_threshold=1). Single source of truth via test
# test_threshold_constant_matches_catalog.
EARNINGS_PROXIMITY_FLOOR: int = 1

# How far in the future to look. yfinance returns the *next* earnings
# date — typically within 90 days. We don't fire for events further than
# this : the alert is "imminent earnings" not "earnings season is coming".
LOOKAHEAD_DAYS: int = 60


@dataclass(frozen=True)
class TickerEarnings:
    """One ticker's next-earnings observation."""

    ticker: str
    earnings_date: date | None
    """None if yfinance returned no future earnings or failed."""

    days_to_event: int | None
    """None if earnings_date is None or in the past."""

    note: str = ""


@dataclass(frozen=True)
class MegacapEarningsResult:
    """One run summary."""

    today: date
    tickers_evaluated: int
    tickers_with_date: int
    """How many tickers returned a valid future earnings date."""

    tickers_alerting: int
    """How many tickers fired (days_to_event <= EARNINGS_PROXIMITY_FLOOR)."""

    alerts_fired: list[str]
    """List of `<ticker>=T-<n>` strings for the alerts persisted."""

    per_ticker: list[TickerEarnings] = field(default_factory=list)


def _fetch_next_earnings_date(ticker: str, *, today: date) -> date | None:
    """Query yfinance for the next confirmed earnings date for `ticker`.

    Returns None on any failure (network, rate-limit, missing column).
    The caller must tolerate a None — it means "we don't know" not "no
    earnings". A ticker silently skipped should NOT fire.
    """
    try:
        # Lazy import so unit tests can monkey-patch the module without
        # forcing the heavy yfinance/pandas import on test collection.
        import yfinance as yf

        t = yf.Ticker(ticker)
        cal = t.calendar
        if cal is None:
            return None

        # yfinance 1.3.x returns either a dict with "Earnings Date" key
        # holding a list[datetime|date], or a pandas DataFrame with the
        # same column. Handle both shapes defensively.
        dates: list[Any] = []
        if isinstance(cal, dict):
            raw = cal.get("Earnings Date", [])
            if isinstance(raw, list):
                dates = list(raw)
            else:
                dates = [raw]
        else:
            # DataFrame fallback (older yfinance versions)
            try:
                if not cal.empty and "Earnings Date" in cal.index:
                    series = cal.loc["Earnings Date"]
                    dates = list(series.dropna())
            except (AttributeError, KeyError, TypeError):
                dates = []

        future_dates: list[date] = []
        for d in dates:
            if isinstance(d, datetime):
                candidate = d.date()
            elif isinstance(d, date):
                candidate = d
            else:
                # Some yfinance versions return numpy datetime64 ; coerce
                # via str then ISO parse.
                try:
                    s = str(d)[:10]
                    candidate = date.fromisoformat(s)
                except (ValueError, TypeError):
                    continue
            if today <= candidate <= today + timedelta(days=LOOKAHEAD_DAYS):
                future_dates.append(candidate)

        return min(future_dates) if future_dates else None
    except Exception as e:  # noqa: BLE001
        log.warning("megacap.yfinance_failed", ticker=ticker, error=str(e))
        return None


async def evaluate_megacap_earnings(
    session: AsyncSession,
    *,
    persist: bool = True,
    today: date | None = None,
) -> MegacapEarningsResult:
    """Iterate over the 7 Mag-7 tickers, fetch each next earnings date,
    fire `MEGACAP_EARNINGS_T-1` when proximity <= EARNINGS_PROXIMITY_FLOOR.

    Returns a structured result so the CLI can print a one-liner per run.
    """
    today = today or datetime.now(UTC).date()

    per_ticker: list[TickerEarnings] = []
    alerts_fired: list[str] = []

    for ticker in MEGACAP_TICKERS:
        edate = _fetch_next_earnings_date(ticker, today=today)
        if edate is None:
            per_ticker.append(
                TickerEarnings(
                    ticker=ticker,
                    earnings_date=None,
                    days_to_event=None,
                    note="no future earnings date from yfinance",
                )
            )
            continue

        days_to_event = (edate - today).days
        per_ticker.append(
            TickerEarnings(
                ticker=ticker,
                earnings_date=edate,
                days_to_event=days_to_event,
            )
        )

        # Fire if we are within EARNINGS_PROXIMITY_FLOOR (today is T-N
        # where N <= floor). days_to_event = 0 means earnings TODAY, =1
        # means tomorrow, etc.
        if 0 <= days_to_event <= EARNINGS_PROXIMITY_FLOOR and persist:
            await check_metric(
                session,
                metric_name="megacap_t_minus_days",
                current_value=float(days_to_event),
                asset=ticker,  # asset-specific so trader sees which ticker
                extra_payload={
                    "ticker": ticker,
                    "earnings_date": edate.isoformat(),
                    "days_to_event": days_to_event,
                    "fetched_at": datetime.now(UTC).isoformat(),
                    "source": "yfinance:earnings_calendar",
                },
            )
            alerts_fired.append(f"{ticker}=T-{days_to_event}")
        elif 0 <= days_to_event <= EARNINGS_PROXIMITY_FLOOR:
            # persist=False — record we WOULD have fired
            alerts_fired.append(f"{ticker}=T-{days_to_event}")

    return MegacapEarningsResult(
        today=today,
        tickers_evaluated=len(MEGACAP_TICKERS),
        tickers_with_date=sum(
            1 for t in per_ticker if t.earnings_date is not None
        ),
        tickers_alerting=len(alerts_fired),
        alerts_fired=alerts_fired,
        per_ticker=per_ticker,
    )
