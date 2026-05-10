"""TARIFF_SHOCK alert wiring (Phase D.5.b.2).

Detects bursts of tariff / trade-war narrative in GDELT 2.0 article
flow. The 2026 macro context is exceptional :

  - SCOTUS 2026-02-20 invalidated IEEPA-based "Liberation Day" tariffs
  - USTR pivoted to **76 simultaneous Section 301 investigations**
    (March 2026) — unprecedented (avg <3/year over the 50-year history
    of the statute)
  - Section 122 BOP 10% surcharge expires 2026-07-24 unless extended
  - Tariff stack now layers Section 301 + Section 232 + Section 122
    + residual IEEPA, with effective duties on China-origin goods
    above 50%

Tariff narrative shocks drive USD/CNH, USD/MXN, EUR/USD, gold, equity
risk premia. A single Trump tweet or USTR press release can shift the
landscape mid-session.

This service converts the GDELT article flow into a tradable alert :

  1. Filter gdelt_events.title for tariff narrative keywords
     (tariff, trade war, Section 301, USTR, protectionism, reciprocal
     tariff, IEEPA, Section 232, ART program, Liberation Day, etc.)
  2. Group filtered articles by UTC date
  3. Z-score today's count against trailing 30d daily count baseline
  4. Compute avg(tone) on today's tariff articles
  5. Fire TARIFF_SHOCK iff count_z >= 2.0 AND avg_tone <= -1.5

The combined gate (count anomaly + negative tone) is the standard
pattern from GDELT sentiment-burst research : count alone catches
benign repetition (newswire boilerplate) ; tone alone fluctuates
on style. Together they identify *agitated* tariff coverage at scale.

Source-stamping (ADR-017) :
  - extra_payload.source = "gdelt:tariff_filter"
  - extra_payload includes today_count, baseline_mean/std, n_history,
    avg_tone_today, n_articles_today, sample of matched titles (capped),
    and the keyword list used.

ROADMAP D.5.b. ADR-037.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import GdeltEvent
from .alerts_runner import check_metric

# Tariff narrative keywords (SQL pre-filter shortlist). ILIKE %kw% in
# Postgres is permissive and over-fetches : e.g. `ustr` matches inside
# `industrial` / `industry`. We apply a strict Python regex post-filter
# with word boundaries to reject those false positives before counting.
#
# List built from 2026 macro research :
#   - SCOTUS Learning Resources v Trump (2026-02-20) — IEEPA pivot
#   - USTR Section 301 wave (76 simultaneous investigations, March 2026)
#   - Section 122 BOP 10% surcharge (expires 2026-07-24)
#   - Section 321 de minimis exemption ended Aug 2025 / postal Feb 2026
#   - CFIUS inbound investment review (foreign-control acquisitions)
#   - E.O. 14105 + COINS Act NDAA FY2026 outbound investment regime
#   - BIS Entity List enforcement
#   - BIOSECURE Act (China biotech outbound)
TARIFF_KEYWORDS: tuple[str, ...] = (
    "tariff",
    "trade war",
    "trade-war",
    "section 301",
    "section 232",
    "section 122",
    "section 321",  # de minimis exemption (Tariff Act 1930)
    "ustr",
    "protectionism",
    "reciprocal tariff",
    "ieepa",
    "art program",
    "liberation day",
    "import dut",  # catches "import duty" + "import duties"
    "trade dispute",
    "trade tension",
    "trade barrier",
    "de minimis",  # Section 321 exemption end (Aug 2025 / Feb 2026 postal)
    "cfius",  # Committee on Foreign Investment in the US
    "outbound investment",  # E.O. 14105 / COINS Act
    "entity list",  # BIS Entity List
    "biosecure",  # BIOSECURE Act (China biotech outbound)
)

# Strict regex post-filter — applied in Python AFTER the SQL ILIKE
# pre-filter to reject substring-collision false positives. Each pattern
# uses word boundaries (\b) where appropriate. Acronyms (USTR, IEEPA,
# CFIUS) are case-SENSITIVE because the lowercase form only appears inside
# longer words ("industrial", "ieep ASSAS" etc) — never as standalone
# tokens in news copy.
_TARIFF_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\btariff", re.IGNORECASE),  # tariff, tariffs, tariff-related
    re.compile(r"\btrade[ -]war", re.IGNORECASE),  # trade war, trade-war, trade-warring
    re.compile(r"\bsection 301\b", re.IGNORECASE),
    re.compile(r"\bsection 232\b", re.IGNORECASE),
    re.compile(r"\bsection 122\b", re.IGNORECASE),
    re.compile(r"\bsection 321\b", re.IGNORECASE),
    re.compile(r"\bUSTR\b"),  # case-SENSITIVE — `ustr` inside `industrial` is a false positive
    re.compile(r"\bprotectionism\b", re.IGNORECASE),
    re.compile(r"\breciprocal tariff", re.IGNORECASE),  # + plural
    re.compile(r"\bIEEPA\b"),  # case-SENSITIVE
    re.compile(
        r"\bART program\b"
    ),  # case-SENSITIVE — `art program` collides with `smart program` etc
    re.compile(r"\bLiberation Day\b", re.IGNORECASE),
    re.compile(r"\bimport (?:duty|duties)\b", re.IGNORECASE),
    re.compile(r"\btrade dispute", re.IGNORECASE),
    re.compile(r"\btrade tension", re.IGNORECASE),
    re.compile(r"\btrade barrier", re.IGNORECASE),
    re.compile(r"\bde minimis\b", re.IGNORECASE),  # Section 321 exemption end
    re.compile(r"\bCFIUS\b"),  # case-SENSITIVE acronym
    re.compile(r"\boutbound investment", re.IGNORECASE),  # E.O. 14105 / COINS Act
    re.compile(r"\bentity list\b", re.IGNORECASE),  # BIS Entity List
    re.compile(r"\bBIOSECURE\b", re.IGNORECASE),  # BIOSECURE Act
)


def _title_matches_tariff(title: str) -> bool:
    """Strict regex check : title contains ANY tariff pattern with proper
    word boundaries. Used as Python post-filter after the permissive SQL
    ILIKE pre-fetch — rejects substring-collision false positives like
    `ustr` matching `industrial`."""
    return any(p.search(title) for p in _TARIFF_PATTERNS)


# Trailing distribution length for the count z-score.
COUNT_ZSCORE_WINDOW_DAYS = 30

# Threshold mirrors the catalog default (`TARIFF_SHOCK` AlertDef
# default_threshold=2.0). Single source of truth via test
# test_threshold_constant_matches_catalog.
ALERT_COUNT_Z_FLOOR: float = 2.0

# Tone is a GDELT VADER-lexicon score in [-10, +10]. Research
# (knowledge4policy.ec.europa.eu Socioeconomic Tracker, GDELT GEG
# benchmarks) indicates avg-tone <= -1.5 corresponds to clearly
# "agitated" reporting. Combined with the count anomaly, this gate
# eliminates false positives from neutral-tone newswire repetition.
AVG_TONE_NEG_FLOOR: float = -1.5

# Minimum sample for a credible z-score on the count series.
_MIN_ZSCORE_HISTORY = 14

# Cap on title sample reported in extra_payload — keep audit log compact.
_TITLE_SAMPLE_CAP = 5


@dataclass(frozen=True)
class TariffShockResult:
    """One run summary."""

    today_count: int
    """Count of tariff-filter-matching articles in the last 24h."""

    baseline_mean: float | None
    """Mean of trailing 30d daily counts (excluding today)."""

    baseline_std: float | None
    """Std of trailing 30d daily counts (excluding today)."""

    count_z: float | None
    """Z-score of today_count vs baseline."""

    avg_tone_today: float | None
    """Mean GDELT tone on today's tariff articles (None if no articles)."""

    n_history: int
    """Number of historical days used for baseline."""

    n_articles_today: int
    """Articles parsed today (== today_count, exposed for clarity)."""

    alert_fired: bool

    note: str = ""

    title_sample: list[str] = field(default_factory=list)
    """Up to _TITLE_SAMPLE_CAP titles from today's matches (lowercased
    elsewhere is fine — keep verbatim here for audit drill-back)."""


