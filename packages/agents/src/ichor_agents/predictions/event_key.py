"""Deterministic comparable-event keys for cross-venue prediction markets.

The token-Jaccard matcher in ``divergence.py`` has two well-known failure
modes on the live macro universe:

1. **False positives** — two *unrelated* questions that share enough generic
   tokens to clear the Jaccard threshold (the witnessed "Brunson ↔ Vance"
   class: a sports name market spuriously matched to a political one on a
   couple of shared tokens). Eliot trades on these, so a false match is
   expensive — precision is the matcher's stated priority.
2. **Structural misalignment** — Kalshi explodes a single macro event into a
   *ladder* of per-strike markets (``KXFED-26JUN-T4.25`` = "Fed funds upper
   bound lands at 4.25 %") while Polymarket prices the *event* as one binary
   ("Will the Fed cut in June?"). Raw token overlap cannot bridge the two.

This module derives a **canonical event key** for a market from *only
deterministic, publicly-structured signals* — never a guess:

  * **Kalshi** : the structured ticker grammar ``SERIES-EVENTDATE-STRIKE``.
    The series prefix maps to a macro class (verified live 2026-06-19:
    ``KXFED``/``KXCPIYOY``/``KXU3``/``KXWRECSS`` …) and the date segment to a
    period.
  * **Polymarket / Manifold** : a small, audited set of conventionalized
    macro phrasings on the question text, each gated on an explicit period
    token (month+year, "Qn YYYY", or a bare 4-digit year for annual events).

A key is ``None`` whenever the class *or* the period cannot be pinned with
confidence — we would rather miss a key than fabricate a comparison
(ADR-017 / zero-fabrication).

How the matcher uses it
-----------------------
The key is consumed as a **precision gate**: two markets carrying two
*different* non-``None`` keys are never matched, no matter their token
overlap. That is a pure tightening (it can only *remove* spurious matches),
which is why it is safe.

What this module deliberately does **not** do
---------------------------------------------
It does not attempt to *fuse* a Kalshi strike ladder into a Polymarket
binary. Turning ``KXFED`` strikes into an implied ``P(cut)`` needs a
ladder→event reduction (sum the YES mass of the strikes below the current
rate) that carries real semantic risk; that recall-adding step is a separate,
flag-gated concern. Here, ``fed_rate`` strikes share a *class+period* key so
they are grouped/deduped and never cross-matched to an unrelated event — but
a Kalshi strike and a Polymarket binary are kept distinguishable by the
``laddered`` flag on the key so the consumer never blindly fuses them.
"""

from __future__ import annotations

import re
from typing import Literal

Venue = Literal["polymarket", "kalshi", "manifold"]

# Macro event classes the three venues conventionally co-price. Kept tight on
# purpose: only classes with a stable, auditable phrasing/ticker signature.
EventClass = Literal[
    "fed_rate",
    "cpi",
    "unemployment",
    "recession",
    "gdp",
]

# Classes whose Kalshi representation is a per-strike *ladder* rather than a
# single binary equivalent to the Polymarket/Manifold question. A key in one
# of these classes is tagged ``laddered`` so the consumer never fuses a single
# strike's YES price with a binary "will it happen?" price (see module
# docstring — that reduction is out of scope here).
_LADDERED_CLASSES: frozenset[EventClass] = frozenset({"fed_rate", "cpi", "unemployment", "gdp"})

# Classes priced as an *annual* event (resolves over a calendar year, phrased
# by the year on Polymarket but sometimes carrying a resolution month in the
# Kalshi ticker). Their period is normalized to the **year only** on every
# venue, so a Kalshi ``KXWRECSS-26DEC`` market and a Polymarket "US recession
# in 2026?" share ``recession:2026`` instead of diverging on a fabricated
# month. All other classes key on year-month.
_ANNUAL_CLASSES: frozenset[EventClass] = frozenset({"recession"})


