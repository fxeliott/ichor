"""S06 Chantier C · C-1 — golden-card diff harness for the conviction fuser.

PURPOSE (PLAN_DIRECTEUR §4bis · kickoff ``SESSION_LOG_2026-06-14-s06-chantier-c-kickoff``)
-----------------------------------------------------------------------------------------
Chantier C makes the verdict *smarter* by fusing ``>= 9`` ``DimensionVote`` layers
into ``conviction_fusion.fuse_conviction`` (today only 3: confluence / dollar /
theme). Slice **C-2** adds a ``votes: Sequence[DimensionVote] = ()`` parameter to the
fuser and threads it through ``session_verdict_builder._derive_direction_and_conviction``.

That migration MUST be *strictly additive*: with the feature flag OFF (no votes
supplied) the fused conviction has to stay **byte-identical** to today's output
(kickoff "7 CI pitfalls" #4 — pinned values ; ADR-022 cap-95 ; ADR-017 direction is
bucket-only). There was no guard proving that — exhaustive ``golden`` greps hit only
an academic citation (``data_pool.py``). This module **is** that prerequisite guard.

It freezes the CURRENT ``fuse_conviction`` output across a representative input matrix
into a committed golden snapshot, then asserts the live fuser still reproduces it
exactly. Slice C-2 re-runs the SAME guard against its flag-OFF path via
:func:`assert_fuser_golden` / :func:`assert_derive_golden` to prove zero behavioural
drift *before* any dimension is wired. The committed snapshot is the "old" reference
that survives C-2's in-place edit of the fuser.

Pattern mirrors the repo's mechanical-lockstep invariants
(``test_invariants_theme_drivers_lockstep.py``): deterministic, fail-loud on drift.

Scope boundary (read before relying on this guard)
--------------------------------------------------
This freezes the **fuser surface** — ``fuse_conviction`` (full ``ConvictionGrounding``)
plus the builder seam's 3-tuple projection ``_derive_direction_and_conviction``. It is
NOT a guard over the fully-assembled ``SessionVerdict`` "card" (nature, Paris windows,
800-char coach text). That is deliberate: ``fuse_conviction`` is the exact surface C-2
edits, so freezing it is the right prerequisite. But a C-2/C-3 change OUTSIDE the fuser
(verdict assembly) would slip past this — a complementary full-card guard belongs to
C-2/C-3. The matrix is exhaustive over the **reachable** behaviour of the CURRENT
3-layer fuser; defensive bounds unreachable with 3 layers (``AGREEMENT_FLOOR``, the
``fused`` 0.0-floor) are documented at ``_EVIDENCE_COMBOS`` and frozen in C-2 when
``votes`` makes them reachable.

Doctrine anchors
----------------
* ADR-017 — ``direction`` stays bucket-derived; the harness also asserts NO
  trade-signal token leaks into any ``rationale_fr`` across the whole matrix.
* ADR-022 — every fused ``conviction_pct`` in the matrix is within ``[0, 95]``.
* ADR-009 (Voie D) — pure arithmetic, zero I/O / LLM / spend.
* Doctrine #11 — a true coin-flip is frozen as honest ``neutral / 0.0``.

Regenerate the golden DELIBERATELY (only after an INTENDED fusion change) with::

    ICHOR_REGEN_GOLDEN=1 uv run --directory apps/api --no-sync \
        pytest tests/test_fuser_golden_harness.py -q
    pnpm exec prettier --write apps/api/tests/golden/fuser_conviction_golden.json

(the second step keeps the committed golden in the CI prettier 3.8.3 code style;
``pytest`` itself compares the snapshot structurally, so it is format-agnostic).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest
from ichor_api.services.conviction_fusion import (
    CONVICTION_CEIL_PCT,
    ConfluenceLean,
    ConvictionGrounding,
    DollarConsensus,
    fuse_conviction,
)
from ichor_api.services.session_verdict_builder import _derive_direction_and_conviction

# Verbatim mirror of the proven CI-clean trade-token regex (``test_conviction_fusion.py:25-28``,
# same pattern as the ``benchmark_gate.py`` SSOT) — exempt from the ADR-081 pre-commit
# BUY/SELL guard, which skips ``tests/`` files and never scans string literals.
_FORBIDDEN_RE = re.compile(
    r"\b(BUY|SELL|TP|SL|long entry|short entry|stop loss|take profit)\b",
    re.IGNORECASE,
)

# Float precision for the canonical snapshot. ``fuse_conviction`` is pure IEEE-754
# arithmetic over fixed constants, so the SAME inputs + SAME code yield bit-identical
# floats (the flag-OFF C-2 equivalence we guard). Rounding is a belt-and-suspenders
# against any cross-platform shortest-repr quirk between the local (Windows) golden
# writer and the Linux CI checker — it can never mask a flag-OFF drift (identical
# pre-rounding values round identically).
_FLOAT_NDIGITS = 9

_GOLDEN_PATH = Path(__file__).resolve().parent / "golden" / "fuser_conviction_golden.json"

# The 5 verdict priority assets (all USD-quote → sign -1) + a USD-base pair
# (sign +1) + an unknown asset (sign 0) so the per-asset dollar mapping is locked
# across every branch of ``_ASSET_USD_SIGN``.
_PRIORITY_ASSETS: tuple[str, ...] = (
    "EUR_USD",
    "GBP_USD",
    "XAU_USD",
    "SPX500_USD",
    "NAS100_USD",
)
_SIGN_PROBE_ASSETS: tuple[str, ...] = (
    *_PRIORITY_ASSETS,
    "USD_CAD",  # USD-base → sign +1
    "USD_JPY",  # USD-base → sign +1
    "AUD_USD",  # USD-quote → sign -1
    "ZZZ_ZZZ",  # unknown → sign 0 (no dollar implication)
)

# Scenario regimes — (tag, bullish_mass, bearish_mass). Spreads chosen to land on
# every dead-zone branch: hard (<=0.05) → neutral/0 ; soft (0.05<spread<0.15) →
# attenuated ; full (>=0.15) → unattenuated ; and a near-cap base to exercise the
# cap-95 clamp under stacked corroboration.
_SCENARIO_REGIMES: tuple[tuple[str, float, float], ...] = (
    ("coinflip_hard", 0.50, 0.48),  # spread 0.02 ≤ 0.05 → neutral / 0
    ("boundary_hard", 0.05, 0.00),  # spread == 0.05 exactly → neutral / 0
    ("soft_zone_up", 0.30, 0.20),  # spread 0.10 → scale 0.50 (slope anchor)
    ("soft_zone_down", 0.20, 0.30),  # spread 0.10 → down, scale 0.50
    ("soft_zone_shallow_up", 0.29, 0.21),  # spread 0.08 → scale 0.30 (slope anchor)
    ("soft_zone_deep_up", 0.31, 0.19),  # spread 0.12 → scale 0.70 (slope anchor)
    ("full_edge_up", 0.60, 0.40),  # spread 0.20 → up, full strength
    ("full_edge_down", 0.40, 0.60),  # spread 0.20 → down, full strength
    ("strong_up", 0.70, 0.30),  # spread 0.40 → up, legacy max(mass)*100
    ("near_cap_up", 0.90, 0.05),  # base 90 → cap-95 reachable under promotion
    ("near_cap_down", 0.05, 0.90),  # symmetric bearish near-cap
)

# Evidence combos — (tag, confluence_lean, theme_present, dollar_consensus,
# dollar_strength). Cover confluence agree/oppose/neutral/absent, theme presence,
# every dollar consensus value, partial strength, and fully-stacked combos.
_EVIDENCE_COMBOS: tuple[tuple[str, str | None, bool, str | None, float], ...] = (
    ("no_evidence", None, False, None, 0.0),
    ("conf_long", "long", False, None, 0.0),
    ("conf_short", "short", False, None, 0.0),
    ("conf_neutral", "neutral", False, None, 0.0),
    ("theme_only", None, True, None, 0.0),
    ("usd_up_full", None, False, "usd_up", 1.0),
    ("usd_down_full", None, False, "usd_down", 1.0),
    ("usd_up_half", None, False, "usd_up", 0.5),
    ("usd_mixed", None, False, "mixed", 1.0),
    ("usd_neutral_consensus", None, False, "neutral", 1.0),
    ("all_aligned_up_bias", "long", True, "usd_down", 1.0),
    ("all_opposed_up_bias", "short", True, "usd_up", 1.0),
    # Maximal disagreement reachable with the 3-layer fuser: confluence opposed
    # (-1) + dollar opposed at full strength (-1) + theme absent (0) → net_vote -2
    # → agreement_factor 0.80 (the lowest factor the current public API can
    # produce). NOTE: ``AGREEMENT_FLOOR`` (0.60) needs net_vote ≤ -4 and the
    # ``_clamp(fused, 0.0, …)`` lower bound needs a negative product — both are
    # DEFENSIVE bounds that are structurally UNREACHABLE with these 3 layers, so
    # they are intentionally NOT frozen here. They become reachable once C-2 adds
    # ``DimensionVote`` layers that can drive net_vote below -4; C-2 MUST add the
    # cases that exercise + freeze them then.
    ("conf_short_usd_opp_no_theme", "short", False, "usd_up", 1.0),
)


@dataclass(frozen=True, slots=True)
class FuserCase:
    """One deterministic input row of the golden matrix."""

    case_id: str
    asset: str
    bull: float
    bear: float
    confluence_lean: str | None
    theme_present: bool
    dollar_consensus: str | None
    dollar_strength: float


def _scn(bull: float, bear: float) -> list[dict[str, object]]:
    """7-bucket Pass-6 decomposition with the bullish/bearish mass in the strong
    buckets and the remainder in ``base`` (mirrors ``test_conviction_fusion._scn``;
    bullish_mass == ``bull``, bearish_mass == ``bear``, sum(p) == 1.0)."""
    base = max(0.0, 1.0 - bull - bear)
    return [
        {"label": "crash_flush", "p": 0.0},
        {"label": "strong_bear", "p": bear},
        {"label": "mild_bear", "p": 0.0},
        {"label": "base", "p": base},
        {"label": "mild_bull", "p": 0.0},
        {"label": "strong_bull", "p": bull},
        {"label": "melt_up", "p": 0.0},
    ]


def build_input_matrix() -> tuple[FuserCase, ...]:
    """The deterministic, branch-exhaustive input matrix.

    Two sub-matrices, in stable order:

    1. **behaviour** — ``EUR_USD`` fixed × every regime × every evidence combo.
       Asset is irrelevant to the fusion *except* through the dollar sign, so a
       single asset locks the full dead-zone / soft-zone / cap / confluence /
       theme / dollar(EUR) behaviour space.
    2. **asset_sign** — every sign-probe asset × {usd_up, usd_down} at full
       strength × {full_edge_up, full_edge_down}, to pin the per-asset
       ``_ASSET_USD_SIGN`` mapping on its own.
    """
    cases: list[FuserCase] = []

    for regime_tag, bull, bear in _SCENARIO_REGIMES:
        for ev_tag, lean, theme, usd, strength in _EVIDENCE_COMBOS:
            cases.append(
                FuserCase(
                    case_id=f"behaviour/{regime_tag}/{ev_tag}",
                    asset="EUR_USD",
                    bull=bull,
                    bear=bear,
                    confluence_lean=lean,
                    theme_present=theme,
                    dollar_consensus=usd,
                    dollar_strength=strength,
                )
            )

    for regime_tag, bull, bear in (
        ("full_edge_up", 0.60, 0.40),
        ("full_edge_down", 0.40, 0.60),
    ):
        for consensus in ("usd_up", "usd_down"):
            for asset in _SIGN_PROBE_ASSETS:
                cases.append(
                    FuserCase(
                        case_id=f"asset_sign/{regime_tag}/{consensus}/{asset}",
                        asset=asset,
                        bull=bull,
                        bear=bear,
                        confluence_lean=None,
                        theme_present=False,
                        dollar_consensus=consensus,
                        dollar_strength=1.0,
                    )
                )

    return tuple(cases)


def _r(value: float) -> float:
    """Canonical float rounding for the snapshot (see ``_FLOAT_NDIGITS``)."""
    return round(float(value), _FLOAT_NDIGITS)


def serialize_grounding(g: ConvictionGrounding) -> dict[str, Any]:
    """Canonical, JSON-stable serialization of a fused grounding."""
    return {
        "direction": g.direction,
        "conviction_pct": _r(g.conviction_pct),
        "base_conviction_pct": _r(g.base_conviction_pct),
        "agreement_factor": _r(g.agreement_factor),
        "soft_zone_scale": _r(g.soft_zone_scale),
        "agreeing": list(g.agreeing),
        "disagreeing": list(g.disagreeing),
        "rationale_fr": g.rationale_fr,
    }


def compute_grounding(case: FuserCase, fuse_fn: Any = fuse_conviction) -> ConvictionGrounding:
    """Run ``fuse_fn`` for a case with the C-1 kwargs (no ``votes`` — the flag-OFF
    surface). ``fuse_fn`` defaults to the live fuser; C-2 passes its extended fuser
    (``votes`` defaulting to ``()``), which must reproduce the same output."""
    result: ConvictionGrounding = fuse_fn(
        asset=case.asset,
        scenarios=_scn(case.bull, case.bear),
        confluence_lean=cast("ConfluenceLean | None", case.confluence_lean),
        theme_present=case.theme_present,
        dollar_consensus=cast("DollarConsensus | None", case.dollar_consensus),
        dollar_strength=case.dollar_strength,
    )
    return result


def _build_snapshot() -> dict[str, Any]:
    """Compute the full golden snapshot from the live fuser."""
    cases = {
        case.case_id: serialize_grounding(compute_grounding(case)) for case in build_input_matrix()
    }
    return {
        "_meta": {
            "contract": (
                "S06 Chantier C / C-1 golden-card diff harness. Frozen "
                "fuse_conviction(ConvictionGrounding) over build_input_matrix(). "
                "Slice C-2 must keep this byte-identical with the votes flag OFF "
                "(assert_fuser_golden). Regenerate ONLY via ICHOR_REGEN_GOLDEN=1 "
                "after an INTENDED fusion change."
            ),
            "case_count": len(cases),
            "float_ndigits": _FLOAT_NDIGITS,
        },
        "cases": cases,
    }


def load_golden() -> dict[str, Any]:
    """Load the committed golden snapshot (fail-loud if missing)."""
    assert _GOLDEN_PATH.is_file(), (
        f"golden snapshot missing: {_GOLDEN_PATH}\n"
        f"Generate it with ICHOR_REGEN_GOLDEN=1 pytest {Path(__file__).name}"
    )
    data: dict[str, Any] = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))
    return data


def regenerate_golden() -> dict[str, Any]:
    """(Re)write the committed golden snapshot from the live fuser."""
    snapshot = _build_snapshot()
    _GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    _GOLDEN_PATH.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return snapshot


# --------------------------------------------------------------------------- #
# Reusable equivalence guards (CONSUMED BY SLICE C-2)                          #
# --------------------------------------------------------------------------- #


def assert_fuser_golden(fuse_fn: Any = fuse_conviction) -> None:
    """Assert ``fuse_fn`` reproduces the committed golden byte-for-byte over the
    whole matrix. C-2 calls this with its extended fuser to prove the flag-OFF
    path is byte-identical to today's behaviour.

    LIMITATION (by design): this only exercises the flag-OFF path — ``compute_grounding``
    never passes ``votes=``, so it relies on C-2's ``votes=()`` default. It proves the
    default path is unchanged; it does NOT cover the flag-ON votes wiring, which C-2
    MUST guard with its own dedicated tests."""
    golden = load_golden()
    golden_cases: dict[str, Any] = golden["cases"]
    for case in build_input_matrix():
        got = serialize_grounding(compute_grounding(case, fuse_fn))
        expected = golden_cases.get(case.case_id)
        assert expected is not None, f"golden has no case {case.case_id!r} — regenerate"
        assert got == expected, (
            f"fuser golden drift @ {case.case_id}\n  got     : {got}\n  expected: {expected}"
        )


def assert_derive_golden(derive_fn: Any = _derive_direction_and_conviction) -> None:
    """Assert the builder seam ``_derive_direction_and_conviction`` stays a faithful
    projection ``(direction, conviction_pct, rationale_fr)`` of the golden grounding.
    C-2 (which threads ``votes`` through this wrapper) re-runs it to prove the seam
    wiring introduced no drift."""
    golden = load_golden()
    golden_cases: dict[str, Any] = golden["cases"]
    for case in build_input_matrix():
        direction, conviction, rationale = derive_fn(
            _scn(case.bull, case.bear),
            asset=case.asset,
            confluence_lean=case.confluence_lean,
            theme_present=case.theme_present,
            dollar_consensus=case.dollar_consensus,
            dollar_strength=case.dollar_strength,
        )
        expected = golden_cases.get(case.case_id)
        assert expected is not None, f"golden has no case {case.case_id!r} — regenerate"
        assert direction == expected["direction"], f"derive direction drift @ {case.case_id}"
        assert _r(conviction) == expected["conviction_pct"], (
            f"derive conviction drift @ {case.case_id}: "
            f"{_r(conviction)} != {expected['conviction_pct']}"
        )
        assert rationale == expected["rationale_fr"], f"derive rationale drift @ {case.case_id}"


# --------------------------------------------------------------------------- #
# Tests                                                                        #
# --------------------------------------------------------------------------- #


def test_regenerate_golden_snapshot() -> None:
    """Opt-in golden (re)generation. No-op unless ``ICHOR_REGEN_GOLDEN=1`` so CI
    can never silently rewrite the frozen reference."""
    if os.environ.get("ICHOR_REGEN_GOLDEN") != "1":
        pytest.skip("set ICHOR_REGEN_GOLDEN=1 to (re)write the golden snapshot")
    snapshot = regenerate_golden()
    assert snapshot["cases"], "regenerated an empty snapshot"


def test_matrix_is_deterministic_and_unique() -> None:
    """The matrix must be stable across calls and free of duplicate case ids
    (a dup would silently overwrite a snapshot entry)."""
    first = build_input_matrix()
    second = build_input_matrix()
    assert first == second, "build_input_matrix is non-deterministic"
    ids = [c.case_id for c in first]
    assert len(ids) == len(set(ids)), "duplicate case_id in the matrix"
    # 11 regimes × 13 combos + 2 regimes × 2 consensus × 9 assets = 143 + 36 = 179.
    assert len(ids) == 179, f"unexpected matrix size {len(ids)} (expected 179)"


def test_matrix_covers_every_branch() -> None:
    """Sanity: the matrix actually exercises each fusion branch, so the golden is
    meaningful (not a trivial all-neutral snapshot)."""
    groundings = [compute_grounding(c) for c in build_input_matrix()]
    directions = {g.direction for g in groundings}
    assert directions == {"up", "down", "neutral"}, f"missing a direction: {directions}"
    assert any(g.conviction_pct == 0.0 and g.direction == "neutral" for g in groundings)
    assert any(g.conviction_pct == CONVICTION_CEIL_PCT for g in groundings), "cap-95 never hit"
    assert any(0.0 < g.soft_zone_scale < 1.0 for g in groundings), "soft-zone never exercised"
    assert any(g.agreeing for g in groundings), "no agreeing layer ever recorded"
    assert any(g.disagreeing for g in groundings), "no disagreeing layer ever recorded"


def test_fuser_reproduces_golden() -> None:
    """THE regression guard: the live fuser still matches the frozen snapshot."""
    assert_fuser_golden()


def test_derive_seam_matches_golden() -> None:
    """The builder seam stays a faithful projection of the golden grounding."""
    assert_derive_golden()


def test_no_trade_tokens_across_matrix() -> None:
    """ADR-017: no ``rationale_fr`` in the whole matrix emits a trade-signal token."""
    for case in build_input_matrix():
        rationale = compute_grounding(case).rationale_fr
        assert _FORBIDDEN_RE.search(rationale) is None, f"trade token leaked @ {case.case_id}"


def test_all_convictions_within_cap95() -> None:
    """ADR-022: every fused conviction in the matrix is within ``[0, 95]``."""
    for case in build_input_matrix():
        conviction = compute_grounding(case).conviction_pct
        assert 0.0 <= conviction <= CONVICTION_CEIL_PCT, (
            f"conviction {conviction} out of [0, 95] @ {case.case_id}"
        )


def test_golden_meta_matches_matrix() -> None:
    """The committed snapshot covers exactly the current matrix (no stale / missing
    cases) — a structural drift guard distinct from the per-case value guard."""
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
