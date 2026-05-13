"""ADR-017 boundary filter — shared regex + helpers for ANY LLM-emitted
text that must NOT contain trade-signal tokens.

Round-31 sub-wave .a extracted the 19-pattern regex superset from
`services/addendum_generator.py` to give the future GEPA optimizer
(W117b) a single source of truth.

Round-32 hardening (ichor-trader YELLOW r32) closes 4 known bypass
surfaces a GEPA-evolved candidate prompt could discover :

  1. **Unicode confusables** — `ＢＵＹ` (full-width), `ВUY` (Cyrillic
     `В` U+0412), `ΒUY` (Greek `Β` U+0392). Byte-level regex misses
     all three. Fix : NFKC normalize + manual Cyrillic/Greek
     confusable transtable before matching.

  2. **Zero-width characters** — `B​UY` (ZWSP-split), `BUY﻿`
     (BOM-tail). Word-boundary regex breaks. Fix : strip the canonical
     6-character zero-width / direction-control set before matching.

  3. **Multilingual imperatives** — `acheter EUR` (FR), `comprar EUR`
     (ES), `kaufen EUR` (DE) all carry the same directive semantics as
     `BUY` but bypass the English-only regex. Fix : extend regex with
     FR/ES/DE imperative + infinitive verb forms.

  4. **Hard-zero fitness contract** — see ADR-091 §"Invariant 2"
     amended round-32 : a candidate output containing ANY forbidden
     token MUST get fitness = -inf, NOT a soft `lambda * count`
     penalty. Soft penalty lets a candidate with 1 obfuscated signal
     emerge with net-positive fitness if its Brier skill is high
     enough. Hard-zero closes that landmine.

Consumers (current + planned) :
  - `services.addendum_generator` (W116c) — defense-in-depth filter on
    LLM addendum text BEFORE persistence to `pass3_addenda`.
  - `services.gepa_optimizer` (W117b sub-wave .c, ADR-091) — fitness
    HARD-ZERO gate. ANY violation = `-inf` fitness. The optimizer
    cannot evolve a "more decisive" prompt that smuggles trade
    signals.
  - Future LLM-touching modules — call `is_adr017_clean(text)` before
    persisting or injecting LLM-generated content.

Strictness rationale : false positives are preferable to false
negatives. An LLM that occasionally has a benign macro mention
("margin debt", "le vendeur" — FR seller noun, not the imperative)
filtered out is acceptable. An LLM that emits `ＴＡＲＧＥＴ 1.0850`
(full-width) and slips past the regex is NOT — that text would be
persisted to `pass3_addenda` and injected into Pass-3 stress prompts
at the next fire.

Invariant : the regex source + normalization pipeline in this module
IS the canonical ADR-017 boundary. Any other module that ships its
own copy is a P0 doctrinal regression (caught at CI by
`test_invariants_ichor.py::test_w116c_addendum_generator_voie_d_compliant`
and round-32 follow-on guard).
"""

from __future__ import annotations

import re
import unicodedata

# --------------------------------------------------------------------
# Normalization layer (round-32 hardening — pre-regex)
# --------------------------------------------------------------------

# Zero-width / direction-control codepoints stripped before matching.
# Each of these can split a forbidden token into two pieces that the
# byte-level regex would miss. Authoritative inventory from Unicode
# UAX #9 + UAX #31 + RFC 7564 PRECIS confusables.
_ZW_CODEPOINTS = (
    0x200B,  # ZERO WIDTH SPACE
    0x200C,  # ZERO WIDTH NON-JOINER
    0x200D,  # ZERO WIDTH JOINER
    0x200E,  # LEFT-TO-RIGHT MARK
    0x200F,  # RIGHT-TO-LEFT MARK
    0x2060,  # WORD JOINER
    0x180E,  # MONGOLIAN VOWEL SEPARATOR
    0xFEFF,  # ZERO WIDTH NO-BREAK SPACE / BOM
)
_ZW_TRANSTABLE: dict[int, None] = dict.fromkeys(_ZW_CODEPOINTS, None)


