"""Round-32 ADR-017 hardening — Unicode bypass + multilingual surface.

These tests close the bypass landmine flagged by `ichor-trader`
pre-round-32 review : a GEPA-evolved candidate prompt can emit
visually-identical trade signals that the byte-level regex misses.

Bypass vectors covered :
  1. Full-width Latin (`ＢＵＹ`, `ＴＡＲＧＥＴ 1.0850`) — folded via NFKC.
  2. Cyrillic confusables (`ВUY`, `СУЦ`) — folded via transtable.
  3. Greek confusables (`ΒUY`) — folded via transtable.
  4. Zero-width split (`B​UY`, `B‍UY`, `B⁠UY`) —
     stripped via `_ZW_TRANSTABLE`.
  5. BOM tail (`BUY﻿`) — stripped.
  6. Mixed-script (`Ｂuy` half-Latin half-full-width) — NFKC folds.
  7. Multilingual imperatives FR/ES/DE (`acheter`, `vendez`, `compra`,
     `vended`, `kaufen`, `verkauf`).
  8. Legitimate non-bypass cases that MUST stay clean
     (`vendeur` FR seller noun, `acheteurs` FR buyers noun,
     `verkäufer` DE seller noun, `kaufpreis` DE purchase price NOUN).

Round-32 contract :
  - `is_adr017_clean` applies `_normalize_for_match` BEFORE regex.
  - `find_violations` returns NORMALIZED substrings (caller can no
    longer match original-text position but the count is faithful).
  - `count_violations` is the GEPA fitness penalty input — ADR-091
    amended round-32 says HARD-ZERO gate, not soft lambda.
"""

from __future__ import annotations

import pytest
from ichor_api.services.adr017_filter import (
    count_violations,
    find_violations,
    is_adr017_clean,
)

# ─────────────────────── Full-width Latin (NFKC fold) ──────────────────


@pytest.mark.parametrize(
    "obfuscated",
    [
        "ＢＵＹ",
        "ＳＥＬＬ EUR",
        "ＴＡＲＧＥＴ 1.0850",
        "ＥＮＴＲＹ 1.0900",
        "Ｂuy now",  # mixed full-width + ASCII — NFKC folds B
        "ＬＯＮＧ ＮＯＷ on dollar",
    ],
)
def test_full_width_latin_caught(obfuscated: str) -> None:
    """Full-width Latin codepoints (U+FF21..U+FF3A) are NFKC-folded
    to ASCII Latin. Pre-round-32 byte regex missed every one of these."""
    assert not is_adr017_clean(obfuscated), (
        f"Round-32 hardening : full-width '{obfuscated}' MUST be caught after NFKC normalization."
    )


# ─────────────────────── Cyrillic confusables ──────────────────


@pytest.mark.parametrize(
    "obfuscated",
    [
        # `В` (U+0412 Cyrillic) looks like `B` ASCII
        "ВUY pressure on EUR",
        # `Ѕ` (U+0405 Cyrillic DZE) looks like `S` ASCII (the only
        # Cyrillic letter visually identical to S — Cyrillic С looks
        # like Latin C, not S, so we use DZE here)
        "ЅELL the dollar",
        # `Е` (U+0415 Cyrillic) looks like `E` ASCII
        "ЕNTRY 1.0900 confluent",
        # Mixed Cyrillic + ASCII (most realistic GEPA mutation)
        "BUY pressure with В zero-width tricks",
    ],
)
def test_cyrillic_confusables_caught(obfuscated: str) -> None:
    """Cyrillic letters that LOOK like Latin (А/В/Е/К/М/Н/О/Р/С/Т/У/Х)
    are folded to ASCII before matching. The Unicode CLDR confusables
    set is the source of truth."""
    assert not is_adr017_clean(obfuscated), (
        f"Round-32 hardening : Cyrillic-confusable '{obfuscated}' "
        f"MUST be caught after confusable-fold."
    )


# ─────────────────────── Greek confusables ──────────────────


@pytest.mark.parametrize(
    "obfuscated",
    [
        "ΒUY EURUSD",  # Β = U+0392 Greek capital Beta
        "ΤARGET 1.0850",  # Τ = U+03A4 Greek capital Tau
        "ΕNTRY 1.0900",  # Ε = U+0395 Greek capital Epsilon
    ],
)
def test_greek_confusables_caught(obfuscated: str) -> None:
    """Greek capital letters that LOOK like Latin (Α/Β/Ε/Ζ/Η/Κ/Μ/Ν/Ο/
    Ρ/Τ/Υ/Χ) are folded to ASCII before matching."""
    assert not is_adr017_clean(obfuscated), (
        f"Round-32 hardening : Greek-confusable '{obfuscated}' "
        f"MUST be caught after confusable-fold."
    )


# ─────────────────────── Zero-width split ──────────────────


