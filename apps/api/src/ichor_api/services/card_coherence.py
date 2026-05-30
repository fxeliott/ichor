"""Card coherence reconciliation + thesis synthesis (content-correctness wave).

Closes three correctness defects found in the 2026-05-30 live-card audit
where the headline `bias_direction` had drifted away from the underlying
evidence (the 7-bucket scenario probability distribution + the quantitative
confluence drivers) :

  - EUR/USD shipped bias=long while its scenario mass was net BEARISH
    (bear 0.36 vs bull 0.29) AND its quant drivers summed negative — a
    long label the model's own probabilities contradicted.
  - NAS100 shipped bias=long and SPX500 bias=neutral on a near-identical
    cash-closed overnight backdrop — arbitrary Pass-2 LLM variance, not a
    coded rule (both are US equity indices, cash market closed).

Two pure functions, no I/O, fully testable :

  1. `reconcile_coherence(...)` — WRITE-time gate (called from
     `cli/run_session_card.py` just before persist). It NEVER promotes /
     flips a bias (that would manufacture a directional call the model did
     not make). It only DEMOTES toward neutral when the evidence is
     contradictory or insufficient, and shaves conviction when the edge is
     weak. The reconciled bias/conviction are what get persisted (so Brier
     calibration scores the honest prediction).

  2. `synthesize_thesis(...)` — READ-time (called from
     `schemas.SessionCardOut.from_orm_row`). Builds the 1-3 sentence verdict
     a trader reads first, describing the *stored* card and surfacing any
     scenario / driver tension. It does NOT change the bias (so the thesis
     never contradicts the badge for historical cards — it flags the
     tension instead, per the "surface, don't silently override" rule).

ADR-017 boundary : the synthesized thesis uses only the existing
probabilistic vocabulary (biais haussier/baissier/neutre, conviction) —
never BUY/SELL/entry/stop tokens. Guarded by a test asserting
`adr017_filter.find_violations(thesis) == ()`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# ── Canonical 7-bucket partition (ADR-085) ──────────────────────────────
# Source of truth for the labels is `ichor_brain.scenarios.BUCKET_LABELS`
# (CI-guarded). We partition them into bull / bear / neutral here ; the
# test `test_card_coherence.py::test_bucket_partition_covers_canonical`
# asserts this partition is exactly BUCKET_LABELS (drift guard).
BULL_BUCKETS: frozenset[str] = frozenset({"mild_bull", "strong_bull", "melt_up"})
BEAR_BUCKETS: frozenset[str] = frozenset({"crash_flush", "strong_bear", "mild_bear"})
NEUTRAL_BUCKETS: frozenset[str] = frozenset({"base"})

# US cash-equity indices — treated more strictly on the closed overnight
# than 24h-traded FX (mission-4 SPX/NAS symmetry).
US_EQUITY_ASSETS: frozenset[str] = frozenset({"SPX500_USD", "NAS100_USD"})
# Sessions where US cash equity is CLOSED with no imminent cash session, so an
# index directional bias rests on thin overnight index-futures only and needs
# a stronger scenario lean. Both ny_close (post-close drift) AND pre_londres
# (≈00:00 ET, London = US deep-overnight) qualify — uniform "même traitement
# session-fermée" (mission-4). DELIBERATELY EXCLUDED : pre_ny (forecasts the
# imminent NY cash open → a directional equity call IS legitimate there) and
# ny_mid (US cash is open).
EQUITY_OVERNIGHT_SESSIONS: frozenset[str] = frozenset({"pre_londres", "ny_close"})

# Dead-band on |bull_mass - bear_mass| below which the scenario distribution
# is judged directionless. FX trades ~24h so a modest lean still counts ;
# US equity on the cash-closed overnight needs a stronger lean to justify
# carrying a directional bias overnight.
FX_SCENARIO_DEADBAND = 0.05
EQUITY_OVERNIGHT_DEADBAND = 0.12
# Dead-band on the summed quant-driver contribution (∈ roughly [-1, 1]).
DRIVER_DEADBAND = 0.10

# When a directional bias is demoted to neutral, conviction expresses
# "confidence in a range/no-clear-direction read" — cap it modestly.
NEUTRAL_CONVICTION_CAP = 35.0
# A directional bias sitting on a balanced distribution keeps its direction
# but loses conviction (honest weak edge).
WEAK_CONVICTION_SCALE = 0.85
WEAK_DRIVER_DISAGREE_SCALE = 0.70
ALIGNED_DRIVER_DISAGREE_SCALE = 0.90
# Conviction is capped at 95 anywhere in the pipeline (ADR-017/022).
CONVICTION_CEILING = 95.0

ASSET_DISPLAY: dict[str, str] = {
    "EUR_USD": "EUR/USD",
    "GBP_USD": "GBP/USD",
    "USD_CAD": "USD/CAD",
    "XAU_USD": "Or (XAU/USD)",
    "SPX500_USD": "S&P 500",
    "NAS100_USD": "Nasdaq 100",
}
_BIAS_WORD: dict[str, str] = {"long": "haussier", "short": "baissier", "neutral": "neutre"}


def scenario_masses(
    scenarios: Sequence[Mapping[str, Any]] | None,
) -> tuple[float, float, float, float]:
    """Return (bull_mass, bear_mass, base_mass, expected_move).

    `expected_move` is the probability-weighted midpoint of each bucket's
    magnitude range (pips for FX, points for indices/gold — caller treats
    it as a directional tilt, not an absolute). Robust to missing/None
    fields.
    """
    bull = bear = base = expected = 0.0
    for entry in scenarios or []:
        if not isinstance(entry, Mapping):
            continue
        label = entry.get("label")
        try:
            p = float(entry.get("p") or 0.0)
        except (TypeError, ValueError):
            continue
        if label in BULL_BUCKETS:
            bull += p
        elif label in BEAR_BUCKETS:
            bear += p
        elif label in NEUTRAL_BUCKETS:
            base += p
        mag = entry.get("magnitude_pips")
        if isinstance(mag, (list, tuple)) and len(mag) == 2:
            try:
                expected += p * (float(mag[0]) + float(mag[1])) / 2.0
            except (TypeError, ValueError):
                pass
    return bull, bear, base, expected


def driver_net(drivers: Sequence[Mapping[str, Any]] | None) -> float:
    """Sum of confluence-driver contributions (positive = long the asset)."""
    if not drivers:
        return 0.0
    total = 0.0
    for d in drivers:
        if not isinstance(d, Mapping):
            continue
        try:
            total += float(d.get("contribution") or 0.0)
        except (TypeError, ValueError):
            continue
    return total


def _lean(bull: float, bear: float, deadband: float) -> str:
    diff = bull - bear
    if diff > deadband:
        return "long"
    if diff < -deadband:
        return "short"
    return "neutral"


def _driver_lean(drivers: Sequence[Mapping[str, Any]] | None) -> str:
    net = driver_net(drivers)
    if net > DRIVER_DEADBAND:
        return "long"
    if net < -DRIVER_DEADBAND:
        return "short"
    return "neutral"


def _opposite(bias: str) -> str:
    return "short" if bias == "long" else "long"


@dataclass(frozen=True)
class CoherenceVerdict:
    """Result of the write-time coherence reconciliation.

    `bias` / `conviction` are the values to persist. `adjusted` is True
    when either changed. `agreement` / `reason` are machine labels for
    structured logging + tests.
    """

    bias: str
    conviction: float
    original_bias: str
    original_conviction: float
    scenario_lean: str
    driver_lean: str
    bull_mass: float
    bear_mass: float
    base_mass: float
    expected_move: float
    adjusted: bool
    agreement: str
    reason: str


def reconcile_coherence(
    *,
    asset: str,
    session_type: str,
    bias: str,
    conviction: float,
    scenarios: Sequence[Mapping[str, Any]] | None,
    drivers: Sequence[Mapping[str, Any]] | None,
) -> CoherenceVerdict:
    """Reconcile the headline bias/conviction with the scenario distribution.

    Demote-only policy (never promote/flip) :

      - directional bias contradicted by a clear opposite scenario lean
        → neutral (EUR/USD long-vs-bearish-mass case).
      - US-equity directional bias on the cash-closed overnight without a
        strong lean → neutral (SPX/NAS symmetry).
      - directional bias on a balanced distribution → kept, conviction
        shaved (honest weak edge), shaved further if drivers disagree.
      - aligned bias whose drivers disagree → kept, conviction shaved
        modestly + surfaced.
    """
    bull, bear, base, expected = scenario_masses(scenarios)
    is_equity_overnight = asset in US_EQUITY_ASSETS and session_type in EQUITY_OVERNIGHT_SESSIONS
    deadband = EQUITY_OVERNIGHT_DEADBAND if is_equity_overnight else FX_SCENARIO_DEADBAND
    s_lean = _lean(bull, bear, deadband)
    d_lean = _driver_lean(drivers)

    new_bias = bias
    new_conv = conviction
    agreement = "neutral_bias"
    reason = "neutral_bias"

    if bias in ("long", "short"):
        opp = _opposite(bias)
        if s_lean == opp:
            new_bias = "neutral"
            new_conv = min(conviction, NEUTRAL_CONVICTION_CAP)
            agreement = "contradicted"
            reason = f"scenario_mass_{s_lean}_vs_bias_{bias}"
        elif is_equity_overnight and s_lean == "neutral":
            new_bias = "neutral"
            new_conv = min(conviction, NEUTRAL_CONVICTION_CAP)
            agreement = "equity_overnight_clamp"
            reason = "equity_overnight_insufficient_lean"
        elif s_lean == "neutral":
            if d_lean == opp:
                new_conv = conviction * WEAK_DRIVER_DISAGREE_SCALE
                agreement = "weak_driver_disagree"
                reason = "balanced_distribution_driver_disagree"
            else:
                new_conv = conviction * WEAK_CONVICTION_SCALE
                agreement = "weak"
                reason = "balanced_distribution"
        else:  # s_lean == bias direction → aligned
            if d_lean == opp:
                new_conv = conviction * ALIGNED_DRIVER_DISAGREE_SCALE
                agreement = "aligned_driver_disagree"
                reason = "scenario_aligned_driver_disagree"
            else:
                agreement = "aligned"
                reason = "aligned"

    new_conv = max(0.0, min(CONVICTION_CEILING, new_conv))
    adjusted = new_bias != bias or abs(new_conv - conviction) > 1e-9
    return CoherenceVerdict(
        bias=new_bias,
        conviction=new_conv,
        original_bias=bias,
        original_conviction=conviction,
        scenario_lean=s_lean,
        driver_lean=d_lean,
        bull_mass=bull,
        bear_mass=bear,
        base_mass=base,
        expected_move=expected,
        adjusted=adjusted,
        agreement=agreement,
        reason=reason,
    )


def _conviction_word(conviction: float) -> str:
    if conviction < 30:
        return "faible"
    if conviction < 50:
        return "modérée"
    if conviction < 70:
        return "moyenne"
    return "élevée"


def synthesize_thesis(
    *,
    asset: str,
    session_type: str,
    bias: str,
    conviction: float,
    regime: str | None,
    scenarios: Sequence[Mapping[str, Any]] | None,
    drivers: Sequence[Mapping[str, Any]] | None,
) -> str:
    """Build the 1-3 sentence verdict for the *stored* card (read-time).

    Describes the persisted bias/conviction and surfaces scenario / driver
    tension. Never flips the bias — flags disagreement instead, so the
    thesis can't contradict the bias badge on historical (pre-gate) cards.
    Deterministic + ADR-017-clean.
    """
    name = ASSET_DISPLAY.get(asset, asset)
    bias_word = _BIAS_WORD.get(bias, "neutre")
    conv_word = _conviction_word(conviction)
    bull, bear, base, _expected = scenario_masses(scenarios)
    has_scen = (bull + bear + base) > 0.5  # a normalized distribution is present

    # S1 — verdict (+ regime parenthetical to save a sentence)
    verdict = f"{name} — biais {bias_word}, conviction {conv_word} ({round(conviction)} %)"
    if regime:
        verdict += f", régime {regime}"
    verdict += "."
    parts = [verdict]

    # S2 — scenario distribution
    s_lean = "neutral"
    if has_scen:
        bull_pct = round(bull * 100)
        bear_pct = round(bear * 100)
        s_lean = _lean(bull, bear, FX_SCENARIO_DEADBAND)
        if s_lean == "neutral":
            parts.append(
                f"Distribution de scénarios équilibrée ({bull_pct} % haussier / {bear_pct} % baissier)."
            )
        else:
            lean_word = "haussière" if s_lean == "long" else "baissière"
            parts.append(
                f"Distribution de scénarios {lean_word} ({bull_pct} % haussier contre {bear_pct} % baissier)."
            )

    # S3 — one coherence note (tension > driver divergence > omit)
    note: str | None = None
    if bias in ("long", "short"):
        opp = _opposite(bias)
        d_lean = _driver_lean(drivers)
        if has_scen and s_lean == opp:
            note = (
                "Tension : la masse de scénarios contredit le biais affiché — "
                "lecture directionnelle à prendre avec prudence."
            )
        elif drivers and d_lean == opp:
            note = "La couche quantitative (drivers) diverge du biais — confluence partielle."
        elif has_scen and s_lean == "neutral":
            note = "Édge faible : distribution sans direction nette."
    if note:
        parts.append(note)

    return " ".join(parts)[:512]