# Cyrillic + Greek confusables → Latin equivalent (uppercase + lowercase).
# Sourced from Unicode CLDR confusables.txt (subset covering the BUY /
# SELL / TARGET / ENTRY / LONG / SHORT / TP / SL letters that appear in
# the ADR-017 forbidden patterns). Extending coverage is cheap — add a
# row per attack vector encountered.
_CONFUSABLE_TRANSTABLE: dict[int, int] = {
    # Cyrillic uppercase → Latin uppercase
    ord("А"): ord("A"),  # U+0410
    ord("В"): ord("B"),  # U+0412
    ord("Е"): ord("E"),  # U+0415
    ord("К"): ord("K"),  # U+041A
    ord("М"): ord("M"),  # U+041C
    ord("Н"): ord("H"),  # U+041D
    ord("О"): ord("O"),  # U+041E
    ord("Р"): ord("P"),  # U+0420
    ord("С"): ord("C"),  # U+0421
    ord("Т"): ord("T"),  # U+0422
    ord("У"): ord("Y"),  # U+0423
    ord("Х"): ord("X"),  # U+0425
    ord("Ѕ"): ord("S"),  # U+0405 Cyrillic DZE — looks like Latin S
    ord("ѕ"): ord("s"),  # U+0455 Cyrillic dze (lowercase)
    # Cyrillic lowercase → Latin lowercase
    ord("а"): ord("a"),
    ord("е"): ord("e"),
    ord("о"): ord("o"),
    ord("р"): ord("p"),
    ord("с"): ord("c"),
    ord("у"): ord("y"),
    ord("х"): ord("x"),
    # Greek uppercase → Latin uppercase
    ord("Α"): ord("A"),  # U+0391
    ord("Β"): ord("B"),  # U+0392
    ord("Ε"): ord("E"),  # U+0395
    ord("Ζ"): ord("Z"),  # U+0396
    ord("Η"): ord("H"),  # U+0397
    ord("Ι"): ord("I"),  # U+0399
    ord("Κ"): ord("K"),  # U+039A
    ord("Μ"): ord("M"),  # U+039C
    ord("Ν"): ord("N"),  # U+039D
    ord("Ο"): ord("O"),  # U+039F
    ord("Ρ"): ord("P"),  # U+03A1
    ord("Τ"): ord("T"),  # U+03A4
    ord("Υ"): ord("Y"),  # U+03A5
    ord("Χ"): ord("X"),  # U+03A7
}


def _normalize_for_match(text: str) -> str:
    """Aggressive normalization for ADR-017 matching.

    Pipeline (order matters) :
      1. NFKC compatibility normalization — folds full-width Latin
         (`Ｂ` U+FF22 → `B` U+0042), Arabic presentation forms, etc.
      2. Zero-width / direction-control character strip — removes
         ZWSP, ZWJ, ZWNJ, LRM, RLM, WJ, MVS, BOM.
      3. Cyrillic + Greek confusable transtable — visually-identical
         non-Latin letters folded to ASCII Latin.

    NOT applied :
      - Case-folding (the regex already has IGNORECASE flag).
      - Whitespace collapsing (the regex tolerates `\\s+` where needed).
      - Quote normalization (`"` vs `“"` is not a known bypass vector).

    The function is pure (no side effects) and idempotent —
    `_normalize_for_match(_normalize_for_match(x)) == _normalize_for_match(x)`.
    """
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_ZW_TRANSTABLE)
    text = text.translate(_CONFUSABLE_TRANSTABLE)
    return text


# --------------------------------------------------------------------
# Regex superset (round-31 baseline + round-32 multilingual extension)
# --------------------------------------------------------------------

# Public regex source — single source of truth shared across consumers.
# Word-boundary anchored ; case-insensitive ; matches ANY of the
# forbidden patterns. Compiled at module import for zero per-call cost.
#
# Pattern inventory (round-32) :
#   English-imperative core (round-26 + round-28 superset) :
#     BUY, SELL                                       (2)
#     LONG NOW, SHORT NOW, LONG AT, SHORT AT          (4)
#     ENTER LONG, ENTER SHORT                         (2)
#     TP\d*, SL\d*                                    (2 — bare + numbered laddering)
#     take_profit, stop_loss                          (2 — verbose with \s_- separators)
#     TARGET <number>, ENTRY <number>                 (2 — numeric trade levels)
#     entry_price                                     (1)
#     leverage                                        (1)
#     MARGIN CALL                                     (1)
#   Multilingual imperative extension (round-32, ichor-trader YELLOW fix) :
#     FR :  acheter, achète, achetez                  (3)
#     FR :  vendre, vends, vendez                     (3)
#     ES :  comprar, compra, comprad                  (3)
#     ES :  vender, vende, vended                     (3)
#     DE :  kaufen, kauf, verkaufen, verkauf          (4)
ADR017_FORBIDDEN_REGEX_SOURCE = (
    r"\b("
    # English imperatives (round-26 + round-28)
    r"BUY|SELL|"
    r"LONG\s+NOW|SHORT\s+NOW|LONG\s+AT|SHORT\s+AT|"
    r"ENTER\s+(?:LONG|SHORT)|"
    r"TP\d*|SL\d*|"
    r"take[\s_-]*profit|stop[\s_-]*loss|"
    r"TARGET[\s:]+\d+\.?\d*|ENTRY[\s:]+\d+\.?\d*|entry\s+price|"
    r"leverage|MARGIN\s+CALL|"
    # French imperatives + infinitives (round-32)
    r"acheter|achete|achetez|"
    r"vendre|vends|vendez|"
    # Spanish imperatives + infinitives (round-32)
    r"comprar|compra|comprad|"
    r"vender|vende|vended|"
    # German imperatives + infinitives (round-32)
    r"kaufen|kauf|verkaufen|verkauf"
    r")\b"
)

