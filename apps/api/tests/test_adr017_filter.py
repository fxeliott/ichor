"""Unit tests for the shared ADR-017 filter module
(`services.adr017_filter`).

Round-31 sub-wave .a (ADR-091 §"Invariant 2") : the 19-pattern superset
is extracted out of `addendum_generator.py` so it has a single source
of truth shared between the W116c addendum generator and the future
W117b GEPA fitness penalty.

Test surface :

1. `is_adr017_clean` matches the historical addendum-generator
   contract (every test case pinned in `test_addendum_generator.py`
   round-26/28 must also pass against the extracted helper).
2. `find_violations` returns the offending substrings with order
   preserved and duplicates kept.
3. `count_violations` agrees with `len(find_violations(...))` on
   every fixture (scalar convenience).
4. `ADR017_FORBIDDEN_PATTERN_LABELS` covers all 17 distinct pattern
   labels (the regex has 17 alternatives ; `TP\\d*` / `SL\\d*` are 1
   alternative each but match both bare and numbered forms).
5. Word-boundary behaviour is preserved : `buyer` / `seller` / `tps`
   do NOT match.
6. Defense-in-depth fragments from `addendum_generator.py` legacy
   tests are re-pinned here so a future refactor that breaks the
   extracted helper fails this file (not the consumer file).
"""

from __future__ import annotations

import pytest
from ichor_api.services.adr017_filter import (
    _ADR017_FORBIDDEN_RE,
    ADR017_FORBIDDEN_PATTERN_LABELS,
    ADR017_FORBIDDEN_REGEX_SOURCE,
    count_violations,
    find_violations,
    is_adr017_clean,
)

# ──────────────────────────── is_adr017_clean ──────────────────────────


def test_clean_macro_addendum_passes() -> None:
    """Probabilistic / directional language is fine."""
    text = (
        "Pocket EUR_USD/usd_complacency anti-skill : steelman should "
        "consider Fed put expectations re-pricing the DXY trend."
    )
    assert is_adr017_clean(text)


def test_clean_long_short_inside_compound_words_passes() -> None:
    """Word-boundary anchored — `buyer` / `seller` / `longstanding` /
    `shortfall` MUST NOT match."""
    for text in (
        "Discretionary buyers stepped in.",
        "Seller flow continues at quarter-end.",
        "A longstanding correlation between DXY and EUR.",
        "Liquidity shortfall in CHF cross.",
    ):
        assert is_adr017_clean(text), f"Should pass : {text!r}"


def test_clean_macro_terms_pass() -> None:
    """Legitimate macro language with MARGIN, TARGET-adjacent context
    that does NOT match the strict patterns must pass."""
    for text in (
        "NYSE margin debt at 12-month high.",
        "FX margin requirements tightening.",
        "Reaching target levels of inflation.",
        "Inflation target of 2% remains the anchor.",
    ):
        assert is_adr017_clean(text), f"Should pass : {text!r}"


@pytest.mark.parametrize(
    "forbidden_text",
    [
        # Bare imperatives
        "Consider BUY pressure on EUR.",
        "Cards trend toward SELL signals.",
        # Lowercase variants (regex is IGNORECASE)
        "buy now reasonable.",
        "Sell pressure builds.",
        # Imperative directionals
        "Pocket suggests LONG NOW on EUR.",
        "Reframe : SHORT NOW the dollar.",
        "Pocket logic : long at 1.18.",
        "Counter-claim short at 1.10 plausible.",
        # Enter compounds
        "Enter long if DXY breaks.",
        "Enter short on the rally.",
        # Take-profit / stop-loss
        "TP near 1.20 likely.",
        "SL at 1.15 prudent.",
        "Steelman: take_profit ladder is the right reframe.",
        "Steelman: take profit ladder is the right reframe.",
        "Steelman: take-profit ladder is the right reframe.",
        "Steelman: stop loss tight is the right reframe.",
        "Steelman: stop_loss tight is the right reframe.",
        # Numeric levels
        "TARGET 1.0850 confluent.",
        "ENTRY 1.0900 zone.",
        "Target : 1.0850 reachable.",
        "ENTRY: 1.0900 tight.",
        "TARGET 1.0 region.",
        # Entry price (legacy)
        "Steelman: entry price 1.15 is the right reframe.",
        # Leverage / margin call
        "Steelman: high leverage exposure is the right reframe.",
        "MARGIN CALL risk elevated.",
        # TP / SL with numeric suffix (laddering)
        "TP1 1.0900, TP2 1.0950 ladder.",
        "SL1 1.0800 trail.",
    ],
)
def test_forbidden_tokens_caught(forbidden_text: str) -> None:
    """Each canonical forbidden pattern MUST be rejected by
    `is_adr017_clean`. Mirrors the round-26 + round-28 fixtures pinned
    in `test_addendum_generator.py`."""
    assert not is_adr017_clean(forbidden_text), (
        f"Should reject : {forbidden_text!r} — the extracted "
        "regex superset is the single source of truth for ADR-017 "
        "boundary enforcement (ADR-091 §Invariant 2)."
    )


# ──────────────────────────── find_violations ──────────────────────────


