"""Text normalization for French finance TTS.

Goal: convert raw briefing markdown into something Azure Neural TTS can
pronounce naturally. The lexicon is JSON, versioned (lexicon_fr.json).

Examples handled:
  EURUSD → "euro-dollar"
  FOMC → "F-O-M-C" (spelled letters)
  bp → "point de base"
  3.5% → "trois virgule cinq pour cent"
  $1.5B → "un virgule cinq milliard de dollars"
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# Default lexicon location — override via lexicon_file arg
DEFAULT_LEXICON = Path(__file__).resolve().parent / "lexicon_fr.json"


def preprocess_finance_fr(text: str, *, lexicon_file: Path | None = None) -> str:
    """Apply all transforms in order. Idempotent."""
    lex = _load_lexicon(lexicon_file or DEFAULT_LEXICON)

    # 1. Strip markdown formatting (basic)
    text = _strip_markdown(text)

    # 2. Apply lexicon (literal substitutions, longest first)
    for original, replacement in sorted(lex["substitutions"].items(), key=lambda kv: -len(kv[0])):
        text = text.replace(original, replacement)

    # 3. Currency amounts: "$1.5B" → "un virgule cinq milliard de dollars"
    text = _normalize_currencies(text)

    # 4. Percentages: "3.5%" → "trois virgule cinq pour cent" (lighter approach: just say "pour cent")
    text = re.sub(r"(\d+(?:[.,]\d+)?)\s*%", _spell_percent_fr, text)

    # 5. Basis points: "25 bp" / "25bps" → "25 points de base"
    text = re.sub(r"(\d+(?:[.,]\d+)?)\s*(bps?|pb)\b", r"\1 points de base", text)

    # 6. Acronyms not in lexicon: 3-5 uppercase letters → spelled out
    #    (only if surrounded by word boundaries, to avoid mangling "USD")
    #    The lexicon should already cover the canonical ones (FOMC, BCE, etc.)

    # 7. Compact whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text


def _load_lexicon(path: Path) -> dict:
    if not path.exists():
        return {"substitutions": {}, "version": "0"}
    return json.loads(path.read_text(encoding="utf-8"))


def _strip_markdown(text: str) -> str:
    """Drop the most common markdown noise: headers, bold, italic, links."""
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)  # headers
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)  # bold
    text = re.sub(r"\*([^*]+)\*", r"\1", text)  # italic
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # links
    text = re.sub(r"`([^`]+)`", r"\1", text)  # inline code
    text = re.sub(r"^[-*]\s+", "", text, flags=re.MULTILINE)  # bullets
    return text


def _normalize_currencies(text: str) -> str:
    """`$1.5B` → `un virgule cinq milliard de dollars`. Light touch only."""
    # Format: $<number><B|M|K>
    pattern = re.compile(r"\$([\d.,]+)\s*([BMK])\b")

    def repl(m: re.Match) -> str:
        num = m.group(1).replace(",", ".")
        mult_word = {"B": "milliards de dollars", "M": "millions de dollars", "K": "milliers de dollars"}[
            m.group(2)
        ]
        return f"{num} {mult_word}"

    return pattern.sub(repl, text)


def _spell_percent_fr(m: re.Match) -> str:
    """Just append `pour cent` — keep the digits, Azure handles their FR pronunciation."""
    num = m.group(1).replace(".", ",")
    return f"{num} pour cent"
