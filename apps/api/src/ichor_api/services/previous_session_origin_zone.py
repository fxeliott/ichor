"""r174 FOUNDATION — previous-session origin zone classifier (Eliot Fathom §V).

Skeleton pure-compute service materialising Eliot's Fathom 2026-05-25 §V
verbatim methodology : « savoir d'où vient le mouvement de la session
précédente, son zone d'origine, son sens, ses hauts et bas ». The
trader's read of which session zone (Asian / London / NY) DROVE the
dominant move of the immediately preceding session, with high/low/
direction stamped, is a context input to the NY position-taking
decision.

## FOUNDATION-only scope at r174 (mirror r160 Dukascopy pattern)

Per doctrine #2 strict scope : THIS commit ships ONLY the schema +
skeleton fn returning None. ZERO behavior change at r174 deploy time.
r175+ ships the actual classifier logic + Pass-2 data-pool wiring +
frontend surfacing if trader-leverage justifies the cost.

The FOUNDATION-only pattern is identical to r160 Dukascopy MVP : ship
the shell, prove the contract (Pydantic + tests + ADR cite),
defer EXECUTION (compute logic + persistence + consumer wiring) to a
subsequent atomic round once trader-leverage is empirically validated.

## Citation provenance (Pattern #15 R59 verified 2026-05-28)

**R59 pre-flight subagent ac56d1c644ce45309 VERDICT** : « previous-session
origin zone » with Asian/London/NY breakdown is a **RETAIL/PRACTITIONER
(ICT — Inner Circle Trader style) concept**, NOT academic. NO peer-
reviewed paper directly supports this framing.

**Primary provenance** : Eliot Fathom recording 2026-05-25 §V verbatim
practitioner methodology — Eliot describes reading the previous
session's high/low + dominant direction as a context input to the
position-taking decision. This is a Mark-Douglas-class « 5 truths »
discipline (each session is unique, but the recent context informs
the probability read).

**Stamp** : `provenance = "practitioner_stamp"` (NOT `"peer_reviewed"`)
+ practitioner_source pointer to Eliot Fathom 2026-05-25 §V transcript.

### R59 META self-catch 10ème (3rd consecutive cite-drift in 6 rounds)

R59 confirmed my previously-stamped « Baltussen-Da-Lammers-Martens 2021
*JFE* DOI 10.1016/j.jfineco.2021.04.029 » was a **MEMORY-STRETCH
CARGO-CULT cite**. The actual paper is « **Hedging Demand and Market
Intraday Momentum** » (*JFE* 142:377-403) about **last-30-min vs
rest-of-day intraday momentum** driven by **option-market-maker
gamma hedging flows**, NOT session zones.

Pattern #15 R59 cumulative META self-catches in 6-round span :
- r168b : Kaul-Sapp 2008 *JBF* « intraday momentum » HALLU → corrected to Elaut-Frömmel-Lampaert 2018 *JFM*
- r173 RED-1 : Rogers-Satchell journal wrong (*Math Finance* → *Annals of Applied Probability*)
- r173 RED-2 : Bauer 2024 jump-test cite HALLUCINATED
- **r174 10ème META** : Baltussen 2021 topic mismatch (gamma hedging ≠ session zones)

**Pattern #20 codification CANDIDATE r175 doctrinal addendum** : « memory
citations REQUIRE R59-pre-commit-mandatory ». 4 consecutive cite-drifts
across r168b/r173/r174 demonstrate that memory-resident peer-reviewed
citations DRIFT over time and MUST be WebFetch-verified before any
commit referencing them.

### Honest scope acknowledgement

Closest legitimate academic neighbors (NONE a direct fit per R59) :
- Heston-Korajczyk-Sadka 2010 *J Finance* 65(4):1369-1407 DOI 10.1111/j.1540-6261.2010.01573.x (cross-section half-hour periodicity, NOT 3-session-zone framing)
- Lou-Polk-Skouras 2019 *JFE* 134(1):192-213 DOI 10.1016/j.jfineco.2019.03.011 (overnight vs intraday 2-component decomposition, NOT 3-zone)
- Parkinson 1980 *J Business* 53(1):61-65 (high-low range estimator — VARIANCE only, NOT directional zone semantics)

These can be cited in r175+ for ARITHMETIC components (Parkinson for
high-low range) but NOT for the « session origin zone » semantic
framing itself, which remains practitioner-stamp.

## ADR-017 boundary

Pure factual snapshot (high price + low price + directional sign).
NEVER a directional bias output for the CURRENT session — the snapshot
is INPUT to Pass-2 narrative + trader decision, NOT an output.

## Session zone definitions

Per Eliot Fathom §V + standard FX desk convention :
- **Asian session** : 00:00 — 08:00 UTC (Tokyo + Sydney + Hong Kong)
- **London session** : 07:00 — 16:00 UTC (London Cash open at 08:00 UTC
  in winter / 07:00 in summer ; overlap with Asian close + NY open)
- **NY session** : 13:00 — 21:00 UTC (NYSE RTH 13:30-20:00 UTC,
  extended for FX 24/5 trading window)

Asset class adjustments :
- **FX / XAU** : 24/5 trading → all 3 sessions apply
- **NAS100 / SPX500** : NYSE RTH only → only NY session has meaningful
  bars ; Asian/London → empty bars → graceful None

## Doctrine alignment

- ADR-017 boundary : pure factual snapshot, never directional bias
- Doctrine #2 strict scope : FOUNDATION-only ship at r174
- Doctrine #4 SSOT : session zone definitions sourced from
  `services/market_session.py` (existing, ADR-099 Tier 1.3)
- Doctrine #11 calibrated honesty : explicit practitioner-stamp +
  peer-reviewed citation DEFERRED honest acknowledgement
- Doctrine #12 anti-recidive : R59 pre-flight obligatoire BEFORE
  EXECUTION-phase ship in r175+
- Mirror r160 Dukascopy FOUNDATION pattern (ADR-099 §Impl(r160))
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

# ─────────────────────────────────── DOMAIN ─────────────────────────────

SessionZoneLabel = Literal["asian", "london", "ny"]
"""Canonical 3-zone enum for the 24-hour FX trading day. Boundaries
defined in module docstring. Per Eliot Fathom §V + standard FX desk
convention. NEW zones MUST land via ADR amendment (e.g., « Mideast »
or « Sydney » sub-decomposition if empirically needed)."""


OriginDirection = Literal["up", "down", "range"]
"""Direction of the previous-session dominant move :
- ``up`` : close > open + |move| >= 2 × ATR(session)
- ``down`` : close < open + |move| >= 2 × ATR(session)
- ``range`` : neither (consolidation / chop)

