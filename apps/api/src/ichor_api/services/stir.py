"""STIR — market-implied Fed-funds path from CME 30-Day SOFR/Fed-funds (ZQ) futures.

Surfaces what is ALREADY collected but never read past a 2-point tone : the
`cme_zq_futures` collector persists the full forward curve into
`fred_observations` as `ZQ_FRONT_IMPLIED_EFFR` + per-contract
`ZQ_{code}_IMPLIED_EFFR` (K26 … F27, implied EFFR = 100 − price). This service
reconstructs the implied path, the cumulative basis-points priced vs the front
month, and — the actual anticipation signal — the *repricing delta* (how the
implied path moved over the last ~5 sessions).

ADR-017 boundary : this is the path the rates market has *priced*, NOT a
forecast and NOT a trade signal. The output narrative says so explicitly and
contains no BUY/SELL/entry/stop vocabulary.

No migration : `fred_observations` already stores per-day, per-contract implied
EFFR, so the repricing delta is two reads per contract (latest vs N sessions
back) computed transiently — mirrors `services/yield_curve.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..collectors.cme_zq_futures import ZQ_FORWARD_TICKERS
from ..models import FredObservation

# Actual policy-rate anchor (effective fed funds, FRED daily).
_EFFR_SERIES = "EFFR"
# Front-month implied EFFR (spot month ZQ contract).
_FRONT_SERIES = "ZQ_FRONT_IMPLIED_EFFR"
_FRONT_LABEL = "Mois courant"
# Ordered forward curve : (series_id, month_label) mirrored from the collector
# so labels never drift from what gets persisted.
_FORWARD: tuple[tuple[str, str], ...] = tuple(
    (f"ZQ_{code}_IMPLIED_EFFR", label) for (_ticker, code, label) in ZQ_FORWARD_TICKERS
)

# A standard FOMC move is 25 bp ; used to express the path in "cuts priced".
_BP_PER_MOVE = 25.0
# Tone dead-band on the front→horizon cumulative move (basis points).
_TONE_BP_DEADBAND = 10.0
# Repricing window : how many trailing sessions define "what changed".
_REPRICING_WINDOW_SESSIONS = 5


@dataclass(frozen=True)
class _FomcMeeting:
    """One FOMC meeting in the ZQ-contract horizon, with the inputs needed to
    back out the meeting's implied rate change CME-FedWatch-style.

    `start_series` = the implied EFFR feeding the pre-meeting rate (a no-meeting
    "clean" prior month). When None, the pre-meeting rate is chained from the
    previous meeting's solved post-meeting rate.

    `end_anchor_series` = a no-meeting month AFTER the meeting whose monthly
    average IS the post-meeting rate — used for LATE-month meetings where the
    in-month day-weight denominator (N − pre_days) is tiny and numerically
    unstable. When None, the post-meeting rate is solved from `month_series` by
    day-weighting : R_month = (pre_days·r_start + (N−pre_days)·r_end)/N.
    `pre_days` = decision day-of-month (the Fed's new target is effective the
    next business day, so the decision day itself runs at the old rate).
    """

    label: str
    decision_date: str
    month_series: str
    days_in_month: int
    pre_days: int
    start_series: str | None
    end_anchor_series: str | None


# 2026 FOMC schedule — decision dates verified 2026-05-30 against the Federal
# Reserve primary calendar (federalreserve.gov/monetarypolicy/fomccalendars.htm)
# + cross-checked via a second fetch. Methodology : CME FedWatch
# (cmegroup.com "Understanding the CME Group FedWatch Tool Methodology").
# REFRESH ANNUALLY (mirror cme_zq_futures.ZQ_FORWARD_TICKERS rolling refresh).
# Only meetings inside the persisted ZQ horizon (May-2026 → Jan-2027) are
# listed. Mid-month meetings use the in-month day-weight (stable denominator) ;
# late-month meetings (Jul-29, Oct-28) use the next clean month as the
# post-meeting anchor to avoid the ÷3 instability.
_FOMC_2026: tuple[_FomcMeeting, ...] = (
    _FomcMeeting(
        "Jun 2026", "2026-06-17", "ZQ_M26_IMPLIED_EFFR", 30, 17, "ZQ_K26_IMPLIED_EFFR", None
    ),
    _FomcMeeting(
        "Jul 2026", "2026-07-29", "ZQ_N26_IMPLIED_EFFR", 31, 29, None, "ZQ_Q26_IMPLIED_EFFR"
    ),
    _FomcMeeting(
        "Sep 2026", "2026-09-16", "ZQ_U26_IMPLIED_EFFR", 30, 16, "ZQ_Q26_IMPLIED_EFFR", None
    ),
    _FomcMeeting(
        "Oct 2026", "2026-10-28", "ZQ_V26_IMPLIED_EFFR", 31, 28, None, "ZQ_X26_IMPLIED_EFFR"
    ),
    _FomcMeeting(
        "Dec 2026", "2026-12-09", "ZQ_Z26_IMPLIED_EFFR", 31, 9, "ZQ_X26_IMPLIED_EFFR", None
    ),
)


@dataclass(frozen=True)
class StirPoint:
    """One ZQ contract month on the implied-path curve."""

    series_id: str
    month_label: str
    implied_effr: float | None
    observation_date: datetime | None
    cum_bps_vs_front: float | None
    """(implied − front) × 100. Negative = easing priced by that month."""
    repricing_bps: float | None
    """(implied_now − implied_{~5 sessions back}) × 100. Negative = the market
    priced MORE easing over the window."""
    sessions_in_window: int


@dataclass(frozen=True)
class StirMeeting:
    """Per-FOMC-meeting market-implied outcome (CME FedWatch-style).

    `implied_change_bps` = post-meeting minus pre-meeting implied rate (× 100).
    Probabilities assume 25 bp increments ; p_hold + p_cut + p_hike sum to ~1
    for a single-step meeting (|Δ| ≤ 25). For |Δ| > 25 the move-direction
    probability is capped at 1 (a second move is being priced — surfaced via
    the magnitude). Market-implied, NOT a forecast (ADR-017)."""

    label: str
    decision_date: str
    implied_change_bps: float | None
    p_cut: float | None
    p_hold: float | None
    p_hike: float | None


@dataclass(frozen=True)
class StirReading:
    as_of: datetime | None
    policy_rate_effr: float | None
    """Actual effective fed funds (FRED EFFR) — the anchor the path moves from."""
    front_implied_effr: float | None
    points: list[StirPoint]
    meetings: list[StirMeeting]
    horizon_label: str | None
    net_bps_to_horizon: float | None
    """Cumulative front→far implied move in bp. Negative = net easing priced."""
    cuts_priced_to_horizon: float | None
    """net_bps_to_horizon / 25, signed. Positive = cuts priced (easing)."""
    tone: str  # "easing_priced" | "tightening_priced" | "flat"
    repricing_bps_horizon: float | None
    """Repricing of the far contract over the window. Negative = more easing
    priced recently."""
    note: str = ""
    sources: list[str] = field(default_factory=list)


async def _series_recent(
    session: AsyncSession,
    series_id: str,
    *,
    limit: int = _REPRICING_WINDOW_SESSIONS + 1,
    max_age_days: int = 21,
) -> list[tuple[datetime, float]]:
    """Most-recent `limit` observations (newest first) within max_age_days."""
    cutoff = datetime.now(UTC).date() - timedelta(days=max_age_days)
    rows = (
        await session.execute(
            select(FredObservation.observation_date, FredObservation.value)
            .where(
                FredObservation.series_id == series_id,
                FredObservation.observation_date >= cutoff,
                FredObservation.value.is_not(None),
            )
            .order_by(desc(FredObservation.observation_date))
            .limit(limit)
        )
    ).all()
    return [(datetime.combine(d, datetime.min.time(), tzinfo=UTC), float(v)) for d, v in rows]


def _point_from_rows(
    series_id: str,
    label: str,
    front_implied: float | None,
    rows: list[tuple[datetime, float]],
) -> StirPoint:
    """Pure : build one curve point from its recent observations (newest first)."""
    if not rows:
        return StirPoint(series_id, label, None, None, None, None, 0)
    implied_now, obs_date = rows[0][1], rows[0][0]
    cum = (implied_now - front_implied) * 100.0 if front_implied is not None else None
    reprice = (implied_now - rows[-1][1]) * 100.0 if len(rows) >= 2 else None
    return StirPoint(
        series_id=series_id,
        month_label=label,
        implied_effr=implied_now,
        observation_date=obs_date,
        cum_bps_vs_front=cum,
        repricing_bps=reprice,
        sessions_in_window=max(0, len(rows) - 1),
    )


def _tone(net_bps: float | None) -> str:
    if net_bps is None:
        return "flat"
    if net_bps < -_TONE_BP_DEADBAND:
        return "easing_priced"
    if net_bps > _TONE_BP_DEADBAND:
        return "tightening_priced"
    return "flat"


def _move_probabilities(
    change_bps: float | None,
) -> tuple[float | None, float | None, float | None]:
    """(p_cut, p_hold, p_hike) for a single FOMC meeting, 25 bp increments.

    P(move) = min(1, |Δ|/25) ; P(hold) = max(0, 1 − |Δ|/25). Δ's sign routes
    the move probability to cut (Δ<0) or hike (Δ>0). When |Δ| > 25 a second
    move is priced — the direction probability caps at 1 and the magnitude
    (the bp change) carries the rest."""
    if change_bps is None:
        return (None, None, None)
    n = abs(change_bps) / _BP_PER_MOVE
    p_dir = min(1.0, n)
    p_hold = max(0.0, 1.0 - n)
    if change_bps < 0:
        return (p_dir, p_hold, 0.0)
    if change_bps > 0:
        return (0.0, p_hold, p_dir)
    return (0.0, 1.0, 0.0)


def _compute_meetings(implied_by_series: dict[str, float]) -> list[StirMeeting]:
    """Back out each FOMC meeting's market-implied rate change (CME FedWatch).

    Chains the 2026 meetings : mid-month meetings solve the post-meeting rate
    from the meeting-month contract by day-weighting against a clean prior
    month ; late-month meetings read it directly from the next clean month
    (anchor). The pre-meeting rate is the prior clean month or the previous
    meeting's solved post-meeting rate. Pure — no I/O."""
    out: list[StirMeeting] = []
    prev_end: float | None = None
    for m in _FOMC_2026:
        r_start = implied_by_series.get(m.start_series) if m.start_series else prev_end
        if m.end_anchor_series is not None:
            r_end = implied_by_series.get(m.end_anchor_series)
        else:
            r_month = implied_by_series.get(m.month_series)
            post_days = m.days_in_month - m.pre_days
            if r_month is not None and r_start is not None and post_days > 0:
                r_end = (m.days_in_month * r_month - m.pre_days * r_start) / post_days
            else:
                r_end = None
        change_bps = (
            (r_end - r_start) * 100.0 if (r_end is not None and r_start is not None) else None
        )
        p_cut, p_hold, p_hike = _move_probabilities(change_bps)
        out.append(
            StirMeeting(
                label=m.label,
                decision_date=m.decision_date,
                implied_change_bps=change_bps,
                p_cut=p_cut,
                p_hold=p_hold,
                p_hike=p_hike,
            )
        )
        if r_end is not None:
            prev_end = r_end
    return out