def _normalize_period(klass: EventClass, year: int, month: int | None) -> str:
    """``YYYY`` for annual classes, ``YYYY-MM`` otherwise (when a month is
    known). Annual classes drop any month so the venues coincide on the year.
    """
    if klass in _ANNUAL_CLASSES or month is None:
        return f"{year:04d}"
    return f"{year:04d}-{month:02d}"


# ───────────────────────── Kalshi ticker grammar ───────────────────────────
# Verified live 2026-06-19 (collectors/kalshi.py MACRO_SERIES). Tickers look
# like ``KXFED-26JUN-T4.25`` / ``KXU3-26JUN-...`` / ``KXWRECSS-26-...``.
_KALSHI_SERIES_CLASS: dict[str, EventClass] = {
    "KXFED": "fed_rate",
    "KXFEDDECISION": "fed_rate",
    "KXFOMC": "fed_rate",
    "KXCPIYOY": "cpi",
    "KXCPI": "cpi",
    "KXCPICORE": "cpi",
    "KXU3": "unemployment",
    "KXUE": "unemployment",
    "KXUNRATE": "unemployment",
    "KXWRECSS": "recession",
    "KXRECSS": "recession",
    "KXRECSSNBER": "recession",
    "KXGDP": "gdp",
}

_MONTH_ABBR: dict[str, int] = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}

_MONTH_NAME: dict[str, int] = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    # common abbreviations seen in market titles
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sept": 9,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

# A 2-digit-year + 3-letter-month segment, e.g. ``26JUN`` in KXFED-26JUN-T4.25.
_KALSHI_YYMMM = re.compile(r"\b(\d{2})([A-Z]{3})\b")
# A bare 2-digit-year event segment, e.g. ``KXWRECSS-26-...`` (annual events).
_KALSHI_YY_ONLY = re.compile(r"^-?(\d{2})(?:-|$)")


def kalshi_event_key(ticker: str) -> str | None:
    """Derive a canonical event key from a Kalshi market ticker.

    Returns ``"<class>:<period>"`` (period = ``YYYY-MM`` or ``YYYY``), or
    ``None`` if the series prefix is not a known macro class or no period can
    be parsed. Pure string parsing of the public ticker grammar — no guess.
    """
    if not ticker:
        return None
    parts = ticker.upper().split("-")
    series = parts[0]
    klass = _KALSHI_SERIES_CLASS.get(series)
    if klass is None:
        return None

    rest = "-".join(parts[1:])
    # Preferred: an explicit YYMMM event segment (monthly cadence).
    m = _KALSHI_YYMMM.search(rest)
    if m is not None:
        month = _MONTH_ABBR.get(m.group(2))
        if month is not None:
            return f"{klass}:{_normalize_period(klass, 2000 + int(m.group(1)), month)}"

    # Fallback: a bare 2-digit year segment (annual events, e.g. recession).
    y = _KALSHI_YY_ONLY.search("-" + rest)
    if y is not None:
        return f"{klass}:{_normalize_period(klass, 2000 + int(y.group(1)), None)}"

    return None


# ───────────────────────── Question-text patterns ──────────────────────────
# Conventionalized macro phrasings (Polymarket/Manifold are English-first).
# Each entry: (class, keyword-regex). The keyword regex must match for the
# class to be considered; the period is parsed separately and is mandatory.
_TEXT_CLASS_PATTERNS: list[tuple[EventClass, re.Pattern[str]]] = [
    (
        "fed_rate",
        re.compile(
            r"\b(fed|fomc|federal reserve|federal funds)\b.*\b"
            r"(rate|cut|hike|raise|hold|lower|decision|bps|basis point|bp)s?\b",
        ),
    ),
    ("cpi", re.compile(r"\b(cpi|inflation rate|consumer price)\b")),
    ("unemployment", re.compile(r"\b(unemployment|jobless|u-?3|nonfarm|payrolls?)\b")),
    ("recession", re.compile(r"\brecession\b")),
    ("gdp", re.compile(r"\b(gdp|gross domestic product)\b")),
]

