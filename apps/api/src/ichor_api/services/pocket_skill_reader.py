"""W115c pocket-skill reader — close the Phase D measure→act loop.

ADR-088 (PROPOSED, round-28 amended) — read Vovk-Zhdanov weight pockets
from `brier_aggregator_weights` and surface a *calibration hint* (NOT a
directional override) to Pass-3 stress reasoning.

Contractual constraints :

* **Read-only side** : NO Pass-2 reasoning override. The 4-pass output
  P(target_up) is unchanged ; W115c only emits a `confidence_band`
  diagnostic that Pass-3 stress can incorporate into its addendum.
* **Feature-flag fail-closed** : `phase_d_w115c_confluence_enabled` row
  absent or disabled → `read_pocket()` returns `None` → orchestrator
  threads `confluence_section=None` → zero-diff baseline behaviour.
* **Hysteresis dead-band (round-28 ADR-088 amendment)** : 2-pp dead-band
  between enter and exit thresholds to prevent flicker as skill_delta
  fluctuates around the boundary. State persisted via the previous
  `confidence_band` carried in PocketSkill (orchestrator's responsibility
  to pass it back in on subsequent calls).
* **Cap5 allowlist exclusion** : `brier_aggregator_weights` is NEVER
  added to `tool_query_db.ALLOWED_TABLES` — Couche-2 agents cannot read
  Vovk weights directly. This service is the canonical access path.

Performance budget : SQL is a single PK lookup on the UNIQUE constraint
`(asset, regime, expert_kind, pocket_version)`. Expected <5ms per
`read_pocket` invocation.

Frontend gel (rule 4) intact : no UI consumption introduced. The
`/v1/phase-d/pocket-summary` endpoint already surfaces band info ;
no new endpoint added.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import BrierAggregatorWeight
from .feature_flags import is_enabled

# Feature flag pinned by ADR-088. Single source of truth so tests can
# import and inspect ; the literal must match the `feature_flags.key`
# column in any future migration that seeds it.
_FEATURE_FLAG_NAME: Final[str] = "phase_d_w115c_confluence_enabled"

# Canonical expert kinds expected in `brier_aggregator_weights`.
# `cli/run_brier_aggregator.py` always writes exactly these three per
# pocket ; a pocket missing any of them is incomplete and treated as
# "no data".
_EXPERT_PROD: Final[str] = "prod_predictor"
_EXPERT_CLIMATOLOGY: Final[str] = "climatology"
_EXPERT_EQUAL: Final[str] = "equal_weight"

# Hysteresis dead-band thresholds (ADR-088 round-28 amendment).
# Enter `high_skill` only when skill_delta crosses ABOVE _HIGH_ENTER.
# Exit `high_skill` only when skill_delta drops BELOW _HIGH_EXIT.
# Symmetric for `anti_skill`. Dead-band width = 0.02 (2 percentage
# points) prevents flicker as skill_delta noise oscillates near the
# boundary.
_HIGH_ENTER: Final[float] = 0.05
_HIGH_EXIT: Final[float] = 0.03
_ANTI_ENTER: Final[float] = -0.05
_ANTI_EXIT: Final[float] = -0.03

# Minimum observations before any band classification — small-sample
# shielding. Vovk requires n >= 4 mathematically ; we go conservative
# at 5 to absorb some sample noise.
_MIN_N_OBSERVATIONS_DEFAULT: Final[int] = 5

ConfidenceBand = Literal["high_skill", "neutral", "anti_skill"]


@dataclass(frozen=True)
class PocketSkill:
    """Read-only Vovk skill diagnostic for one `(asset, regime)` pocket.

    Returned by `read_pocket()` ; consumed by Pass-3 stress when the
    orchestrator threads `confluence_section`. The 4-pass orchestrator
    is responsible for persisting `confidence_band` across calls so
    the hysteresis state is maintained (typically via re-fetching the
    previous session_card_audit row's stored band).
    """

    asset: str
    regime: str
    pocket_version: int
    prod_weight: float
    climatology_weight: float
    equal_weight_weight: float
    skill_delta: float
    """`prod_weight - equal_weight_weight`. In practice spans [-0.10, +0.20]."""
    n_observations: int
    confidence_band: ConfidenceBand
    """Hysteresis-stable band classification (see `_classify_band`)."""


def _classify_band(
    skill_delta: float,
    *,
    n_observations: int,
    min_n: int,
    previous_band: ConfidenceBand | None,
) -> ConfidenceBand:
    """Apply hysteresis dead-band classification (ADR-088 round-28).

    Logic :
    * If `n < min_n` → always `neutral` (small-sample shielding).
    * If `previous_band is None` (cold-start) → use strict-enter
      thresholds : `high_skill` only if `>= _HIGH_ENTER`, `anti_skill`
      only if `<= _ANTI_ENTER`, else `neutral`.
    * If `previous_band == "high_skill"` : stay `high_skill` until
      `skill_delta` drops BELOW `_HIGH_EXIT` (then `neutral`).
    * If `previous_band == "anti_skill"` : stay `anti_skill` until
      `skill_delta` rises ABOVE `_ANTI_EXIT` (then `neutral`).
    * If `previous_band == "neutral"` : check strict-enter thresholds.

    The dead-band prevents flicker : a pocket fluctuating around
    `skill_delta = -0.049 / -0.051` will NOT toggle anti_skill↔neutral
    every nightly Vovk fire.
    """
    if n_observations < min_n:
        return "neutral"

    if previous_band == "high_skill":
        return "high_skill" if skill_delta >= _HIGH_EXIT else "neutral"
    if previous_band == "anti_skill":
        return "anti_skill" if skill_delta <= _ANTI_EXIT else "neutral"

    # Cold-start OR previously-neutral → strict enter thresholds.
    if skill_delta >= _HIGH_ENTER:
        return "high_skill"
    if skill_delta <= _ANTI_ENTER:
        return "anti_skill"
    return "neutral"


async def _is_feature_enabled(session: AsyncSession) -> bool:
    """Wrapper over `feature_flags.is_enabled` with the W115c flag key.

    Returns False if the flag row is absent (fail-closed pattern,
    consistent with W116c addendum generator). Cached for 60s via the
    `feature_flags` service local cache.
    """
    return await is_enabled(session, _FEATURE_FLAG_NAME)


async def read_pocket(
    session: AsyncSession,
    *,
    asset: str,
    regime: str,
    pocket_version: int = 1,
    min_n_observations: int = _MIN_N_OBSERVATIONS_DEFAULT,
    previous_band: ConfidenceBand | None = None,
) -> PocketSkill | None:
    """Read Vovk pocket weights and return a hysteresis-stable
    `PocketSkill` diagnostic.

    Returns `None` when :
    * The W115c feature flag is OFF (fail-closed, NEVER raises).
    * The pocket is incomplete (missing any of the 3 expert kinds).

    Returns a `PocketSkill` with `confidence_band="neutral"` when :
    * The pocket exists but `n_observations < min_n_observations`
      (small-sample shielding).

    Arguments :
    * `asset` — e.g. "EUR_USD".
    * `regime` — e.g. "usd_complacency".
    * `pocket_version` — defaults to 1. Increment when Vovk math changes
      (`brier_aggregator_weights.pocket_version` is part of the UNIQUE
      key).
    * `min_n_observations` — small-sample threshold ; default 5.
    * `previous_band` — caller's last-known band for this pocket. The
      orchestrator threads this from the previous session_card_audit
      row (when available) so hysteresis state persists across calls.
      Pass `None` for cold-start (strict-enter thresholds applied).

    Performance : single SQL SELECT on `(asset, regime, pocket_version)`
    UNIQUE index returns ≤ 3 rows. <5ms p99 expected.
    """
    if not await _is_feature_enabled(session):
        return None

    stmt = select(BrierAggregatorWeight).where(
        BrierAggregatorWeight.asset == asset,
        BrierAggregatorWeight.regime == regime,
        BrierAggregatorWeight.pocket_version == pocket_version,
    )
    rows = list((await session.execute(stmt)).scalars().all())

    # Build per-expert dict — pocket must have all three to be valid.
    by_expert: dict[str, BrierAggregatorWeight] = {r.expert_kind: r for r in rows}
    prod = by_expert.get(_EXPERT_PROD)
    clim = by_expert.get(_EXPERT_CLIMATOLOGY)
    eq = by_expert.get(_EXPERT_EQUAL)

    if prod is None or clim is None or eq is None:
        return None

    # n_observations should be identical across the 3 expert rows
    # (they're updated together each Vovk fire). Take max defensively.
    n_obs = max(prod.n_observations, clim.n_observations, eq.n_observations)

    skill_delta = prod.weight - eq.weight
    band = _classify_band(
        skill_delta,
        n_observations=n_obs,
        min_n=min_n_observations,
        previous_band=previous_band,
    )

    return PocketSkill(
        asset=asset,
        regime=regime,
        pocket_version=pocket_version,
        prod_weight=prod.weight,
        climatology_weight=clim.weight,
        equal_weight_weight=eq.weight,
        skill_delta=skill_delta,
        n_observations=n_obs,
        confidence_band=band,
    )


def render_pass3_addendum(skill: PocketSkill) -> str:
    """Render a calibration-hint addendum for Pass-3 stress prompt.

    NOT a directive. NOT an override of Pass-2 bias / conviction.
    Only a hint about *how confident the Pass-3 stress should be* in
    the prior 4-pass output for this pocket. ADR-017 boundary intact
    by construction — no BUY/SELL/TARGET/ENTRY tokens emitted.
    """
    if skill.confidence_band == "high_skill":
        framing = (
            "The 4-pass output for this pocket has historically been "
            "*more reliable than equal-weight* on realized outcomes. "
            "Weight Pass-2 bias and conviction with default trust."
        )
    elif skill.confidence_band == "anti_skill":
        framing = (
            "The 4-pass output for this pocket has historically been "
            "*less reliable than equal-weight* on realized outcomes. "
            "When evaluating Pass-2 bias and conviction, weight "
            "invalidation risks higher than your default."
        )
    else:  # neutral
        framing = (
            "The 4-pass output for this pocket has marginal historical "
            "skill vs equal-weight. Apply default invalidation discipline."
        )

    return (
        f"[Round-28 Phase D W115c confluence signal]\n"
        f"Pocket ({skill.asset}, {skill.regime}) : "
        f"{skill.confidence_band} "
        f"(n={skill.n_observations}, skill_delta={skill.skill_delta:+.4f}).\n"
        f"{framing}"
    )


__all__ = [
    "_FEATURE_FLAG_NAME",
    "ConfidenceBand",
    "PocketSkill",
    "_classify_band",
    "read_pocket",
    "render_pass3_addendum",
]
