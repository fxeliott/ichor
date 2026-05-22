"""economic_event_surprise -- pure classifier unit tests.

Coverage targets (r141) :
  - `parse_economic_value` : happy formats + malformed edge cases
  - `classify_surprise` : all 5 states + edge cases (parse failures, swapped
    envelope, single-sided envelope, exact consensus, zero consensus,
    negative range, K-scaled units)

ADR-017 invariant : test names + assertions stay descriptive (state geometry,
magnitude scalars) -- no BUY/SELL/long/short vocabulary anywhere.
"""

from __future__ import annotations

import dataclasses
import math

import pytest
from ichor_api.services.economic_event_surprise import (
    classify_surprise,
    parse_economic_value,
)

# -- parse_economic_value ----------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("3.2%", 3.2),
        ("0.25%", 0.25),
        ("-2.5", -2.5),
        ("+5K", 5000.0),
        ("$50K", 50000.0),
        ("1.5M", 1_500_000.0),
        ("1.5B", 1_500_000_000.0),
        ("180K", 180_000.0),
        ("1,500", 1500.0),
        ("3", 3.0),
        ("0", 0.0),
        ("-0.5", -0.5),
    ],
)
def test_parse_value_happy_path(raw: str, expected: float) -> None:
    got = parse_economic_value(raw)
    assert got is not None
    assert math.isclose(got, expected, rel_tol=1e-9, abs_tol=1e-12)


@pytest.mark.parametrize(
    "raw",
    [None, "", "  ", "TBA", "Tentative", "n/a", "1.5.0", "abc", "$$50K"],
)
def test_parse_value_returns_none_on_garbage(raw: str | None) -> None:
    assert parse_economic_value(raw) is None


@pytest.mark.parametrize(
    "raw",
    ["1,5", "1,50", "1,5K", "12,3", "1,5%", "1.500.000"],
)
def test_parse_value_rejects_european_decimal_and_malformed_thousands(
    raw: str,
) -> None:
    """code-reviewer r141 S1 fix : the regex must REJECT European-decimal
    forms (`1,5` = 1.5 in EU convention) rather than silently misparsing
    them as American thousands (`1,5` -> 15 was the pre-fix bug). Inverse
    direction : `1.500.000` (EU thousands) also rejected (not a US format).

    Note : `"1,500.000"` IS valid US notation (1500 with trailing zeros)
    and parses to 1500.0 -- explicitly NOT in this rejection list.
    """
    assert parse_economic_value(raw) is None


# -- classify_surprise -------------------------------------------------------


def test_unavailable_when_actual_missing() -> None:
    out = classify_surprise(
        actual=None,
        consensus="3.0",
        forecast_min="2.8",
        forecast_max="3.2",
    )
    assert out.state == "unavailable"
    assert out.actual is None
    # Empty/None input does NOT register as a parse failure.
    assert "actual" not in out.parse_failures


def test_unavailable_when_actual_unparseable_records_parse_failure() -> None:
    out = classify_surprise(
        actual="TBA",
        consensus="3.0",
        forecast_min="2.8",
        forecast_max="3.2",
    )
    assert out.state == "unavailable"
    assert "actual" in out.parse_failures


def test_unavailable_when_both_envelope_bounds_missing() -> None:
    out = classify_surprise(
        actual="3.2",
        consensus="3.0",
        forecast_min=None,
        forecast_max=None,
    )
    assert out.state == "unavailable"
    # Magnitude still computed honestly even when classification can't fire.
    assert out.magnitude_pct is not None
    assert math.isclose(out.magnitude_pct, (3.2 - 3.0) / 3.0 * 100, rel_tol=1e-9)


def test_in_range_lands_inside_envelope() -> None:
    out = classify_surprise(
        actual="3.0",
        consensus="3.1",
        forecast_min="2.9",
        forecast_max="3.3",
    )
    assert out.state == "in_range"
    assert out.range_breach is None


def test_in_range_inclusive_at_forecast_min() -> None:
    """code-reviewer r141 S4 fix : pin inclusive lower bound semantics."""
    out = classify_surprise(
        actual="2.9",
        consensus="3.1",
        forecast_min="2.9",
        forecast_max="3.3",
    )
    assert out.state == "in_range"


def test_in_range_inclusive_at_forecast_max() -> None:
    """code-reviewer r141 S4 fix : pin inclusive upper bound semantics."""
    out = classify_surprise(
        actual="3.3",
        consensus="3.1",
        forecast_min="2.9",
        forecast_max="3.3",
    )
    assert out.state == "in_range"


def test_above_range_records_breach_distance() -> None:
    out = classify_surprise(
        actual="3.4",
        consensus="3.1",
        forecast_min="2.9",
        forecast_max="3.3",
    )
    assert out.state == "above_range"
    assert out.range_breach is not None
    assert math.isclose(out.range_breach, 0.1, rel_tol=1e-9)


def test_below_range_records_breach_distance() -> None:
    out = classify_surprise(
        actual="2.5",
        consensus="3.1",
        forecast_min="2.9",
        forecast_max="3.3",
    )
    assert out.state == "below_range"
    assert out.range_breach is not None
    assert math.isclose(out.range_breach, 0.4, rel_tol=1e-9)


def test_exact_consensus_takes_precedence_over_in_range() -> None:
    out = classify_surprise(
        actual="3.0",
        consensus="3.0",
        forecast_min="2.9",
        forecast_max="3.1",
    )
    assert out.state == "exact_consensus"
    assert out.magnitude_pct == 0.0