_MONTH_YEAR_RE = re.compile(
    r"\b(january|february|march|april|may|june|july|august|september|october|"
    r"november|december|jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec)\b"
    r"[^0-9]{0,12}(20\d{2})",
)
_YEAR_MONTH_RE = re.compile(
    r"\b(20\d{2})[^0-9]{0,12}"
    r"(january|february|march|april|may|june|july|august|september|october|"
    r"november|december|jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec)\b",
)
_QUARTER_RE = re.compile(r"\bq([1-4])\b[^0-9]{0,6}(20\d{2})", re.IGNORECASE)
_BARE_YEAR_RE = re.compile(r"\b(20\d{2})\b")


def _period_from_text(text: str, klass: EventClass) -> str | None:
    """Parse a class-aware period from question text.

    *Annual* classes resolve to the **year** taken from any of month+year,
    quarter+year, or a bare 4-digit year. *Dated* (monthly) classes require a
    month (either order with the year) → ``YYYY-MM``, or a quarter →
    ``YYYY-qN`` (a quarter is **not** collapsed to a month, to avoid a
    fabricated month match: "Q2 2026" ≠ "June 2026"). A bare year alone is not
    enough for a dated class → ``None``.
    """
    annual = klass in _ANNUAL_CLASSES

    m = _MONTH_YEAR_RE.search(text)
    if m is not None:
        month = _MONTH_NAME.get(m.group(1))
        if month is not None:
            return _normalize_period(klass, int(m.group(2)), month)
    m = _YEAR_MONTH_RE.search(text)
    if m is not None:
        month = _MONTH_NAME.get(m.group(2))
        if month is not None:
            return _normalize_period(klass, int(m.group(1)), month)
    q = _QUARTER_RE.search(text)
    if q is not None:
        year = int(q.group(2))
        return f"{year:04d}" if annual else f"{year:04d}-q{q.group(1)}"
    if annual:
        y = _BARE_YEAR_RE.search(text)
        if y is not None:
            return _normalize_period(klass, int(y.group(1)), None)
    return None


def text_event_key(question: str) -> str | None:
    """Derive a canonical event key from a market's question text.

    Returns ``"<class>:<period>"`` or ``None``. The class must match a
    conventionalized macro pattern *and* a class-appropriate period must be
    present; otherwise ``None`` (never a guess). Annual classes (recession)
    accept a bare 4-digit year; dated classes require a month or quarter.
    """
    if not question:
        return None
    low = question.lower()
    for klass, pat in _TEXT_CLASS_PATTERNS:
        if pat.search(low):
            period = _period_from_text(low, klass)
            if period is not None:
                return f"{klass}:{period}"
            return None  # right class, no confident period → no key
    return None


def event_key(venue: Venue, market_id: str, question: str) -> str | None:
    """Best deterministic comparable-event key for a market, or ``None``.

    Kalshi is keyed off its structured ticker first (most reliable), falling
    back to the question text. Polymarket/Manifold use the question text only.
    """
    if venue == "kalshi":
        return kalshi_event_key(market_id) or text_event_key(question)
    return text_event_key(question)


def event_class_of(key: str | None) -> EventClass | None:
    """Extract the class component of a key (``"fed_rate:2026-06"`` →
    ``"fed_rate"``), or ``None``."""
    if not key:
        return None
    klass = key.split(":", 1)[0]
    return klass if klass in _KALSHI_SERIES_CLASS.values() else None  # type: ignore[return-value]


def is_laddered_key(key: str | None) -> bool:
    """True when the key's class is priced as a per-strike ladder on Kalshi
    (so a single strike's YES must not be fused with a binary event price)."""
    klass = event_class_of(key)
    return klass in _LADDERED_CLASSES if klass is not None else False
