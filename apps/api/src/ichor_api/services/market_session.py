"""Market session + holiday awareness (ADR-099 Tier 1.3).

Pure-compute, ZERO new dependency (Python 3.12 stdlib `zoneinfo` is
DST-correct). Eliot's explicit requirement : "savoir quand il y a jour
ferié mais aussi le weekend pour adapter". The 4-pass timers fire 365
d/yr ; this module is the honest signal the dashboard surfaces instead
of the crude DST-naive UTC heuristic that was in SessionStatus.tsx.

Scope (YAGNI — exactly the 5-asset briefing universe) :
  - FX / XAU trade 24/5 → closed weekends only.
  - SPX500 / NAS100 are US equities → closed weekends AND US market
    (NYSE/Nasdaq) holidays.
  US holidays are computed by the STANDARD rules (fixed dates + nth-
  weekday + Good Friday via the Anonymous Gregorian Easter computus +
  the NYSE Sat→Fri / Sun→Mon observed shift, incl. the New-Year-Saturday
  no-Friday-observance exception). Nothing is hand-fabricated.

ADR-017 : pure calendar facts. No bias, no BUY/SELL.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
NY = ZoneInfo("America/New_York")

# London cash open is 08:00 London == 09:00 Paris all year (London is
# always Paris−1h). NY open 09:30 ET is converted via zoneinfo (the
# ET↔Paris offset is NOT a constant — brief DST-mismatch windows exist).
_LONDON_OPEN_PARIS_H = 9
_NY_OPEN_ET = (9, 30)


def _easter(year: int) -> date:
    """Anonymous Gregorian algorithm (exact, standard)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month = (h + ell - 7 * m + 114) // 31
    day = ((h + ell - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """n-th `weekday` (Mon=0) of month. n=-1 → last."""
    if n > 0:
        d = date(year, month, 1)
        offset = (weekday - d.weekday()) % 7
        return d + timedelta(days=offset + 7 * (n - 1))
    # last
    if month == 12:
        nxt = date(year + 1, 1, 1)
    else:
        nxt = date(year, month + 1, 1)
    d = nxt - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def _observed(d: date, *, is_new_year: bool = False) -> date:
    """NYSE observed shift: Sat→Fri, Sun→Mon. Exception: New Year's Day
    on a Saturday is NOT observed the preceding Friday."""
    if d.weekday() == 5:  # Saturday
        return d if is_new_year else d - timedelta(days=1)
    if d.weekday() == 6:  # Sunday
        return d + timedelta(days=1)
    return d


def us_market_holidays(year: int) -> dict[date, str]:
    """NYSE/Nasdaq full-day holidays for `year` (observed dates)."""
    gf = _easter(year) - timedelta(days=2)
    raw: list[tuple[date, str, bool]] = [
        (_observed(date(year, 1, 1), is_new_year=True), "New Year's Day", False),
        (_nth_weekday(year, 1, 0, 3), "Martin Luther King Jr. Day", True),
        (_nth_weekday(year, 2, 0, 3), "Washington's Birthday", True),
        (gf, "Good Friday", True),
        (_nth_weekday(year, 5, 0, -1), "Memorial Day", True),
        (_observed(date(year, 6, 19)), "Juneteenth", False),
        (_observed(date(year, 7, 4)), "Independence Day", False),
        (_nth_weekday(year, 9, 0, 1), "Labor Day", True),
        (_nth_weekday(year, 11, 3, 4), "Thanksgiving", True),
        (_observed(date(year, 12, 25)), "Christmas Day", False),
    ]
    return {d: name for d, name, _exact in raw}


@dataclass(frozen=True)
class SessionStatus:
    now_paris: datetime
    weekday: str
    state: str  # weekend|us_holiday|pre_londres|london_active|pre_ny|ny_active|off_hours
    market_closed_fx: bool
    market_closed_us_equity: bool
    holiday_name: str | None
    next_open_label: str
    next_open_paris: datetime
    minutes_until_next_open: int

    def to_dict(self) -> dict:
        return {
            "now_paris": self.now_paris.isoformat(),
            "weekday": self.weekday,
            "state": self.state,
            "market_closed_fx": self.market_closed_fx,
            "market_closed_us_equity": self.market_closed_us_equity,
            "holiday_name": self.holiday_name,
            "next_open_label": self.next_open_label,
            "next_open_paris": self.next_open_paris.isoformat(),
            "minutes_until_next_open": self.minutes_until_next_open,
        }


def _ny_open_paris(d: date) -> datetime:
    """09:30 ET on day `d`, expressed in Paris tz (DST-correct)."""
    et = datetime(d.year, d.month, d.day, _NY_OPEN_ET[0], _NY_OPEN_ET[1], tzinfo=NY)
    return et.astimezone(PARIS)


def _next_fx_reopen(now: datetime) -> datetime:
    """FX reopens Sunday ~22:00 Paris (Sydney open). Approximation —
    FX has no single canonical reopen instant (22:00-23:00 Paris)."""
    d = now.date()
    while d.weekday() != 6:  # Sunday
        d += timedelta(days=1)
    return datetime(d.year, d.month, d.day, 22, 0, tzinfo=PARIS)


def _next_business_day(d: date, holidays: dict[date, str]) -> date:
    nd = d + timedelta(days=1)
    while nd.weekday() >= 5 or nd in holidays:
        nd += timedelta(days=1)
    return nd


def compute_session_status(now: datetime | None = None) -> SessionStatus:
    now = (now or datetime.now(PARIS)).astimezone(PARIS)
    today = now.date()
    wd = now.weekday()  # Mon=0 .. Sun=6
    weekday_name = now.strftime("%A")

    hols = us_market_holidays(today.year)
    us_hol_name = hols.get(today)

    # Weekend (FX) : Sat all day + Sun before 22:00 Paris (Sydney reopen).
    is_fx_weekend = wd == 5 or (wd == 6 and now.hour < 22)

    if is_fx_weekend:
        reopen = _next_fx_reopen(now)
        return SessionStatus(
            now_paris=now,
            weekday=weekday_name,
            state="weekend",
            market_closed_fx=True,
            market_closed_us_equity=True,
            holiday_name=None,
            next_open_label="Réouverture FX (Sydney, dim. ~22:00 Paris)",
            next_open_paris=reopen,
            minutes_until_next_open=max(0, int((reopen - now).total_seconds() // 60)),
        )

    if us_hol_name is not None:
        # FX/XAU still trade ; only US equities (SPX/NAS) are closed.
        nbd = _next_business_day(today, hols)
        nopen = _ny_open_paris(nbd)
        return SessionStatus(
            now_paris=now,
            weekday=weekday_name,
            state="us_holiday",
            market_closed_fx=False,
            market_closed_us_equity=True,
            holiday_name=us_hol_name,
            next_open_label=f"Marchés US fermés ({us_hol_name}) · FX/XAU ouverts",
            next_open_paris=nopen,
            minutes_until_next_open=max(0, int((nopen - now).total_seconds() // 60)),
        )

    london_open = now.replace(hour=_LONDON_OPEN_PARIS_H, minute=0, second=0, microsecond=0)
    ny_open = _ny_open_paris(today)
    hm = now.hour * 60 + now.minute

    def mins_to(target: datetime) -> int:
        return max(0, int((target - now).total_seconds() // 60))

    if hm < _LONDON_OPEN_PARIS_H * 60:
        if now.hour >= 6:
            state, label, target = "pre_londres", "Ouverture Londres (09:00 Paris)", london_open
        else:
            state, label, target = (
                "off_hours",
                "Pré-Londres (06:00 Paris)",
                now.replace(hour=6, minute=0, second=0, microsecond=0),
            )
    elif now < ny_open and (ny_open - now).total_seconds() <= 3.5 * 3600:
        state, label, target = "pre_ny", "Ouverture New York", ny_open
    elif now < ny_open:
        state, label, target = "london_active", "Ouverture New York", ny_open
    elif now.hour < 22:
        state, label, target = "ny_active", "Réouverture FX (dim.)", _next_fx_reopen(now)
    else:
        nxt = _next_business_day(today, hols)
        state, label, target = (
            "off_hours",
            "Pré-Londres (06:00 Paris)",
            datetime(nxt.year, nxt.month, nxt.day, 6, 0, tzinfo=PARIS),
        )

    return SessionStatus(
        now_paris=now,
        weekday=weekday_name,
        state=state,
        market_closed_fx=False,
        market_closed_us_equity=False,
        holiday_name=None,
        next_open_label=label,
        next_open_paris=target,
        minutes_until_next_open=mins_to(target),
    )
