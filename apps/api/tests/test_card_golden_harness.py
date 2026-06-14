"""S06 Chantier C · C-3 — full-CARD golden diff harness (complement to C-1).

PURPOSE
-------
The C-1 harness (``test_fuser_golden_harness``) freezes only the conviction
**fuser** surface (``ConvictionGrounding``) + the ``_derive_direction_and_conviction``
3-tuple seam. It does NOT guard the rest of the deterministic verdict-CARD
assembly — ``_derive_nature`` (ADR-106 D2 classification), the 800-char
``_build_coach_explanation_populated`` coach text, and the Paris ``_window_stamps``.
A C-2/C-3 change to any of those (or to a constant they read) would slip past the
fuser golden — the gap flagged at ``test_fuser_golden_harness.py:26-37`` as a
C-2/C-3 TODO. This module closes it.

It freezes the COMBINED output of the pure card-assembly helpers
(``build_session_verdict`` calls these exact functions, in this exact way, to
populate the ``SessionVerdict`` it returns) across a deterministic matrix into a
committed golden snapshot, then asserts the live helpers still reproduce it. Pure
+ additive: it imports the existing helpers and adds NO production code, so it can
never change live behaviour — exactly the C-1 discipline.

Scope boundary (read before relying on this guard)
--------------------------------------------------
This freezes the deterministic assembly **logic** (direction / conviction /
nature / coach text / Paris windows). It does NOT execute the async, DB-bound
``build_session_verdict`` itself, so it does not guard the final pydantic
field-WIRING (which helper output maps to which ``SessionVerdict`` field) nor the
side-effect carriers (live triggers, invalidation monitor, tradeability) — those
need a live session. A follow-up that makes ``build_session_verdict`` delegate to
a single extracted ``build_session_verdict_from_primitives`` would let this guard
cover the wiring too; that touches the apex path and is a separate gated slice.

Regenerate the golden DELIBERATELY (only after an INTENDED assembly change) with::

    ICHOR_REGEN_GOLDEN=1 uv run --directory apps/api --no-sync \
        pytest tests/test_card_golden_harness.py -q

(The harness writes canonical ``json.dumps(sort_keys=True, indent=2)`` already
byte-identical to prettier 3.8.3 for this file, so no prettier step is needed —
unlike the C-1 golden. ``pytest`` compares structurally regardless.)

Doctrine anchors: ADR-017 (no trade token leaks into the coach text across the
whole matrix) · ADR-022 (every conviction in [0, 95]) · ADR-009 (pure, zero I/O).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from ichor_api.services.conviction_fusion import CONVICTION_CEIL_PCT
from ichor_api.services.session_verdict_builder import (
    _build_coach_explanation_populated,
    _derive_direction_and_conviction,
    _derive_nature,
    _window_stamps_paris,
)

# Verbatim mirror of the proven CI-clean trade-token regex (test_conviction_fusion.py:25-28).
_FORBIDDEN_RE = re.compile(
    r"\b(BUY|SELL|TP|SL|long entry|short entry|stop loss|take profit)\b",
    re.IGNORECASE,
)

_FLOAT_NDIGITS = 9
_GOLDEN_PATH = Path(__file__).resolve().parent / "golden" / "session_card_golden.json"

# A FIXED instant so the Paris window stamps are deterministic (the only now_utc
# input to the assembly). 2026-06-09 is inside CEST; the window math is pinned.
_NOW = datetime(2026, 6, 9, 12, 0, tzinfo=UTC)

_PRIORITY_ASSETS: tuple[str, ...] = (
    "EUR_USD",
    "GBP_USD",
    "XAU_USD",
    "SPX500_USD",
    "NAS100_USD",
)

# Explicit 7-bucket Pass-6 decompositions chosen to exercise every ``_derive_nature``
# branch (momentum tail-heavy / structured mid-heavy / range_bound base-heavy /
# uncertain mixed) AND the dead-zone bands that change the assembled CARD: HARD
# (coin-flip → neutral/0), SOFT (``soft_zone_up`` → attenuated, surfaces the buffer
# clause in the coach), FULL edge, and near-cap. Each sums to 1.0. NB the >800-char
# coach truncation branch (``_build_coach_explanation_populated`` drops the rationale)
# is UNREACHABLE with the current 3-layer evidence (max coach ~631) — like C-1's
# ``AGREEMENT_FLOOR``, it becomes reachable once C-3b wires votes that lengthen the
# rationale, and MUST be frozen with a fixture then. (label order = builder order.)
_SCENARIO_FIXTURES: tuple[tuple[str, dict[str, float]], ...] = (
    (
        "momentum_up",
        {
            "crash_flush": 0.02,
            "strong_bear": 0.03,
            "mild_bear": 0.05,
            "base": 0.10,
            "mild_bull": 0.05,
            "strong_bull": 0.25,
            "melt_up": 0.50,
        },
    ),
    (
        "momentum_down",
        {
            "crash_flush": 0.50,
            "strong_bear": 0.25,
            "mild_bear": 0.05,
            "base": 0.10,
            "mild_bull": 0.05,
            "strong_bull": 0.03,
            "melt_up": 0.02,
        },
    ),
    (
        "structured_up",
        {
            "crash_flush": 0.02,
            "strong_bear": 0.05,
            "mild_bear": 0.08,
            "base": 0.15,
            "mild_bull": 0.45,
            "strong_bull": 0.20,
            "melt_up": 0.05,
        },
    ),
    (
        "structured_down",
        {
            "crash_flush": 0.05,
            "strong_bear": 0.20,
            "mild_bear": 0.45,
            "base": 0.15,
            "mild_bull": 0.08,
            "strong_bull": 0.05,
            "melt_up": 0.02,
        },
    ),
    (
        "range_bound",
        {
            "crash_flush": 0.02,
            "strong_bear": 0.05,
            "mild_bear": 0.08,
            "base": 0.70,
            "mild_bull": 0.08,
            "strong_bull": 0.05,
            "melt_up": 0.02,
        },
    ),
    (
        "uncertain_mixed_up",
        {
            "crash_flush": 0.10,
            "strong_bear": 0.10,
            "mild_bear": 0.10,
            "base": 0.18,
            "mild_bull": 0.12,
            "strong_bull": 0.15,
            "melt_up": 0.25,
        },
    ),
    (
        "coinflip_hard",
        {
            "crash_flush": 0.10,
            "strong_bear": 0.14,
            "mild_bear": 0.10,
            "base": 0.30,
            "mild_bull": 0.10,
            "strong_bull": 0.16,
            "melt_up": 0.10,
        },
    ),
    (
        "near_cap_up",
        {
            "crash_flush": 0.00,
            "strong_bear": 0.03,
            "mild_bear": 0.02,
            "base": 0.05,
            "mild_bull": 0.05,
            "strong_bull": 0.45,
            "melt_up": 0.40,
        },
    ),
    (
        # spread = bullish(0.30) - bearish(0.20) = 0.10 → lands in the graded SOFT
        # dead-zone (0.05 < 0.10 < 0.15) so soft_zone_scale < 1.0 and the coach
        # surfaces the "bord directionnel faible (zone tampon)" attenuation clause —
        # the headline S04 graded-dead-zone behaviour, frozen here at CARD level.
        "soft_zone_up",
        {
            "crash_flush": 0.05,
            "strong_bear": 0.05,
            "mild_bear": 0.10,
            "base": 0.30,
            "mild_bull": 0.15,
            "strong_bull": 0.10,
            "melt_up": 0.05,
        },
    ),
)

# (tag, confluence_lean, theme_present, dollar_consensus, dollar_strength) — a small
# set that varies the conviction (→ coach text) without exploding the matrix.
_EVIDENCE_COMBOS: tuple[tuple[str, str | None, bool, str | None, float], ...] = (
    ("no_evidence", None, False, None, 0.0),
    ("all_aligned_up", "long", True, "usd_down", 1.0),
    ("all_opposed_up", "short", False, "usd_up", 1.0),
)


@dataclass(frozen=True, slots=True)
class CardCase:
    """One deterministic input row of the full-card golden matrix."""

    case_id: str
    asset: str
    scenario_tag: str
    confluence_lean: str | None
    theme_present: bool
    dollar_consensus: str | None
    dollar_strength: float


def _scenarios_for(tag: str) -> list[dict[str, Any]]:
    """The 7-bucket Pass-6 list for a fixture tag (stable label order)."""
    buckets = dict(_SCENARIO_FIXTURES)[tag]
    order = (
        "crash_flush",
        "strong_bear",
        "mild_bear",
        "base",
        "mild_bull",
        "strong_bull",
        "melt_up",
    )
    return [{"label": lbl, "p": buckets[lbl]} for lbl in order]


def build_input_matrix() -> tuple[CardCase, ...]:
    """Deterministic, stable-order matrix. Two sub-matrices:

    1. **behaviour** — EUR_USD × every scenario × every evidence combo: locks the
       nature / dead-zone / conviction / coach behaviour space.
    2. **asset_probe** — every priority asset × ``near_cap_up`` × ``no_evidence``:
       locks the per-asset coach text + dollar-sign composition.
    """
    cases: list[CardCase] = []
    for scn_tag, _ in _SCENARIO_FIXTURES:
        for ev_tag, lean, theme, usd, strength in _EVIDENCE_COMBOS:
            cases.append(
                CardCase(
                    case_id=f"behaviour/{scn_tag}/{ev_tag}",
                    asset="EUR_USD",
                    scenario_tag=scn_tag,
                    confluence_lean=lean,
                    theme_present=theme,
                    dollar_consensus=usd,
                    dollar_strength=strength,
                )
            )
    for asset in _PRIORITY_ASSETS:
        cases.append(
            CardCase(
                case_id=f"asset_probe/near_cap_up/{asset}",
                asset=asset,
                scenario_tag="near_cap_up",
                confluence_lean=None,
                theme_present=False,
                dollar_consensus=None,
                dollar_strength=0.0,
            )
        )
    return tuple(cases)


def _r(value: float) -> float:
    return round(float(value), _FLOAT_NDIGITS)


def compute_card(case: CardCase) -> dict[str, Any]:
    """Assemble the deterministic card fields exactly as ``build_session_verdict``
    does, from the case primitives — the surface this harness freezes."""
    scenarios = _scenarios_for(case.scenario_tag)
    direction, conviction_pct, rationale_fr = _derive_direction_and_conviction(
        scenarios,
        asset=case.asset,
        confluence_lean=case.confluence_lean,
        theme_present=case.theme_present,
        dollar_consensus=case.dollar_consensus,
        dollar_strength=case.dollar_strength,
    )
    nature = _derive_nature(scenarios)
    coach = _build_coach_explanation_populated(
        cast("Any", case.asset),
        direction,
        conviction_pct,
        nature,
        scenarios,
        rationale_fr,
    )
    window_open, window_close, expires = _window_stamps_paris(_NOW)
    return {
        "direction": direction,
        "conviction_pct": _r(conviction_pct),
        "nature": nature,
        "coach_explanation": coach,
        "window_open_paris": window_open.isoformat(),
        "window_close_paris": window_close.isoformat(),
        "expires_at_utc": expires.isoformat(),
    }


def _build_snapshot() -> dict[str, Any]:
    cases = {case.case_id: compute_card(case) for case in build_input_matrix()}
    return {
        "_meta": {
            "contract": (
                "S06 Chantier C full-card golden harness. Frozen deterministic "
                "card assembly (direction/conviction/nature/coach/Paris windows) "
                "over build_input_matrix(). Complements the C-1 fuser golden. "
                "Regenerate ONLY via ICHOR_REGEN_GOLDEN=1 after an INTENDED change."
            ),
            "case_count": len(cases),
            "now_utc": _NOW.isoformat(),
            "float_ndigits": _FLOAT_NDIGITS,
        },
        "cases": cases,
    }


def load_golden() -> dict[str, Any]:
    assert _GOLDEN_PATH.is_file(), (
        f"golden snapshot missing: {_GOLDEN_PATH}\n"
        f"Generate it with ICHOR_REGEN_GOLDEN=1 pytest {Path(__file__).name}"
    )
    data: dict[str, Any] = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))
    return data


def regenerate_golden() -> dict[str, Any]:
    snapshot = _build_snapshot()
    _GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    _GOLDEN_PATH.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return snapshot


def assert_card_golden() -> None:
    """Assert the live assembly helpers reproduce the committed golden card-for-card."""
    golden = load_golden()
    golden_cases: dict[str, Any] = golden["cases"]
    for case in build_input_matrix():
        got = compute_card(case)
        expected = golden_cases.get(case.case_id)
        assert expected is not None, f"golden has no case {case.case_id!r} — regenerate"
        assert got == expected, (
            f"card golden drift @ {case.case_id}\n  got     : {got}\n  expected: {expected}"
        )


# --------------------------------------------------------------------------- #
# Tests                                                                        #
# --------------------------------------------------------------------------- #


def test_regenerate_golden_snapshot() -> None:
    if os.environ.get("ICHOR_REGEN_GOLDEN") != "1":
        pytest.skip("set ICHOR_REGEN_GOLDEN=1 to (re)write the golden snapshot")
    snapshot = regenerate_golden()
    assert snapshot["cases"], "regenerated an empty snapshot"


def test_matrix_is_deterministic_and_unique() -> None:
    first = build_input_matrix()
    second = build_input_matrix()
    assert first == second, "build_input_matrix is non-deterministic"
    ids = [c.case_id for c in first]
    assert len(ids) == len(set(ids)), "duplicate case_id in the matrix"
    # 9 scenarios × 3 evidence + 5 asset probes = 27 + 5 = 32.
    assert len(ids) == 32, f"unexpected matrix size {len(ids)} (expected 32)"


def test_matrix_covers_every_nature_and_direction() -> None:
    """The matrix must exercise all 4 natures and all 3 directions, so the golden
    is a meaningful guard (not a trivial all-uncertain snapshot)."""
    cards = [compute_card(c) for c in build_input_matrix()]
    natures = {c["nature"] for c in cards}
    directions = {c["direction"] for c in cards}
    assert natures == {"momentum", "structured", "range_bound", "uncertain"}, (
        f"missing a nature: {natures}"
    )
    assert directions == {"up", "down", "neutral"}, f"missing a direction: {directions}"
    # The graded SOFT dead-zone must be genuinely exercised (not just claimed): at
    # least one coach surfaces the buffer-clause that only appears when soft_zone_scale<1.
    assert any("zone tampon" in c["coach_explanation"] for c in cards), (
        "soft dead-zone never exercised — add/keep a soft_zone fixture (spread 0.05-0.15)"
    )


def test_card_reproduces_golden() -> None:
    """THE regression guard: live assembly still matches the frozen snapshot."""
    assert_card_golden()


def test_golden_meta_matches_matrix() -> None:
    golden = load_golden()
    matrix_ids = {c.case_id for c in build_input_matrix()}
    golden_ids = set(golden["cases"].keys())
    assert golden_ids == matrix_ids, (
        f"golden/matrix case set drift\n"
        f"  only in golden: {sorted(golden_ids - matrix_ids)}\n"
        f"  only in matrix: {sorted(matrix_ids - golden_ids)}\n"
        f"Regenerate with ICHOR_REGEN_GOLDEN=1."
    )
    assert golden["_meta"]["case_count"] == len(matrix_ids)
    assert golden["_meta"]["now_utc"] == _NOW.isoformat()


def test_no_trade_tokens_in_any_coach_text() -> None:
    """ADR-017: no coach_explanation in the whole matrix emits a trade-signal token."""
    for case in build_input_matrix():
        coach = compute_card(case)["coach_explanation"]
        assert _FORBIDDEN_RE.search(coach) is None, f"trade token leaked @ {case.case_id}"


def test_coach_within_pydantic_bounds() -> None:
    """The coach text must stay inside the SessionVerdict.coach_explanation contract
    (``min_length=80``, ``max_length=800``) so the assembled card never 422s."""
    for case in build_input_matrix():
        coach = compute_card(case)["coach_explanation"]
        assert 80 <= len(coach) <= 800, (
            f"coach length {len(coach)} out of [80, 800] @ {case.case_id}"
        )


def test_all_convictions_within_cap95() -> None:
    """ADR-022: every conviction in the matrix is within [0, 95]."""
    for case in build_input_matrix():
        conviction = compute_card(case)["conviction_pct"]
        assert 0.0 <= conviction <= CONVICTION_CEIL_PCT, (
            f"conviction {conviction} out of [0, 95] @ {case.case_id}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