def test_find_violations_empty_on_clean_text() -> None:
    assert find_violations("Macro-only narrative with no trade tokens.") == []


def test_find_violations_returns_substrings() -> None:
    """The function returns the actual matched substrings (not labels)."""
    matches = find_violations("Consider BUY pressure and SELL flow.")
    assert "BUY" in matches
    assert "SELL" in matches
    assert len(matches) == 2


def test_find_violations_preserves_duplicates() -> None:
    """Each match is a separate finding — duplicates kept for fitness
    function weighting (ADR-091)."""
    matches = find_violations("BUY BUY SELL")
    assert len(matches) == 3
    assert matches.count("BUY") == 2
    assert matches.count("SELL") == 1


def test_find_violations_preserves_scan_order() -> None:
    """First match comes first ; downstream logging shows the LLM
    sequence of forbidden emissions."""
    matches = find_violations("First SELL then BUY then TP1.")
    assert matches == ["SELL", "BUY", "TP1"]


# ──────────────────────────── count_violations ──────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "Macro-only.",
        "BUY",
        "BUY SELL",
        "TARGET 1.0 region, BUY now, SL at 1.05.",
    ],
)
def test_count_matches_find(text: str) -> None:
    """Scalar convenience MUST agree with `len(find_violations(...))`
    on every fixture (no off-by-one, no overlap-double-counting)."""
    assert count_violations(text) == len(find_violations(text))


def test_count_zero_on_clean() -> None:
    assert count_violations("DXY mean-reversion plausible.") == 0


def test_count_positive_on_violation() -> None:
    assert count_violations("Consider BUY pressure.") == 1


# ──────────────────────────── pattern labels ──────────────────────────


def test_pattern_labels_present_and_nonempty() -> None:
    """The human-readable label set is consumed by diagnostics and
    fitness-function logging (ADR-091). It MUST stay non-empty and
    cover the 17 distinct pattern labels."""
    assert isinstance(ADR017_FORBIDDEN_PATTERN_LABELS, frozenset)
    assert len(ADR017_FORBIDDEN_PATTERN_LABELS) == 17


def test_pattern_labels_include_core_imperatives() -> None:
    """The two bare imperatives MUST be in the label set even though
    they're trivially obvious — the label set is the documentation
    surface used by diagnostics."""
    assert "BUY" in ADR017_FORBIDDEN_PATTERN_LABELS
    assert "SELL" in ADR017_FORBIDDEN_PATTERN_LABELS


def test_pattern_labels_include_round28_additions() -> None:
    """Round-28 RED HIGH extensions MUST be labelled — these are the
    patterns the pre-round-28 regex missed."""
    for needle in ("LONG NOW", "SHORT NOW", "MARGIN CALL"):
        assert any(needle in lbl for lbl in ADR017_FORBIDDEN_PATTERN_LABELS), (
            f"Pattern label set is missing a label containing {needle!r}."
        )


# ──────────────────────────── regex source ──────────────────────────


def test_regex_source_word_boundary_anchored() -> None:
    """The regex MUST start with `\\b(` and end with `)\\b` so token
    inclusion checks remain strict (legitimate macro words containing
    `buy`/`sell` substrings stay clean)."""
    assert ADR017_FORBIDDEN_REGEX_SOURCE.startswith(r"\b(")
    assert ADR017_FORBIDDEN_REGEX_SOURCE.endswith(r")\b")


def test_compiled_regex_is_case_insensitive() -> None:
    """Defense-in-depth contract : an LLM that emits `buy` lower-case
    instead of `BUY` MUST still be caught."""
    import re

    assert _ADR017_FORBIDDEN_RE.flags & re.IGNORECASE == re.IGNORECASE


# ────────── Cross-module parity with addendum_generator re-export ──────────


def test_addendum_generator_delegates_to_canonical_helper() -> None:
    """Round-31 sub-wave .a backward-compat : the legacy
    `addendum_passes_adr017_filter` on the consumer module MUST
    delegate to `is_adr017_clean` — both must return the same answer
    on every fixture."""
    from ichor_api.services.addendum_generator import addendum_passes_adr017_filter

    for text in (
        "Clean macro narrative.",
        "Consider BUY pressure.",
        "TARGET 1.0850 explicit.",
        "MARGIN CALL risk.",
        "NYSE margin debt at high.",
    ):
        assert addendum_passes_adr017_filter(text) == is_adr017_clean(text), (
            f"Delegation broke for fixture : {text!r} — the consumer "
            "module must call into the extracted helper."
        )


def test_addendum_generator_reexports_compiled_regex() -> None:
    """Backward-compat : external code that imports
    `_ADR017_FORBIDDEN_RE` from the consumer module must still see
    the SAME compiled regex instance as the extracted module exports
    (no accidental fork)."""
    from ichor_api.services.addendum_generator import (
        _ADR017_FORBIDDEN_RE as consumer_regex,
    )

    assert consumer_regex is _ADR017_FORBIDDEN_RE, (
        "Re-export drift : the consumer module re-bound "
        "`_ADR017_FORBIDDEN_RE` to a different object. Update the "
        "import to `from .adr017_filter import _ADR017_FORBIDDEN_RE`."
    )