_ADR017_FORBIDDEN_RE = re.compile(ADR017_FORBIDDEN_REGEX_SOURCE, re.IGNORECASE)


# Human-readable labels — order matches the regex alternation. NOT
# consumed at runtime ; the regex itself is the authoritative match
# engine. Frozenset exists so downstream diagnostics (fitness function
# logging, test enumeration) can list "which patterns ARE blocked"
# without parsing the regex source.
#
# Round-32 round added 5 new labels for multilingual + general "non-EN
# imperatives" coverage. The label count is asserted in
# `test_pattern_labels_present_and_nonempty` ; bumping the regex
# requires bumping this set.
ADR017_FORBIDDEN_PATTERN_LABELS: frozenset[str] = frozenset(
    {
        # English imperatives (round-26 + round-28) — 17 labels
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
        # Multilingual imperatives (round-32) — 5 grouped labels
        "FR : acheter / achète / achetez",
        "FR : vendre / vends / vendez",
        "ES : comprar / compra / comprad",
        "ES : vender / vende / vended",
        "DE : kaufen / kauf / verkaufen / verkauf",
    }
)


# --------------------------------------------------------------------
# Public matching API (normalize → regex pipeline)
# --------------------------------------------------------------------


def is_adr017_clean(text: str) -> bool:
    """Return True iff `text` contains NO ADR-017 forbidden token.

    Canonical defense-in-depth filter applying the round-32 pipeline :
    Unicode normalize (NFKC + zero-width strip + Cyrillic/Greek
    confusable fold) → multilingual regex match.

    Caller MUST gate persistence on `is_adr017_clean(text) is True`.
    Round-32 contract : an LLM emitting `ＢＵＹ` (full-width) /
    `ВUY` (Cyrillic) / `acheter EUR` (French imperative) is REJECTED
    — these were silent passes pre-round-32.
    """
    normalized = _normalize_for_match(text)
    return _ADR017_FORBIDDEN_RE.search(normalized) is None


def find_violations(text: str) -> list[str]:
    """Return the list of forbidden substrings found in `text` after
    round-32 normalization.

    The returned substrings are from the NORMALIZED form, not the
    original. NFKC + confusable folding can change byte sequences —
    callers needing original-position information should run their
    own search using `ADR017_FORBIDDEN_PATTERN_LABELS` as a hint.

    Useful for :
      - Logging the canonical offending fragment when filtering an
        LLM output.
      - GEPA fitness diagnostics (ADR-091) — count + label inspection.

    Order matches normalized-scan order ; duplicates are returned
    (each match is a separate finding).
    """
    normalized = _normalize_for_match(text)
    return [m.group(0) for m in _ADR017_FORBIDDEN_RE.finditer(normalized)]


def count_violations(text: str) -> int:
    """Return the number of forbidden substrings in `text` after
    round-32 normalization.

    Thin convenience over `find_violations` for the GEPA fitness
    function (ADR-091). Avoids materializing the list when the
    operator only wants the scalar.

    ADR-091 amended round-32 : the GEPA fitness function MUST treat
    `count_violations(output) > 0` as a HARD-ZERO gate (fitness =
    `-inf`), NOT a soft-lambda penalty. Soft penalty allows a
    candidate with 1 obfuscated signal to score positive fitness if
    its Brier skill is high enough — that's a known bypass landmine.
    """
    normalized = _normalize_for_match(text)
    return sum(1 for _ in _ADR017_FORBIDDEN_RE.finditer(normalized))
