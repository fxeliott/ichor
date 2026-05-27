"""Cross-asset correlation matrix — rolling 30d intraday returns.

For session-momentum trading, knowing how the 8 Phase-1 assets correlate
to each other in the current regime is essential :
  - In `haven_bid` quadrant : XAU/USD vs USD/JPY tightens (-0.6+) ;
    NAS100 vs SPX500 stays high (+0.95+).
  - In `goldilocks` : EUR/USD vs AUD/USD couple together (+0.5+) and
    decouple from XAU.
  - In `funding_stress` : everything correlates to USD strength.

This service computes the Pearson correlation matrix on minute-level
log returns over a configurable rolling window (default 30 days), plus
diagnostic flags : which pairs are unusually high/low correlated vs
their long-run mean.

Pure-stdlib math (no pandas / numpy required).

VISION_2026 — closes the "what's the cross-asset picture?" gap. A
trader staring at one pair misses the regime-conditional correlation
shifts that often signal the move.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import PolygonIntradayBar

_ASSETS = (
    "EUR_USD",
    "GBP_USD",
    "USD_JPY",
    "AUD_USD",
    "USD_CAD",
    "XAU_USD",
    "NAS100_USD",
    "SPX500_USD",
    # r171 G2 — DXY added to surface co-mouvement vs USD broad strength,
    # honoring Eliot's verbatim "DXY = pilier de notre analyse" (Fathom
    # transcript 2026-05-25 §XI). The correlation surface stays a
    # co-mouvement MONITORING tool, not a directional prediction — per
    # Engel-West 2005 *JPE* 113(3):485-517 DOI 10.1086/429137 abstract :
    # "fundamental variables ... provide little help in predicting changes
    # in floating exchange rates". The DXY row helps Eliot read the regime,
    # not predict the next bar (ADR-017 boundary preserved).
    #
    # Cold-start note : Polygon free tier does not stream I:DXY (mirrors
    # the I:SPX 403 documented in ADR-089 / r27 ; SPY proxy adopted for
    # SPX500_USD). Until a DXY ETF proxy (UUP — Invesco DB US Dollar Index
    # Bullish Fund) is wired (r172 candidate), `series["DXY"]` returns {}
    # and DXY-* matrix cells stay None (graceful via len(common) < 30 skip
    # at line ~162). The frontend r171 <DxyCorrelationPanel> renders the
    # honest "insufficient history" sentinel until proxy ships.
    "DXY",
)


@dataclass(frozen=True)
class CorrelationMatrix:
    window_days: int
    assets: list[str]
    matrix: list[list[float | None]]
    """matrix[i][j] = corr(assets[i], assets[j]) ; None if insufficient overlap."""
    n_returns_used: int
    """Number of overlapping return points used in the most-populated cell."""
    generated_at: datetime
    flags: list[str] = field(default_factory=list)
    """Notable observations : "EUR_USD/AUD_USD unusually low (0.10 vs 0.50 norm)"."""


# Long-run reference correlations (trader heuristic — used to flag deviations).
# These are coarse priors based on standard FX desk knowledge ; we flag if
# the realized correlation diverges by > 0.30 from this prior.
_REFERENCE_CORR: dict[tuple[str, str], float] = {
    ("EUR_USD", "GBP_USD"): +0.65,
    ("EUR_USD", "AUD_USD"): +0.55,
    ("GBP_USD", "AUD_USD"): +0.50,
    ("EUR_USD", "USD_JPY"): -0.30,
    ("EUR_USD", "USD_CAD"): -0.40,
    ("AUD_USD", "USD_CAD"): -0.45,
    ("XAU_USD", "EUR_USD"): +0.40,
    ("XAU_USD", "USD_JPY"): -0.50,
    ("NAS100_USD", "SPX500_USD"): +0.92,
    ("NAS100_USD", "XAU_USD"): +0.20,
    ("USD_JPY", "USD_CAD"): +0.30,
    # r171 G2 — DXY co-mouvement priors (trader-heuristic, FX desk
    # standard ; NOT peer-reviewed values per se — Engel-West 2005 is
    # the FRAMING backbone, individual prior magnitudes are calibrated
    # against the published DXY ICE basket weights and classic textbook
    # FX inversions). Stamped as such for Pattern #15 R59 honesty.
    #
    # DXY ICE basket weights (per Federal Reserve H.10 / FactSet methodology) :
    # EUR 57.6% / JPY 13.6% / GBP 11.9% / CAD 9.1% / SEK 4.2% / CHF 3.6%
    # → EUR/USD is the near-perfect inverse, JPY/CAD pairs inverted by
    # quoting convention (USD/JPY = positive corr with DXY, USD/CAD = same).
    # XAU = classic dollar inverse. NAS/SPX = mild headwind via multinationals.
    ("DXY", "EUR_USD"): -0.95,  # 57.6% of basket, near-perfect inverse
    ("DXY", "GBP_USD"): -0.85,  # 11.9% of basket, inverse
    ("DXY", "USD_JPY"): +0.55,  # 13.6% of basket, USD/JPY quoting convention
    ("DXY", "AUD_USD"): -0.65,  # commodity FX, USD-driven risk
    ("DXY", "USD_CAD"): +0.55,  # 9.1% of basket, USD/CAD quoting convention
    ("DXY", "XAU_USD"): -0.75,  # gold-dollar classic inverse
    ("DXY", "NAS100_USD"): -0.30,  # USD strength = multinational earnings headwind
    ("DXY", "SPX500_USD"): -0.25,  # similar transmission, smaller magnitude
}


def _ref_corr(a: str, b: str) -> float | None:
    return _REFERENCE_CORR.get((a, b)) or _REFERENCE_CORR.get((b, a))


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 30:
        return None
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    den = math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else 0.0
    if den <= 0:
        return None
    return sxy / den


async def _hourly_returns(
    session: AsyncSession, asset: str, window_days: int
) -> dict[datetime, float]:
    """Hourly log returns keyed by floor-to-hour timestamp.

    Sampling at hourly frequency keeps the math tractable ; minute-level
    correlation is dominated by noise on such a small dataset.
    """
    cutoff = datetime.now(UTC) - timedelta(days=window_days)
    rows = list(
        (
            await session.execute(
                select(PolygonIntradayBar)
                .where(
                    PolygonIntradayBar.asset == asset,
                    PolygonIntradayBar.bar_ts >= cutoff,
                )
                .order_by(PolygonIntradayBar.bar_ts.asc())
            )
        )
        .scalars()
        .all()
    )
    if len(rows) < 30:
        return {}
    # Bucket bars by floor-to-hour, take the last close per bucket.
    by_hour: dict[datetime, float] = {}
    for r in rows:
        h = r.bar_ts.replace(minute=0, second=0, microsecond=0)
        by_hour[h] = float(r.close)
    # Sorted hours
    hours = sorted(by_hour.keys())
    out: dict[datetime, float] = {}
    prev: float | None = None
    for h in hours:
        c = by_hour[h]
        if prev is not None and prev > 0:
            try:
                out[h] = math.log(c / prev)
            except ValueError:
                pass  # negative / zero close
        prev = c
    return out


async def assess_correlations(session: AsyncSession, *, window_days: int = 30) -> CorrelationMatrix:
    """Build the 8×8 correlation matrix over the rolling window."""
    series: dict[str, dict[datetime, float]] = {}
    for asset in _ASSETS:
        series[asset] = await _hourly_returns(session, asset, window_days)

    n_assets = len(_ASSETS)
    matrix: list[list[float | None]] = [[None] * n_assets for _ in range(n_assets)]
    max_overlap = 0

    for i, a in enumerate(_ASSETS):
        for j, b in enumerate(_ASSETS):
            if i == j:
                matrix[i][j] = 1.0
                continue
            if matrix[j][i] is not None:
                matrix[i][j] = matrix[j][i]
                continue
            xa = series.get(a, {})
            xb = series.get(b, {})
            common = sorted(set(xa.keys()) & set(xb.keys()))
            if len(common) < 30:
                continue
            xs = [xa[t] for t in common]
            ys = [xb[t] for t in common]
            corr = _pearson(xs, ys)
            matrix[i][j] = corr
            max_overlap = max(max_overlap, len(common))

    flags: list[str] = []
    for i, a in enumerate(_ASSETS):
        for j in range(i + 1, n_assets):
            b = _ASSETS[j]
            realized = matrix[i][j]
            ref = _ref_corr(a, b)
            if realized is None or ref is None:
                continue
            delta = realized - ref
            if abs(delta) >= 0.30:
                tag = "tighter" if delta > 0 else "looser"
                flags.append(
                    f"{a}/{b} unusually {tag} : {realized:+.2f} vs ref {ref:+.2f} ({delta:+.2f})"
                )

    return CorrelationMatrix(
        window_days=window_days,
        assets=list(_ASSETS),
        matrix=matrix,
        n_returns_used=max_overlap,
        generated_at=datetime.now(UTC),
        flags=flags,
    )


def render_correlations_block(m: CorrelationMatrix) -> tuple[str, list[str]]:
    """Markdown block for data_pool.py."""
    if m.n_returns_used < 30:
        return (
            f"## Cross-asset correlations ({m.window_days}d, hourly returns)\n"
            f"- (insufficient bar history — need ≥ 30 hours of overlap)",
            [],
        )

    lines = [
        f"## Cross-asset correlations ({m.window_days}d, hourly log returns, n={m.n_returns_used})"
    ]
    # Compact upper-triangle list rather than full matrix
    rows: list[str] = []
    for i in range(len(m.assets)):
        for j in range(i + 1, len(m.assets)):
            v = m.matrix[i][j]
            if v is None:
                continue
            ref = _ref_corr(m.assets[i], m.assets[j])
            ref_part = f" (ref {ref:+.2f})" if ref is not None else ""
            rows.append(f"  · {m.assets[i]:<11s} ↔ {m.assets[j]:<11s} = {v:+.2f}{ref_part}")
    lines.append("- Pairwise (upper triangle) :")
    lines.extend(rows)

    if m.flags:
        lines.append("- 🔔 Régime shifts vs prior :")
        for f in m.flags:
            lines.append(f"  · {f}")

    sources = [f"polygon_intraday:correlation_matrix:{m.window_days}d"]
    return "\n".join(lines), sources