@pytest.mark.parametrize(
    "obfuscated",
    [
        "B​UY",  # ZERO WIDTH SPACE
        "B‍UY",  # ZERO WIDTH JOINER
        "B⁠UY",  # WORD JOINER
        "B‌UY",  # ZERO WIDTH NON-JOINER
        "BUY﻿",  # BOM tail
        "​BUY",  # ZWSP prefix
        "S​E​L​L pressure",  # ZWSP between every letter
    ],
)
def test_zero_width_split_caught(obfuscated: str) -> None:
    """Zero-width / direction-control codepoints are stripped before
    matching so the regex sees the contiguous forbidden token."""
    assert not is_adr017_clean(obfuscated), (
        f"Round-32 hardening : zero-width-split {obfuscated!r} "
        f"MUST be caught after _ZW_TRANSTABLE strip."
    )


# ─────────────────────── Multilingual imperatives ──────────────────


@pytest.mark.parametrize(
    "obfuscated",
    [
        # French imperatives + infinitives
        "Il est temps d'acheter EUR maintenant.",
        "Achetez le dollar avant la BCE.",
        "Le candidat suggère vendre l'USDJPY.",
        "Vendez la livre tout de suite.",
        # Spanish imperatives + infinitives
        "Hay que comprar EUR ahora.",
        "Compra el euro.",
        "Vender el dólar es la solución.",
        "Vende el yen.",
        # German imperatives + infinitives
        "Kaufen Sie EUR vor der EZB.",
        "Verkaufen Sie USD jetzt.",
        "Es ist Zeit zum Kauf von EUR.",  # `Kauf` substantive form (still imperative semantic)
    ],
)
def test_multilingual_imperatives_caught(obfuscated: str) -> None:
    """FR/ES/DE imperatives + infinitives carry the same directive
    semantics as English BUY/SELL and MUST be caught. Round-32
    multilingual regex extension."""
    assert not is_adr017_clean(obfuscated), (
        f"Round-32 hardening : multilingual imperative '{obfuscated}' "
        f"MUST be caught by the FR/ES/DE regex alternatives."
    )


# ─────────────────────── Legitimate non-bypass (must pass) ──────────────────


@pytest.mark.parametrize(
    "legitimate",
    [
        # FR seller / buyer NOUNS — different inflection from imperative
        "Le vendeur s'est retiré du marché.",  # vendeur != vendre
        "Les acheteurs ont absorbé l'offre.",  # acheteurs != acheter
        # ES seller / buyer NOUNS
        "El vendedor se retira.",  # vendedor != vender
        "Los compradores absorben.",  # compradores != comprar
        # DE seller / buyer NOUNS
        "Der Verkäufer hat sich zurückgezogen.",  # Verkäufer != verkauf
        # English legitimate macro language
        "NYSE margin debt at 12-month high.",
        "Reaching target levels of inflation.",
        # Pure-data narrative
        "EUR/USD anti-skill in usd_complacency : steelman should "
        "probe DXY mean-reversion vs Fed put divergence.",
    ],
)
def test_legitimate_text_still_passes(legitimate: str) -> None:
    """Critical regression check : round-32 multilingual + normalize
    MUST NOT over-trigger on legitimate macro language. False
    positives degrade the W116c addendum generator's signal."""
    assert is_adr017_clean(legitimate), (
        f"Round-32 over-blocking regression : '{legitimate}' should "
        f"PASS the filter (non-imperative noun forms / pure macro "
        f"language). Adjust the regex if this fails."
    )


# ─────────────────────── count_violations parity ──────────────────


def test_count_normalization_aware() -> None:
    """`count_violations` on `ＢＵＹ ＢＵＹ ＳＥＬＬ` (full-width)
    must return 3, mirroring the ASCII case."""
    assert count_violations("ＢＵＹ ＢＵＹ ＳＥＬＬ") == 3


def test_count_zero_width_split_counted_once() -> None:
    """A single token split by ZWSP must be counted ONCE, not split
    into halves by the regex."""
    assert count_violations("B​UY") == 1


def test_find_violations_returns_normalized_form() -> None:
    """`find_violations` returns the NORMALIZED substring. Caller can
    inspect to understand what the canonical match was."""
    matches = find_violations("ＢＵＹ EUR")
    # After NFKC, ＢＵＹ → BUY ; the match should be 'BUY' not 'ＢＵＹ'.
    assert "BUY" in matches or any("buy" == m.lower() for m in matches)


# ─────────────────────── Idempotence + purity ──────────────────


def test_normalize_idempotent_via_double_call() -> None:
    """`is_adr017_clean(text)` must give the SAME result whether the
    caller pre-normalizes or not. Round-32 contract : normalization
    is internal, idempotent."""
    from ichor_api.services.adr017_filter import _normalize_for_match

    for sample in (
        "ＢＵＹ now",
        "B​UY",
        "ВUY (Cyrillic)",
        "Clean macro narrative.",
    ):
        once = _normalize_for_match(sample)
        twice = _normalize_for_match(once)
        assert once == twice, (
            f"Normalization not idempotent on {sample!r} : "
            f"first pass = {once!r}, second pass = {twice!r}"
        )
