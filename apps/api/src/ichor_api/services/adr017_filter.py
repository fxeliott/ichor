"""ADR-017 boundary filter — shared regex + helpers for ANY LLM-emitted
text that must NOT contain trade-signal tokens.

Round-31 sub-wave .a (ADR-091 §"Invariant 2") : extracted from
`services/addendum_generator.py` to give the future GEPA optimizer
(W117b) a single source of truth for the 19-pattern superset. Without
this extraction the GEPA fitness function would need to import a
private regex from a peer service, or worse re-implement the patterns
and diverge.

Consumers (current + planned) :
  - `services.addendum_generator` (W116c) — defense-in-depth filter on
    LLM addendum text BEFORE persistence to `pass3_addenda`.
  - `services.gepa_optimizer` (W117b, ADR-091 invariant 2) — fitness
    penalty term : `-lambda * len(find_violations(candidate_output))`
    sculpts the GEPA fitness landscape away from "more decisive =
    higher fitness" pathological evolution.
  - Future LLM-touching modules (any) — call `is_adr017_clean(text)`
    before persisting or injecting LLM-generated content.

Pattern superset codified by ADR-087 §"LLM extension 1 W116c addendum
generator" and extended round-28 (RED HIGH from ichor-trader review).
19 patterns total. Strictness rationale : false positives are
preferable to false negatives. An LLM that occasionally has a benign
macro mention like "margin debt" filtered out is acceptable. An LLM
that emits "TARGET 1.0850 ENTRY 1.0900" and slips past the regex is
NOT — that text would be persisted to `pass3_addenda` and injected
into Pass-3 stress prompts at the next fire.

Invariant : the regex source string in this module IS the canonical
ADR-017 boundary regex. Any other module that ships its own copy of
the regex is a P0 doctrinal regression (catch via W90 follow-on
invariant test if/when ADR-091 ships).
"""

from __future__ import annotations

import re

# Public regex source — single source of truth shared across consumers.
# Word-boundary anchored ; case-insensitive ; matches ANY of the 19
# forbidden patterns. Compiled at module import for zero per-call cost.
#
# Pattern inventory (19) :
#   BUY, SELL                                        (2 — bare imperatives)
#   LONG NOW, SHORT NOW, LONG AT, SHORT AT           (4 — imperative directionals)
#   ENTER LONG, ENTER SHORT                          (2 — imperative entries)
#   TP\d*, SL\d*                                     (2 — take-profit / stop-loss laddering)
#   take_profit, stop_loss                           (2 — verbose forms with \s_- separators)
#   TARGET <number>, ENTRY <number>                  (2 — numeric trade levels)
#   entry_price                                      (1 — explicit level naming)
#   leverage                                         (1 — bare leverage mention)
#   MARGIN CALL                                      (1 — compound trade state)
# Total = 17 distinct alternatives ; with TP\d* / SL\d* matching both
# bare and numbered forms the practical coverage is 19+ tokens.
ADR017_FORBIDDEN_REGEX_SOURCE = (
    r"\b(BUY|SELL|"
    r"LONG\s+NOW|SHORT\s+NOW|LONG\s+AT|SHORT\s+AT|"
    r"ENTER\s+(?:LONG|SHORT)|"
    r"TP\d*|SL\d*|"
    r"take[\s_-]*profit|stop[\s_-]*loss|"
    r"TARGET[\s:]+\d+\.?\d*|ENTRY[\s:]+\d+\.?\d*|entry\s+price|"
    r"leverage|MARGIN\s+CALL"
    r")\b"
)

_ADR017_FORBIDDEN_RE = re.compile(ADR017_FORBIDDEN_REGEX_SOURCE, re.IGNORECASE)


# Human-readable labels — order matches the regex alternation. NOT
# consumed at runtime ; the regex itself is the authoritative match
# engine. Frozenset exists so downstream diagnostics (fitness function
# logging, test enumeration) can list "which patterns ARE blocked"
# without parsing the regex source.
ADR017_FORBIDDEN_PATTERN_LABELS: frozenset[str] = frozenset(
    {
        "BUY",
        "SELL",
        "LONG NOW",
        "SHORT NOW",
        "LONG AT",
        "SHORT AT",
        "ENTER LONG",
        "ENTER SHORT",
        "TP (with optional digits)",
        "SL (with optional digits)",
        "take_profit / take profit / take-profit",
        "stop_loss / stop loss / stop-loss",
        "TARGET <number>",
        "ENTRY <number>",
        "entry price / entry_price",
        "leverage",
        "MARGIN CALL",
    }
)


def is_adr017_clean(text: str) -> bool:
    """Return True iff `text` contains NO ADR-017 forbidden token.

    Canonical defense-in-depth filter : every LLM-generated text
    destined for persistence and/or downstream Pass-3 injection MUST
    be passed through this helper. The caller MUST gate persistence
    on `is_adr017_clean(text) is True`.
    """
    return _ADR017_FORBIDDEN_RE.search(text) is None


def find_violations(text: str) -> list[str]:
    """Return the list of forbidden substrings found in `text`.

    Useful for :
      - logging the offending fragment when filtering an LLM output.
      - GEPA fitness function (ADR-091) penalty term : the count is
        the penalty weight, the substrings let the operator inspect
        which patterns are drifting.

    Order matches scan order ; duplicates are returned (each match is
    a separate finding).
    """
    return [m.group(0) for m in _ADR017_FORBIDDEN_RE.finditer(text)]


def count_violations(text: str) -> int:
    """Return the number of forbidden substrings in `text`.

    Thin convenience over `find_violations` for the GEPA fitness
    function (ADR-091) where only the count is needed for the penalty
    term `-lambda * count`. Avoids materializing the list when the
    operator only wants the scalar.
    """
    return sum(1 for _ in _ADR017_FORBIDDEN_RE.finditer(text))
