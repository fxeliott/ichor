"""economic_event_surprise -- classify a published actual vs its forecast range.

Pure compute, no I/O. Inputs are text values as stored by the ForexFactory
collector (and future r142 reconciler), outputs a `SurpriseClassification`
dataclass naming the state (`in_range` / `above_range` / `below_range` /
`exact_consensus` / `unavailable`) plus the standardized magnitudes.

The institutional read codified here :

A published `actual` value that lies WITHIN the analyst forecast range
(min..max envelope) is NOT a repricing catalyst -- even if it deviates from
the consensus point, it was already priced in by the dispersion of analyst
expectations. A published `actual` that lies OUTSIDE the range IS a repricing
catalyst -- the market's prior was wrong on both the center AND the width
of its distribution.

The world-class trader transcript audited r141 captured this verbatim :

    "si on sort a 3 % alors oui on est au-dessus des attentes mais on va dire
     ca restait dans le range des attentes ca va pas non plus surprendre le
     marche. Alors que si on sort a 3.2 la ca vient vraiment changer la donne."

ADR-017 compliance : this module produces probability framing + surprise
labels only -- never BUY/SELL/long/short imperatives. `magnitude_pct` and
`range_breach` are descriptive scalars, polarity-neutral. State labels are
descriptive (`above_range` describes the actual vs envelope geometry, not
a directional bias).

Doctrine #11 calibrated honesty : `state = "unavailable"` is the only honest
output when `actual` is missing or both envelope bounds are missing. Never
fabricate a fallback classification from `forecast` alone -- the whole point
of the range read is that the point estimate is insufficient.

ADR refs : ADR-099 Impl(r141) -- Mission centrale Axis-5 deepen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

__all__ = [
    "SurpriseClassification",
    "SurpriseState",
    "classify_surprise",
    "parse_economic_value",
]

SurpriseState = Literal[
    "unavailable",
    "in_range",
    "above_range",
    "below_range",
    "exact_consensus",
]


@dataclass(frozen=True)
class SurpriseClassification:
    """Output of `classify_surprise` -- descriptive only (ADR-017).

    Attributes :
        state            : one of {unavailable, in_range, above_range,
                           below_range, exact_consensus}.
        actual           : parsed float of the published value, or None if
                           parse failed.
        consensus        : parsed float of the forecast consensus point
                           (FF `forecast` column), or None.
        forecast_min     : parsed float of the lower envelope, or None.
        forecast_max     : parsed float of the upper envelope, or None.
        magnitude_pct    : actual-vs-consensus deviation as percentage of
                           |consensus|, or None when consensus is missing
                           or zero. Polarity-neutral (signed).
        range_breach     : absolute distance to the nearest envelope bound
                           (forecast_min or forecast_max) in raw units (NOT
                           normalized) when state in {above_range,
                           below_range} ; otherwise None.
        parse_failures   : frozen set of field names that failed to parse
                           to float. Empty means all non-empty text values
                           parsed cleanly. Empty/None inputs do NOT count
                           as failures -- only malformed non-empty strings.
    """

    state: SurpriseState
    actual: float | None
    consensus: float | None
    forecast_min: float | None
    forecast_max: float | None
    magnitude_pct: float | None
    range_breach: float | None
    parse_failures: frozenset[str]


# Strips the common unit suffixes published by FF / Trading Economics /
# Investing.com. Order matters in the regex -- `%` is stripped at the end
# (informational suffix that doesn't change magnitude).
#
# The magnitude group accepts EITHER a plain digit run (`[0-9]+`) OR a
# strict American-thousands form (`[0-9]{1,3}(?:,[0-9]{3})+`). This rejects
# European decimal-comma (`"1,5"`, `"1,50"`) which would otherwise silently
# misparse via naive `,` strip -- code-reviewer r141 S1 fix. The optional
# decimal `(?:\.[0-9]+)?` attaches to either branch.
_UNIT_SUFFIX_PATTERN = re.compile(
    r"""
    ^\s*
    ([+-]?)                                                 # 1: optional sign
    \$?                                                      # optional dollar prefix
    (
        [0-9]+(?:\.[0-9]+)?                                  # plain digit run
        |
        [0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?                # American thousands
    )                                                        # 2: magnitude
    \s*
    (T|B|M|K|t|b|m|k)?                                       # 3: optional scale unit
    \s*
    %?                                                       # optional percent suffix
    \s*$
    """,
    re.VERBOSE,
)
_SCALE_FACTOR: dict[str, float] = {
    "T": 1e12,
    "t": 1e12,
    "B": 1e9,
    "b": 1e9,
    "M": 1e6,
    "m": 1e6,
    "K": 1e3,
    "k": 1e3,
}


def parse_economic_value(raw: str | None) -> float | None:
    """Parse a ForexFactory-style text value to float, or None on failure.

    Examples :
      "3.2%"   -> 3.2
      "$50K"   -> 50000.0
      "1.5M"   -> 1_500_000.0
      "+5K"    -> 5000.0
      "-2.5"   -> -2.5
      "1,500"  -> 1500.0      (American thousands separator)
      ""       -> None
      "TBA"    -> None
      None     -> None

    Note on commas : ForexFactory uses American formatting where comma is
    a thousands separator ("1,500" = 1500). European decimal-comma formats
    ("1,5") are NOT supported on this table -- those collectors (e.g.
    bundesbank, ecb) own their own parsers keyed to source.

    Never raises -- malformed inputs return None so the classifier can
    compose parse failures into the `parse_failures` set instead of
    bubbling exceptions into the prompt context.
    """
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    m = _UNIT_SUFFIX_PATTERN.match(s)
    if m is None:
        return None
    sign_raw, mag_raw, scale = m.group(1), m.group(2), m.group(3)
    # Strip American thousands separators before float conversion.
    mag = mag_raw.replace(",", "")
    # Hard guard against accidental double-decimal (regex permits one).
    if mag.count(".") > 1:
        return None
    try:
        value = float(mag)
    except ValueError:
        return None
    if sign_raw == "-":
        value = -value
    if scale:
        value *= _SCALE_FACTOR[scale]
    return value


def classify_surprise(
    *,
    actual: str | None,
    consensus: str | None,
    forecast_min: str | None,
    forecast_max: str | None,
) -> SurpriseClassification:
    """Classify a published actual value vs its forecast envelope.

    Args (all text -- caller provides ForexFactory-shaped strings) :
        actual         : published value once event has fired.
        consensus      : analyst consensus point (FF `forecast` column).
        forecast_min   : lower envelope of analyst range.
        forecast_max   : upper envelope of analyst range.

    Returns a `SurpriseClassification` ; never raises.

    Behaviour (precedence) :
      1. If `actual` is missing or unparseable -> state=`unavailable`.
      2. If BOTH `forecast_min` AND `forecast_max` are missing or
         unparseable -> state=`unavailable` (can't classify vs range).
      3. If `forecast_min > forecast_max` (provider bug) -> swap silently
         and proceed.
      4. If `actual == consensus` exactly (and consensus parsed) ->
         state=`exact_consensus` (special case -- the actual landed
         exactly on the consensus point, in/above/below not meaningful).
      5. If `forecast_min <= actual <= forecast_max` -> state=`in_range`.
      6. If `actual > forecast_max` -> state=`above_range`,
         `range_breach = actual - forecast_max`.
      7. If `actual < forecast_min` -> state=`below_range`,
         `range_breach = forecast_min - actual`.

    Single-sided envelope : if only `forecast_min` OR only `forecast_max`
    is published (rare, but possible from providers like Trading Economics
    when the range is asymmetric), the missing bound is treated as
    +/-infinity for the geometry check.

    `magnitude_pct` is computed whenever both `actual` and `consensus`
    parse and consensus is non-zero ; otherwise None. It is signed
    (negative when actual < consensus).

    Polarity convention : the classifier does NOT invert sign for
    UNRATE-style (lower-is-better) indicators. Polarity-correction is a
    downstream concern of `<MacroSurprisePanel>` (r136) which holds the
    per-indicator semantic catalog.
    """
    parse_failures: set[str] = set()
    actual_f = parse_economic_value(actual)
    if actual_f is None and actual is not None and actual.strip():
        parse_failures.add("actual")
    consensus_f = parse_economic_value(consensus)
    if consensus_f is None and consensus is not None and consensus.strip():
        parse_failures.add("consensus")
    fmin_f = parse_economic_value(forecast_min)
    if fmin_f is None and forecast_min is not None and forecast_min.strip():
        parse_failures.add("forecast_min")
    fmax_f = parse_economic_value(forecast_max)
    if fmax_f is None and forecast_max is not None and forecast_max.strip():
        parse_failures.add("forecast_max")

    # magnitude_pct computed whenever possible, independent of state -- the
    # consumer may still want to know the deviation even if the range
    # classification couldn't fire. Epsilon guard (code-reviewer r141 S5)
    # parity with W99 `_no_nan` discipline -- rejects sub-normal consensus
    # values that would overflow the division.
    magnitude_pct: float | None = None
    if actual_f is not None and consensus_f is not None and abs(consensus_f) > 1e-9:
        magnitude_pct = (actual_f - consensus_f) / abs(consensus_f) * 100.0

    if actual_f is None:
        return SurpriseClassification(
            state="unavailable",
            actual=actual_f,
            consensus=consensus_f,
            forecast_min=fmin_f,
            forecast_max=fmax_f,
            magnitude_pct=magnitude_pct,
            range_breach=None,
            parse_failures=frozenset(parse_failures),
        )
    if fmin_f is None and fmax_f is None:
        return SurpriseClassification(
            state="unavailable",
            actual=actual_f,
            consensus=consensus_f,
            forecast_min=fmin_f,
            forecast_max=fmax_f,
            magnitude_pct=magnitude_pct,
            range_breach=None,
            parse_failures=frozenset(parse_failures),
        )

    # Tolerate provider bug min > max -- swap silently AND surface via
    # `parse_failures` sentinel so downstream r142 reconciler + UI consumers
    # can observe provider-bug rate (concordant 2/2 review : trader Y-2 +
    # code-reviewer N3 -- doctrine #11 argues for surfacing, not silencing).
    if fmin_f is not None and fmax_f is not None and fmin_f > fmax_f:
        fmin_f, fmax_f = fmax_f, fmin_f
        parse_failures.add("forecast_range_inverted")

    # Exact-consensus special case (only when consensus AND actual parse).
    if consensus_f is not None and actual_f == consensus_f:
        return SurpriseClassification(
            state="exact_consensus",
            actual=actual_f,
            consensus=consensus_f,
            forecast_min=fmin_f,
            forecast_max=fmax_f,
            magnitude_pct=magnitude_pct,
            range_breach=None,
            parse_failures=frozenset(parse_failures),
        )

    above = fmax_f is not None and actual_f > fmax_f
    below = fmin_f is not None and actual_f < fmin_f

    if above:
        return SurpriseClassification(
            state="above_range",
            actual=actual_f,
            consensus=consensus_f,
            forecast_min=fmin_f,
            forecast_max=fmax_f,
            magnitude_pct=magnitude_pct,
            range_breach=actual_f - fmax_f,
            parse_failures=frozenset(parse_failures),
        )
    if below:
        return SurpriseClassification(
            state="below_range",
            actual=actual_f,
            consensus=consensus_f,
            forecast_min=fmin_f,
            forecast_max=fmax_f,
            magnitude_pct=magnitude_pct,
            range_breach=fmin_f - actual_f,
            parse_failures=frozenset(parse_failures),
        )
    return SurpriseClassification(
        state="in_range",
        actual=actual_f,
        consensus=consensus_f,
        forecast_min=fmin_f,
        forecast_max=fmax_f,
        magnitude_pct=magnitude_pct,
        range_breach=None,
        parse_failures=frozenset(parse_failures),
    )
