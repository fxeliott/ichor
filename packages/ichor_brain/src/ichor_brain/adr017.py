"""ADR-017 boundary filter — the SINGLE canonical home (SSOT).

Session 02 socle audit (2026-06-18) relocation : this module used to live at
``apps/api/src/ichor_api/services/adr017_filter.py``. It was moved DOWN into
``ichor_brain`` (the lower architectural layer, importable without
``ichor_api`` on the path) so that the brain-side construction validators
(``scenarios.Scenario`` / ``InvalidationCondition`` / ``session_verdict``
``SessionVerdict`` / ``LiveTrigger`` / ``passes.counterfactual``) and the
``apps/api`` persistence-gating consumers share ONE source of truth instead of
three drifting byte-identical copies. ``apps/api/.../adr017_filter.py`` now
re-exports this module verbatim (byte-equivalent public surface).

WHY the move closes a real hole — the brain validators used to apply a WEAK
ASCII-only 8-token regex (no Unicode normalization). ``LiveTrigger.description``
ingests EXTERNAL text (news / GDELT / eco-event titles) and the coach/mechanism
fields carry LLM output : a ``ＢＵＹ`` (full-width), ``ВUY`` (Cyrillic), ``B​UY``
(zero-width split) or ``acheter`` (FR imperative) slipped past silently. They now
go through :func:`contains_trade_signal` which normalizes first.

TWO matching surfaces, intentionally distinct :

  * :func:`is_adr017_clean` — the STRONG, broad gate (19+ patterns incl.
    ``leverage`` / ``MARGIN CALL`` / ``TARGET <num>`` / ``ENTRY <num>`` / FR
    signal nouns). Used by PERSISTENCE-gating callers (addendum_generator,
    gepa_optimizer, web_research scrub, card safety gate, streaming_refresh)
    where false-positives are acceptable — a benign macro mention filtered out
    is fine, an obfuscated signal persisted is NOT. UNCHANGED behaviour.

  * :func:`contains_trade_signal` — the NARROW construction-validator gate
    (the original 8 imperative tokens + multilingual imperative VERBS), applied
    AFTER the same normalization. Deliberately EXCLUDES the price-level /
    leverage / margin patterns so a Pass-6 ``mechanism`` that legitimately
    *references* a technical level ("targets 1.0850 as resistance", allowed by
    ADR-017 "referenced not prescribed") does not raise at construction and
    crash a whole card. The narrow set still rejects every imperative trade
    instruction, now obfuscation-resistant.

Round-32 hardening (carried over verbatim) closes 4 known bypass surfaces a
GEPA-evolved candidate prompt could discover :

  1. **Unicode confusables** — ``ＢＵＹ`` (full-width), ``ВUY`` (Cyrillic),
     ``ΒUY`` (Greek). NFKC normalize + Cyrillic/Greek confusable transtable.
  2. **Zero-width characters** — ``B​UY`` (ZWSP-split), ``BUY﻿`` (BOM-tail).
     Strip the canonical zero-width / direction-control set before matching.
  3. **Multilingual imperatives** — ``acheter`` (FR), ``comprar`` (ES),
     ``kaufen`` (DE). Regex extended with FR/ES/DE imperative + infinitive forms.
  4. **Hard-zero fitness contract** — see ADR-091 §"Invariant 2" : a candidate
     output containing ANY forbidden token MUST get fitness = -inf.

Invariant : this module's regex source + normalization pipeline IS the canonical
ADR-017 boundary. Any other module that ships its own copy is a P0 doctrinal
regression (CI-guarded via ``test_adr017_ssot.py`` + ``test_invariants_ichor.py``).
"""

from __future__ import annotations

import re
import unicodedata

# --------------------------------------------------------------------
# Normalization layer (round-32 hardening — pre-regex)
# --------------------------------------------------------------------