async def assess_stir(session: AsyncSession) -> StirReading:
    """Reconstruct the market-implied Fed path + repricing delta from ZQ futures."""
    sources: list[str] = []

    effr_rows = await _series_recent(session, _EFFR_SERIES, limit=1)
    policy_rate = effr_rows[0][1] if effr_rows else None
    if effr_rows:
        sources.append(f"FRED:{_EFFR_SERIES}")

    front_rows = await _series_recent(session, _FRONT_SERIES)
    front_implied = front_rows[0][1] if front_rows else None
    as_of = front_rows[0][0] if front_rows else None
    if front_rows:
        sources.append(f"CME:{_FRONT_SERIES}")

    points: list[StirPoint] = []
    for series_id, label in _FORWARD:
        rows = await _series_recent(session, series_id)
        points.append(_point_from_rows(series_id, label, front_implied, rows))
        if rows:
            sources.append(f"CME:{series_id}")

    far = points[-1] if points else None
    net_bps = far.cum_bps_vs_front if far else None
    horizon_label = far.month_label if far else None
    reprice_horizon = far.repricing_bps if far else None
    cuts = (-net_bps / _BP_PER_MOVE) if net_bps is not None else None
    tone = _tone(net_bps)

    # Per-FOMC-meeting probabilities reuse the implied rates already read into
    # `points` (+ front) — no extra DB round-trip.
    implied_by_series = {p.series_id: p.implied_effr for p in points if p.implied_effr is not None}
    if front_implied is not None:
        implied_by_series[_FRONT_SERIES] = front_implied
    meetings = _compute_meetings(implied_by_series)

    note = _build_note(
        policy_rate, front_implied, horizon_label, net_bps, cuts, tone, reprice_horizon
    )

    return StirReading(
        as_of=as_of,
        policy_rate_effr=policy_rate,
        front_implied_effr=front_implied,
        points=points,
        meetings=meetings,
        horizon_label=horizon_label,
        net_bps_to_horizon=net_bps,
        cuts_priced_to_horizon=cuts,
        tone=tone,
        repricing_bps_horizon=reprice_horizon,
        note=note,
        sources=sources,
    )


