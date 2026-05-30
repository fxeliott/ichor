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
class StirReading:
    as_of: datetime | None
    policy_rate_effr: float | None
    """Actual effective fed funds (FRED EFFR) — the anchor the path moves from."""
    front_implied_effr: float | None
    points: list[StirPoint]
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

    note = _build_note(
        policy_rate, front_implied, horizon_label, net_bps, cuts, tone, reprice_horizon
    )

    return StirReading(
        as_of=as_of,
        policy_rate_effr=policy_rate,
        front_implied_effr=front_implied,
        points=points,
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