def test_swapped_min_max_when_consensus_match_precedes_does_not_raise() -> None:
    """Provider bug min > max ; exact_consensus precedence wins so the swap
    codepath isn't reached in this case. Pin that we don't raise.

    code-reviewer r141 S3 fix : renamed from `_recovered_silently` (the
    previous title was misleading -- the swap codepath was never actually
    exercised here because exact_consensus precedence wins first).
    """
    out = classify_surprise(
        actual="3.0",
        consensus="3.0",
        forecast_min="3.3",
        forecast_max="2.9",
    )
    assert out.state == "exact_consensus"


def test_swapped_min_max_with_actual_in_recovered_range_surfaces_sentinel() -> None:
    """Provider bug : min > max. Classifier must swap silently AND surface
    a `forecast_range_inverted` sentinel in `parse_failures` so downstream
    r142 reconciler + UI consumers can observe provider-bug rate.

    Concordant 2/2 review (trader Y-2 + code-reviewer N3) -- doctrine #11
    argues for surfacing, not silencing.
    """
    out = classify_surprise(
        actual="3.1",
        consensus="3.0",
        forecast_min="3.3",
        forecast_max="2.9",
    )
    # After swap envelope is [2.9, 3.3], actual 3.1 is inside.
    assert out.state == "in_range"
    assert "forecast_range_inverted" in out.parse_failures


def test_single_sided_envelope_above_only() -> None:
    # Only forecast_max published -- missing min treated as -infinity.
    out = classify_surprise(
        actual="3.5",
        consensus="3.0",
        forecast_min=None,
        forecast_max="3.2",
    )
    assert out.state == "above_range"


def test_single_sided_envelope_below_only() -> None:
    # Only forecast_min published -- missing max treated as +infinity.
    out = classify_surprise(
        actual="2.5",
        consensus="3.0",
        forecast_min="2.8",
        forecast_max=None,
    )
    assert out.state == "below_range"


def test_single_sided_envelope_in_range_when_actual_satisfies_known_bound() -> None:
    out = classify_surprise(
        actual="3.0",
        consensus="3.1",
        forecast_min=None,
        forecast_max="3.2",
    )
    assert out.state == "in_range"


def test_zero_consensus_does_not_divide() -> None:
    # magnitude_pct undefined when consensus == 0 (would divide by zero).
    out = classify_surprise(
        actual="0.5",
        consensus="0",
        forecast_min="-0.1",
        forecast_max="0.1",
    )
    assert out.magnitude_pct is None
    assert out.state == "above_range"


def test_negative_envelope_actual_breaches_above() -> None:
    # Both bounds negative (e.g. Eurozone deflation reading -0.5..-0.2).
    out = classify_surprise(
        actual="-0.1",
        consensus="-0.3",
        forecast_min="-0.5",
        forecast_max="-0.2",
    )
    assert out.state == "above_range"
    assert out.range_breach is not None
    assert math.isclose(out.range_breach, 0.1, rel_tol=1e-9)


def test_unit_consistency_actual_in_K_envelope_in_K() -> None:
    # NFP at 200K vs envelope 180K..220K -- units must normalize before
    # the geometry check.
    out = classify_surprise(
        actual="200K",
        consensus="195K",
        forecast_min="180K",
        forecast_max="220K",
    )
    assert out.state == "in_range"
    assert out.magnitude_pct is not None
    assert math.isclose(
        out.magnitude_pct,
        (200_000 - 195_000) / 195_000 * 100,
        rel_tol=1e-9,
    )


def test_dollar_scaled_actual_above_envelope() -> None:
    out = classify_surprise(
        actual="$1.6M",
        consensus="$1.5M",
        forecast_min="$1.45M",
        forecast_max="$1.55M",
    )
    assert out.state == "above_range"
    assert out.range_breach is not None
    assert math.isclose(out.range_breach, 50_000.0, rel_tol=1e-9)


def test_classifier_returns_frozen_dataclass() -> None:
    """code-reviewer r141 S2 fix : narrowed from `(AttributeError, Exception)`
    which would accept AssertionError. The exact type raised by attempting
    to set a field on a `frozen=True` dataclass is `FrozenInstanceError`.
    """
    out = classify_surprise(actual="3.0", consensus="3.0", forecast_min="2.9", forecast_max="3.1")
    with pytest.raises(dataclasses.FrozenInstanceError):
        out.state = "something_else"  # type: ignore[misc]


# -- Institutional read pin (trader probe r141) ------------------------------


def test_transcript_verbatim_3pct_inside_3p2_outside() -> None:
    """Pin the institutional read codified from the transcript verbatim
    (trader r141 probe) :

        "si on sort a 3 % alors oui on est au-dessus des attentes mais on
         va dire ca restait dans le range des attentes ca va pas non plus
         surprendre le marche. Alors que si on sort a 3.2 la ca vient
         vraiment changer la donne."

    Consensus 3.0, range 2.8..3.0 :
      - actual 3.0% -> in_range (no repricing)
      - actual 3.2% -> above_range (material catalyst, range_breach=0.2)
    """
    no_repricing = classify_surprise(
        actual="3.0", consensus="3.0", forecast_min="2.8", forecast_max="3.0"
    )
    assert no_repricing.state == "exact_consensus"
    # exact_consensus precedence -- 3.0 == 3.0 -- still NOT a repricing event.

    minor_deviation_in_range = classify_surprise(
        actual="3.0", consensus="2.9", forecast_min="2.8", forecast_max="3.0"
    )
    assert minor_deviation_in_range.state == "in_range"
    assert minor_deviation_in_range.range_breach is None

    material_catalyst = classify_surprise(
        actual="3.2", consensus="3.0", forecast_min="2.8", forecast_max="3.0"
    )
    assert material_catalyst.state == "above_range"
    assert material_catalyst.range_breach is not None
    assert math.isclose(material_catalyst.range_breach, 0.2, rel_tol=1e-9)