# Zero-width / direction-control codepoints stripped before matching.
# Each can split a forbidden token into two pieces the byte-level regex
# would miss. Authoritative inventory from Unicode UAX #9 + UAX #31 +
# RFC 7564 PRECIS confusables.
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
# Subset covering the BUY / SELL / TARGET / ENTRY / LONG / SHORT / TP / SL
# letters that appear in the ADR-017 forbidden patterns. Extending coverage
# is cheap — add a row per attack vector encountered.
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
         (``Ｂ`` U+FF22 → ``B`` U+0042), Arabic presentation forms, etc.
      2. Zero-width / direction-control character strip.
      3. Cyrillic + Greek confusable transtable — visually-identical
         non-Latin letters folded to ASCII Latin.

    Pure + idempotent :
    ``_normalize_for_match(_normalize_for_match(x)) == _normalize_for_match(x)``.
    """
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_ZW_TRANSTABLE)
    text = text.translate(_CONFUSABLE_TRANSTABLE)
    return text


# --------------------------------------------------------------------
# Regex superset (round-31 baseline + round-32 multilingual extension)
# --------------------------------------------------------------------

# Public regex source — single source of truth shared across consumers.
# Word-boundary anchored ; case-insensitive ; matches ANY forbidden pattern.
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
    # French imperatives + infinitives (round-32 ; ach[eè]te closes the
    # accented-imperative gap "achète" caught by the S02 socle audit corpus)
    r"acheter|ach[eè]te|achetez|"
    r"vendre|vends|vendez|"
    # Spanish imperatives + infinitives (round-32)
    r"comprar|compra|comprad|"
    r"vender|vende|vended|"
    # German imperatives + infinitives (round-32)
    r"kaufen|kauf|verkaufen|verkauf|"
    # French ACTIONABLE signal nouns (S05 re-fire M2) — narrow on purpose so
    # « origine acheteuse/vendeuse », « cible d'inflation », « le vendeur » stay
    # CLEAN ; only price-adjacent / explicit position-taking forms match.
    r"points?\s+d['’ ]?\s*entr[ée]es?|niveaux?\s+d['’ ]?\s*entr[ée]es?|prix\s+d['’ ]?\s*entr[ée]es?|"
    r"entr[ée]es?\s+en\s+positions?|entr[ée]es?\s+(?:à|a|au)\s+\d+[.,]\d+|"
    r"cibles?\s+de\s+(?:prix|cours)|objectifs?\s+de\s+(?:prix|cours)|"
    r"prendre\s+(?:une\s+|des\s+)?positions?\s+(?:longues?|courtes?|acheteuses?|vendeuses?)"
    r")\b"
)

_ADR017_FORBIDDEN_RE = re.compile(ADR017_FORBIDDEN_REGEX_SOURCE, re.IGNORECASE)


# Human-readable labels — order matches the regex alternation. NOT consumed at
# runtime ; the regex itself is the authoritative match engine.
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
        # French actionable signal NOUNS (S05 re-fire M2) — 4 grouped labels
        "FR : point / niveau / prix d'entrée",
        "FR : entrée en position / entrée à <prix>",
        "FR : cible de prix·cours / objectif de prix·cours",
        "FR : prendre une position longue / courte / acheteuse / vendeuse",
    }
)


# --------------------------------------------------------------------
# NARROW construction-validator surface (S02 socle audit 2026-06-18)
# --------------------------------------------------------------------

# The imperative trade-instruction tokens that MUST raise at object-construction
# time on the brain validators. This is the original brain 8-token set
# (BUY/SELL/TP/SL/long entry/short entry/stop loss/take profit) PLUS the
# round-32 multilingual imperative VERBS — but deliberately WITHOUT the
# price-level / leverage / margin / signal-noun patterns from the strong gate,
# so a legitimate "referenced not prescribed" technical level does not crash a
# card. Applied AFTER ``_normalize_for_match`` so full-width / Cyrillic /
# zero-width obfuscations no longer slip through (the old weak regex's hole).
_NARROW_FORBIDDEN_REGEX_SOURCE = (
    r"\b("
    # English imperative core (the original brain 8-token set)
    r"BUY|SELL|TP\d*|SL\d*|"
    r"long\s+entry|short\s+entry|stop[\s_-]*loss|take[\s_-]*profit|"
    r"LONG\s+NOW|SHORT\s+NOW|LONG\s+AT|SHORT\s+AT|ENTER\s+(?:LONG|SHORT)|"
    # French imperatives + infinitives (round-32 ; ach[eè]te closes the
    # accented-imperative gap "achète")
    r"acheter|ach[eè]te|achetez|vendre|vends|vendez|"
    # Spanish imperatives + infinitives (round-32)
    r"comprar|compra|comprad|vender|vende|vended|"
    # German imperatives + infinitives (round-32)
    r"kaufen|kauf|verkaufen|verkauf"
    r")\b"
)

_NARROW_FORBIDDEN_RE = re.compile(_NARROW_FORBIDDEN_REGEX_SOURCE, re.IGNORECASE)


def contains_trade_signal(text: str) -> bool:
    """Return True iff ``text`` carries an imperative trade instruction.

    The brain-side construction validator gate (S02 socle audit). Normalizes
    (NFKC + zero-width strip + Cyrillic/Greek fold) then matches the NARROW
    imperative set. Obfuscation-resistant, but does NOT flag a legitimate
    reference to a price level / leverage / target the way the broad
    :func:`is_adr017_clean` does — so a Pass-6 ``mechanism`` that *references*
    "1.0850 as resistance" stays constructible.

    Callers raise ``ValueError`` on ``True`` to enforce the ADR-017 boundary at
    object construction (``Scenario.mechanism``, ``InvalidationCondition``
    ``.description``, ``SessionVerdict.coach_explanation``, ``LiveTrigger``
    ``.description``, ``CounterfactualReading`` narrative/drivers).
    """
    return _NARROW_FORBIDDEN_RE.search(_normalize_for_match(text)) is not None


# --------------------------------------------------------------------
# STRONG public matching API (normalize → broad regex pipeline)
# --------------------------------------------------------------------


def is_adr017_clean(text: str) -> bool:
    """Return True iff ``text`` contains NO ADR-017 forbidden token.

    The STRONG defense-in-depth gate for PERSISTENCE / injection paths : NFKC +
    zero-width strip + Cyrillic/Greek fold → broad multilingual regex (incl.
    leverage / MARGIN CALL / TARGET <num> / ENTRY <num> / FR signal nouns).

    Caller MUST gate persistence on ``is_adr017_clean(text) is True``.
    """
    normalized = _normalize_for_match(text)
    return _ADR017_FORBIDDEN_RE.search(normalized) is None


def find_violations(text: str) -> list[str]:
    """Return the forbidden substrings found in ``text`` after normalization.

    The returned substrings are from the NORMALIZED form (NFKC + confusable
    folding can change byte sequences). Useful for logging the canonical
    offending fragment + GEPA fitness diagnostics (ADR-091).
    """
    normalized = _normalize_for_match(text)
    return [m.group(0) for m in _ADR017_FORBIDDEN_RE.finditer(normalized)]


def count_violations(text: str) -> int:
    """Return the number of forbidden substrings in ``text`` after normalization.

    Thin convenience over :func:`find_violations` for the GEPA fitness function
    (ADR-091) — the MUST treat ``count_violations(output) > 0`` as a HARD-ZERO
    gate (fitness = ``-inf``), never a soft-lambda penalty.
    """
    normalized = _normalize_for_match(text)
    return sum(1 for _ in _ADR017_FORBIDDEN_RE.finditer(normalized))


# --------------------------------------------------------------------
# Deterministic scrubber (S03 / G1 — Opus live web research)
# --------------------------------------------------------------------

# Common English trade words → neutral French descriptors. Order matters :
# compounds (sell-off / buy-side) before the bare buy/sell so the nicer
# replacement wins.
_SCRUB_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bsell[\s\-]?offs?\b", re.IGNORECASE), "repli"),
    (re.compile(r"\bbuy[\s\-]?side\b", re.IGNORECASE), "côté acheteur"),
    (re.compile(r"\bsell[\s\-]?side\b", re.IGNORECASE), "côté vendeur"),
    (re.compile(r"\bbuy\b", re.IGNORECASE), "achats"),
    (re.compile(r"\bsell\b", re.IGNORECASE), "ventes"),
)


def scrub_adr017(text: str) -> str:
    """Return ``text`` with ALL ADR-017 forbidden tokens neutralised —
    GUARANTEED clean : ``is_adr017_clean(scrub_adr017(x)) is True`` for any input.

    Two layers : (1) replace common English trade words with neutral French
    descriptors so the prose stays readable ; (2) if anything still trips the
    canonical regex, NFKC-normalise and redact every remaining match with
    ``[…]`` (which cannot itself match the regex → provably clean). Uses the
    SAME regex SSOT the gate enforces, so cleanliness is exact, not approximate.
    """
    if not text:
        return text
    out = text
    for pat, repl in _SCRUB_REPLACEMENTS:
        out = pat.sub(repl, out)
    if is_adr017_clean(out):
        return out
    normalized = _normalize_for_match(out)
    return _ADR017_FORBIDDEN_RE.sub("[…]", normalized)