Thresholds are r175+ calibration ; r174 FOUNDATION skeleton returns
None so the threshold values are not yet pinned."""


@dataclass(frozen=True)
class OriginZoneSnapshot:
    """Previous-session origin zone snapshot.

    Eliot Fathom §V verbatim practitioner methodology — the trader's
    read of which session zone DROVE the dominant move of the
    immediately preceding session, with high/low/direction stamped.

    Doctrine #11 calibrated honesty fields :
    - ``bar_count`` : honest sample-size disclosure (1-min bars from
      ``polygon_intraday`` over the session window). When < 30 bars,
      the snapshot is unreliable ; r175+ classifier returns None in
      that case (HONEST_SENTINEL ``rolling_corr_low_n`` analog).
    - ``start_utc`` / ``end_utc`` : exact session window stamps
      (timezone-aware, UTC).

    Frozen for cache safety + structural-immutability discipline
    (mirror ``CorrelationMatrix`` r171a pattern).
    """

    session_zone: SessionZoneLabel
    """Which of the 3 session zones drove the dominant previous-session
    move. For multi-zone sessions (e.g., London → NY trend continuation),
    classifier picks the zone with the LARGEST absolute return."""

    high_price: float
    """Maximum bar.high observed during the dominant session zone window."""

    low_price: float
    """Minimum bar.low observed during the dominant session zone window."""

    direction: OriginDirection
    """Net direction of the dominant move : up / down / range."""

    bar_count: int
    """Number of 1-min ``polygon_intraday`` bars in the dominant
    session zone window. Used for sample-size sanity check per
    Cohen 1988 n=30 threshold (mirror ``rolling_corr_low_n`` sentinel).
    Snapshots with ``bar_count < 30`` are non-actionable — classifier
    returns None at that threshold in r175+."""

    start_utc: datetime
    """Inclusive UTC start of the dominant session zone window."""

    end_utc: datetime
    """Exclusive UTC end of the dominant session zone window."""


# ─────────────────────────────────── SKELETON COMPUTE ──────────────────


async def compute_previous_session_origin_zone(
    session: AsyncSession,
    asset: str,
    *,
    now_utc: datetime,
) -> OriginZoneSnapshot | None:
    """r174 FOUNDATION skeleton — returns None unconditionally.

    r175+ EXECUTION-phase will implement :

    1. Resolve the « previous session » window based on `now_utc` +
       Eliot's NY 14h-20h Paris position-taking window. The « previous
       session » is the most-recent session that CLOSED before the
       current NY pre-session briefing window (typically the prior NY
       session for weekend / late-NY emissions, OR the prior London
       session for early-NY emissions).
    2. Query `polygon_intraday` 1-min bars over the previous session
       window for `asset`.
    3. Decompose into Asian / London / NY sub-windows. For each
       sub-window, compute (high, low, close - open) absolute move.
    4. Pick the sub-window with the LARGEST absolute move as the
       « dominant session zone ». Classify direction per the threshold
       defined in `OriginDirection` (2 × session ATR for up/down,
       else range).
    5. Return `OriginZoneSnapshot` OR None if `bar_count < 30`
       (honest absence per doctrine #11).

    r174 FOUNDATION returns None unconditionally. ZERO behavior change
    at r174 deploy. Consumer wiring (Pass-2 data-pool + frontend
    surface) lands r175+ once classifier logic is empirically
    validated against historical sessions.

    Args:
        session : SQLAlchemy async session (DB query handle, NOT used
            at r174 FOUNDATION but reserved for r175+ signature
            stability).
        asset : asset code (e.g. "EUR_USD"). Reserved for r175+ ;
            FOUNDATION returns None regardless.
        now_utc : UTC wall-clock datetime. Reserved for r175+ session-
            window resolution.

    Returns:
        None at r174 FOUNDATION (skeleton). r175+ returns
        `OriginZoneSnapshot` when data is available + `bar_count >= 30`,
        else None.
    """
    # r174 FOUNDATION : skeleton. r175+ implements the 5-step compute.
    # The function signature is FROZEN by this ship so r175+ wiring
    # consumers (Pass-2 data-pool, frontend, tests) can integrate
    # incrementally without breaking changes.
    _ = (session, asset, now_utc)  # silence ruff unused-arg warning
    return None
