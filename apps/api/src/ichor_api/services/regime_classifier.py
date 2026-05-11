"""Master regime classifier — 7-bucket macro state from 7 inputs.

Pure function. No DB access. Extracted from `data_pool._section_executive_summary`
(Wave 51 logic, 2026-05-08) into a reusable service so the same classifier
can drive : (a) the 4-pass briefing exec summary, (b) the `/v1/regime`
read endpoint (future), (c) the frontend `useRegimeStore` ambient
(future align — currently drifted), (d) Pass-1 régime priming output.

The 7 buckets are not Stephen Jen's canonical 3-régime dollar smile —
they extend it with Ichor-original buckets to cover what the audit
2026-05-11 G3 surfaced as missing :
  - `crisis`        : panic / fat-tail (VIX > 30 OR SKEW > 150 OR HY OAS > 6%)
  - `broken_smile`  : Stephen Jen 2025-26 "US-driven instability" (term-prem
                      up + vol calm + SKEW elevated)
  - `stagflation`   : growth slowdown + inflation persistence
  - `risk_off`      : classic LEFT-smile stress (USD safe-haven bid)
  - `goldilocks`    : growth-in-trend + loose FCI + inflation at target
  - `risk_on`       : loose FCI + low vol + low SKEW (complacency)
  - `transitional`  : none of the templates match cleanly

The thresholds are heuristic (calibrated against the 2022-2026 cycle).
NOT canonical institutional standards — Eurizon SLJ / Jen maintain a
3-régime framework and JPM Asset Management proposes a "smirk" 2024-26
asymmetric variant. See ADR-082 reframe rationale + researcher 2026-05-11
findings absorbed pre-W104c.

Used by:
  - `services/data_pool._section_executive_summary` (4-pass briefings)
  - `tests/test_regime_classifier.py` (CI guard against threshold drift)

NOT used by:
  - `services/session_scenarios.py` (`RegimeQuadrant` 4-bucket Literal —
    deliberate decoupling for now ; W104c_part2 will add the 7→4 mapping
    via `derive_quadrant_from_master_regime`).
  - `apps/web2/lib/use-regime-ambient.ts` (frontend uses a different
    4-bucket vocabulary — flagged for align in W107 Living Analysis View).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MasterRegime = Literal[
    "crisis",
    "broken_smile",
    "stagflation",
    "risk_off",
    "goldilocks",
    "risk_on",
    "transitional",
]


@dataclass(frozen=True)
class RegimeInputs:
    """Inputs to `classify_master_regime`. All optional — None signals stale
    or absent FRED observation. Classifier degrades gracefully (returns
    `transitional` when key inputs are missing rather than guessing)."""

    skew: float | None  # CBOE SKEW (130 base, 150 stress)
    vix: float | None  # VIX (FRED VIXCLS)
    hy_oas: float | None  # ICE BofA US HY OAS (FRED BAMLH0A0HYM2) in %
    nfci: float | None  # Chicago Fed NFCI (already z-scored by construction)
    cli_us: float | None  # OECD US CLI (FRED USALOLITOAASTSAM, 100 = trend)
    expinf: float | None  # 1y expected inflation (FRED EXPINF1YR) in %
    term_prem: float | None  # 10y term premium (FRED THREEFYTP10) in %


# Per-regime asset-class bias hint (ADR-017 priming — describes the
# macro-consistent observation, NOT a trade signal).
_BIAS_HINTS: dict[MasterRegime, dict[str, str]] = {
    "broken_smile": {
        "fx_majors": "USD-bearish (USD weakness despite vol calm)",
        "xau": "USD-weak + tail-risk-elevated → gold supportive",
        "us_equity_indices": "Mixed (Fed accommodative but USD weakness offsets)",
        "treasuries": "Term-prem expansion → curve steepening",
    },
    "crisis": {
        "fx_majors": "USD-haven bid except USD/JPY (JPY haven)",
        "xau": "Bid (flight to quality)",
        "us_equity_indices": "Sharp downside, vol spike",
        "treasuries": "Bid (duration safe haven)",
    },
    "stagflation": {
        "fx_majors": "USD-mixed (cuts priced but inflation persists)",
        "xau": "Bid (real-yield compression + inflation hedge)",
        "us_equity_indices": "Defensive sectors, growth underperforms",
        "treasuries": "TIPS outperform nominals",
    },
    "risk_off": {
        "fx_majors": "USD bid, EUR/AUD/NZD weak (carry unwind)",
        "xau": "Bid (haven, but real yields can offset)",
        "us_equity_indices": "Downside, vol spike",
        "treasuries": "Bid (haven duration)",
    },
    "goldilocks": {
        "fx_majors": "USD soft (Fed neutral) + EUR/AUD bid",
        "xau": "Range-bound (no panic, no inflation surge)",
        "us_equity_indices": "Bid (low vol + earnings tailwind)",
        "treasuries": "Range-bound mid-curve",
    },
    "risk_on": {
        "fx_majors": "USD soft + AUD/NZD/EM bid (carry on)",
        "xau": "Soft (real yields compress relative)",
        "us_equity_indices": "Strong bid (complacency)",
        "treasuries": "Curve steepens (no haven bid)",
    },
    "transitional": {
        "fx_majors": "Mixed signals, await clearer template",
        "xau": "Range-bound",
        "us_equity_indices": "Range-bound",
        "treasuries": "Range-bound",
    },
}


@dataclass(frozen=True)
class RegimeClassification:
    """Output of `classify_master_regime`. `regime` is the 7-bucket label,
    `rationale` is a 1-line explanation citing inputs, `confidence` is a
    heuristic margin in [0, 1] (NOT a statistical probability), and
    `bias_hints` is the per-asset-class priming for Pass-2 narrative
    generation (ADR-017 compliant — observations, not signals)."""

    regime: MasterRegime
    rationale: str
    confidence: float
    bias_hints: dict[str, str]


def classify_master_regime(inputs: RegimeInputs) -> RegimeClassification:
    """Classify the current macro régime into one of 7 buckets.

    Priority order (first match wins) :
      1. crisis        — panic conditions trump everything
      2. broken_smile  — Stephen Jen 2025-26 US-driven instability
      3. stagflation   — growth slowing + inflation persisting
      4. risk_off      — classic LEFT smile stress (vol or credit blow out)
      5. goldilocks    — growth in trend + loose FCI + anchored inflation
      6. risk_on       — loose FCI + low vol + low SKEW (complacency)
      7. transitional  — fallback when none of the templates match

    The thresholds (SKEW 150 / VIX 30 / HY OAS 6% / etc.) are heuristic
    calibrated on the 2022-2026 cycle. See module docstring for caveats
    on canonical reference. Pure function — no DB access, deterministic.
    """
    skew, vix, hy_oas = inputs.skew, inputs.vix, inputs.hy_oas
    nfci, cli_us = inputs.nfci, inputs.cli_us
    expinf, term_prem = inputs.expinf, inputs.term_prem

    regime: MasterRegime = "transitional"
    rationale = "no clear template match"
    confidence = 0.0

    # 1. Crisis — panic / fat-tail conditions (highest priority)
    if (
        (skew is not None and skew >= 150)
        or (vix is not None and vix >= 30)
        or (hy_oas is not None and hy_oas >= 6.0)
    ):
        regime = "crisis"
        rationale = f"SKEW={skew} VIX={vix} HY-OAS={hy_oas}% — flight to quality"
        c = 0
        if skew is not None and skew >= 150:
            c += 1
        if vix is not None and vix >= 30:
            c += 1
        if hy_oas is not None and hy_oas >= 6.0:
            c += 1
        confidence = c / 3.0

    # 2. Broken smile (Stephen Jen US-driven instability)
    elif (
        term_prem is not None
        and term_prem > 0.0
        and vix is not None
        and vix < 22
        and hy_oas is not None
        and hy_oas < 4.5
        and skew is not None
        and skew >= 130
    ):
        regime = "broken_smile"
        rationale = (
            f"term-prem {term_prem:+.2f}% + VIX {vix:.1f} (modest) + HY-OAS "
            f"{hy_oas:.2f}% (calm) + SKEW {skew:.0f} (elevated) — US-driven "
            "instability per Stephen Jen 2025-26"
        )
        margins: list[float] = [
            min(1.0, max(0.0, (term_prem - 0.0) / 0.5)),
            min(1.0, max(0.0, (22 - vix) / 5)),
            min(1.0, max(0.0, (4.5 - hy_oas) / 1.0)),
            min(1.0, max(0.0, (skew - 130) / 20.0)),
        ]
        confidence = sum(margins) / len(margins)

    # 3. Stagflation — growth slowdown + inflation persistence
    elif cli_us is not None and cli_us < 100 and expinf is not None and expinf > 2.5:
        regime = "stagflation"
        rationale = (
            f"US CLI {cli_us:.2f} (<100, slowdown) + EXPINF1YR {expinf:.2f}% "
            "(>2.5% above target) — growth slowing while inflation persists"
        )
        margins = [
            min(1.0, max(0.0, (100 - cli_us) / 2.0)),
            min(1.0, max(0.0, (expinf - 2.5) / 1.0)),
        ]
        confidence = sum(margins) / len(margins)

    # 4. Risk-off (classic LEFT smile)
    elif (vix is not None and vix > 22) or (hy_oas is not None and hy_oas > 5.0):
        regime = "risk_off"
        rationale = f"VIX {vix} HY-OAS {hy_oas}% — classic stress, USD bid"
        margins = []
        if vix is not None:
            margins.append(min(1.0, max(0.0, (vix - 22) / 8.0)))
        if hy_oas is not None:
            margins.append(min(1.0, max(0.0, (hy_oas - 5.0) / 2.0)))
        confidence = max(margins) if margins else 0.0

    # 5. Goldilocks — growth in trend + loose FCI + anchored inflation
    elif (
        cli_us is not None
        and cli_us > 100
        and nfci is not None
        and nfci < 0
        and expinf is not None
        and 1.5 <= expinf <= 2.5
    ):
        regime = "goldilocks"
        rationale = (
            f"CLI {cli_us:.2f}▲ + NFCI {nfci:+.2f} (loose) + EXPINF1YR "
            f"{expinf:.2f}% near target — growth in trend, calm vol"
        )
        margins = [
            min(1.0, max(0.0, (cli_us - 100) / 2.0)),
            min(1.0, max(0.0, -nfci / 0.5)),
            1.0 if 1.5 <= expinf <= 2.5 else 0.0,
        ]
        confidence = sum(margins) / len(margins)

    # 6. Risk-on (loose conditions, low vol)
    elif (
        nfci is not None
        and nfci < -0.3
        and skew is not None
        and skew < 130
        and vix is not None
        and vix < 18
    ):
        regime = "risk_on"
        rationale = (
            f"NFCI {nfci:+.2f} (loose) + SKEW {skew:.0f} + VIX {vix:.1f} — complacent, equity bid"
        )
        margins = [
            min(1.0, max(0.0, (-0.3 - nfci) / 0.5)),
            min(1.0, max(0.0, (130 - skew) / 15.0)),
            min(1.0, max(0.0, (18 - vix) / 5.0)),
        ]
        confidence = sum(margins) / len(margins)

    return RegimeClassification(
        regime=regime,
        rationale=rationale,
        confidence=confidence,
        bias_hints=_BIAS_HINTS[regime],
    )