async def _fetch_tariff_articles(
    session: AsyncSession,
    *,
    days: int,
) -> list[tuple[datetime, str, float]]:
    """Pull gdelt_events from the last `days`, title matching ANY tariff
    keyword (case-insensitive). Returns (seendate, title, tone) tuples
    oldest-first.

    Two-stage filter :
      1. SQL ILIKE on TARIFF_KEYWORDS — permissive pre-fetch (catches
         everything we might want, including some substring collisions)
      2. Python regex on _TARIFF_PATTERNS — strict word-boundary check
         that rejects false positives like `ustr` matching `industrial`
    """
    cutoff = datetime.now(UTC) - timedelta(days=days)
    filters = or_(*(GdeltEvent.title.ilike(f"%{kw}%") for kw in TARIFF_KEYWORDS))
    stmt = (
        select(GdeltEvent.seendate, GdeltEvent.title, GdeltEvent.tone)
        .where(GdeltEvent.seendate >= cutoff, filters)
        .order_by(GdeltEvent.seendate.asc())
    )
    rows = (await session.execute(stmt)).all()
    # Strict Python post-filter to reject substring-collision false positives
    return [(r[0], r[1], float(r[2])) for r in rows if _title_matches_tariff(r[1])]


def _bucket_by_day(
    articles: list[tuple[datetime, str, float]],
    *,
    today: date,
) -> tuple[int, list[float], int, list[float], list[str]]:
    """Bucket articles into (today_count, history_counts, today_n, today_tones, today_titles).

    `history_counts` covers the trailing 30d EXCLUDING today (so the z-score
    is against an unbiased baseline). Empty days are filled with 0 counts.
    """
    # Initialise daily buckets for the 30 days prior to today
    history_buckets: dict[date, int] = {
        today - timedelta(days=d): 0 for d in range(1, COUNT_ZSCORE_WINDOW_DAYS + 1)
    }
    today_count = 0
    today_tones: list[float] = []
    today_titles: list[str] = []
    for seen_dt, title, tone in articles:
        d = seen_dt.date()
        if d == today:
            today_count += 1
            today_tones.append(tone)
            if len(today_titles) < _TITLE_SAMPLE_CAP:
                today_titles.append(title)
        elif d in history_buckets:
            history_buckets[d] += 1
        # Articles older than 30d are silently ignored (caller fetched a
        # buffered window — defensive)

    history_counts = [history_buckets[d] for d in sorted(history_buckets.keys())]
    return today_count, history_counts, today_count, today_tones, today_titles