def _build_note(
    policy_rate: float | None,
    front_implied: float | None,
    horizon_label: str | None,
    net_bps: float | None,
    cuts: float | None,
    tone: str,
    reprice_horizon: float | None,
) -> str:
    """ADR-017-clean French summary of the implied path + repricing."""
    if front_implied is None or horizon_label is None or net_bps is None:
        return "Courbe ZQ indisponible (collecteur CME en attente de données fraîches)."

    tone_word = {
        "easing_priced": "assouplissement",
        "tightening_priced": "resserrement",
        "flat": "statu quo",
    }[tone]
    # Round half-up on the magnitude to match the frontend fmtBps()
    # (`Math.abs(bps).toFixed(0)`) so the note and the header badge can never
    # disagree at a .5 boundary (e.g. 12.5 → both "13 pb").
    parts = [
        f"Trajectoire implicite du marché monétaire (futures Fed-funds ZQ) : "
        f"{tone_word} de {int(abs(net_bps) + 0.5)} pb pricé du mois courant à {horizon_label}"
    ]
    if cuts is not None and abs(cuts) >= 0.2:
        direction = "baisses" if cuts > 0 else "hausses"
        parts.append(f"≈ {abs(cuts):.1f} {direction} de 25 pb")
    if reprice_horizon is not None and abs(reprice_horizon) >= 1.0:
        moved = "davantage d'assouplissement" if reprice_horizon < 0 else "moins d'assouplissement"
        sign = "+" if reprice_horizon >= 0 else "−"
        parts.append(
            f"sur ~5 séances le marché a pricé {moved} "
            f"({sign}{int(abs(reprice_horizon) + 0.5)} pb sur {horizon_label})"
        )
    note = " ; ".join(parts) + "."
    note += " Trajectoire pricée par le marché, pas une prévision ni un signal."
    return note