def _zscore(
    history: list[float],
    current: float,
) -> tuple[float | None, float | None, float | None]:
    """(z, mean, std) of `current` against `history`. None on degenerate input.

    History is the daily counts of the last 30d EXCLUDING today.
    """
    n = len(history)
    if n < _MIN_ZSCORE_HISTORY:
        return None, None, None
    mean = sum(history) / n
    var = sum((v - mean) ** 2 for v in history) / n
    std = math.sqrt(var)
    if std == 0:
        return None, mean, std
    return (current - mean) / std, mean, std


async def evaluate_tariff_shock(
    session: AsyncSession,
    *,
    persist: bool = True,
    today: date | None = None,
) -> TariffShockResult:
    """Compute the tariff narrative count z-score + avg tone, fire
    TARIFF_SHOCK iff count_z >= ALERT_COUNT_Z_FLOOR AND avg_tone <=
    AVG_TONE_NEG_FLOOR.

    Returns a structured result so the CLI can print a one-liner.
    """
    today = today or datetime.now(UTC).date()

    # Fetch with a small buffer beyond the 30d window
    articles = await _fetch_tariff_articles(session, days=COUNT_ZSCORE_WINDOW_DAYS + 7)

    today_count, history, n_today, today_tones, today_titles = _bucket_by_day(articles, today=today)

    avg_tone_today: float | None = (
        round(sum(today_tones) / len(today_tones), 3) if today_tones else None
    )

    # Build a float-list view of history for the z-score helper
    history_floats = [float(c) for c in history]
    z, mean, std = _zscore(history_floats, float(today_count))

    if z is None:
        note = (
            f"tariff articles today={today_count} avg_tone={avg_tone_today} "
            f"(insufficient history: {len(history_floats)}d, "
            f"need >= {_MIN_ZSCORE_HISTORY})"
        )
        return TariffShockResult(
            today_count=today_count,
            baseline_mean=mean,
            baseline_std=std,
            count_z=None,
            avg_tone_today=avg_tone_today,
            n_history=len(history_floats),
            n_articles_today=n_today,
            alert_fired=False,
            note=note,
            title_sample=today_titles,
        )

    note = (
        f"tariff today={today_count} baseline={mean:.2f}±{std:.2f} "
        f"count_z={z:+.2f} avg_tone={avg_tone_today}"
    )

    # Combined gate: count anomaly AND negative tone
    is_count_anomaly = z >= ALERT_COUNT_Z_FLOOR
    is_negative_tone = avg_tone_today is not None and avg_tone_today <= AVG_TONE_NEG_FLOOR

    fired = False
    if is_count_anomaly and is_negative_tone and persist:
        await check_metric(
            session,
            metric_name="tariff_count_z",
            current_value=z,
            asset=None,  # macro-broad
            extra_payload={
                "today_count": today_count,
                "baseline_mean": mean,
                "baseline_std": std,
                "n_history": len(history_floats),
                "avg_tone_today": avg_tone_today,
                "n_articles_today": n_today,
                "title_sample": today_titles,
                "tariff_keywords_used": list(TARIFF_KEYWORDS),
                "tariff_patterns_used": [p.pattern for p in _TARIFF_PATTERNS],
                "source": "gdelt:tariff_filter",
            },
        )
        fired = True

    return TariffShockResult(
        today_count=today_count,
        baseline_mean=round(mean, 3) if mean is not None else None,
        baseline_std=round(std, 3) if std is not None else None,
        count_z=round(z, 3),
        avg_tone_today=avg_tone_today,
        n_history=len(history_floats),
        n_articles_today=n_today,
        alert_fired=fired,
        note=note,
        title_sample=today_titles,
    )
