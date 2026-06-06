"""Tests for `scrub_adr017` (S03/G1 deterministic ADR-017 scrubber).

Live web research can splice English trade words into an LLM rationale; the
safety gate then discards the whole card. `scrub_adr017` neutralises them
deterministically BEFORE the gate. Contract: the output is GUARANTEED clean
(`is_adr017_clean(scrub_adr017(x)) is True`) for ANY input, using the same
regex SSOT the gate enforces.
"""

from __future__ import annotations

import pytest
from ichor_api.services.adr017_filter import is_adr017_clean, scrub_adr017


def test_scrub_neutralizes_common_web_trade_words() -> None:
    s = scrub_adr017("Traders buy the dollar amid a sharp sell-off; buy-side flows dominate.")
    assert is_adr017_clean(s)
    # bare english trade words gone, replaced by readable French descriptors
    assert "achats" in s
    assert "repli" in s


def test_scrub_clean_text_is_unchanged() -> None:
    clean = "Le dollar se renforce après un rapport emploi solide (per Reuters, 06-06)."
    assert scrub_adr017(clean) == clean


def test_scrub_empty_passthrough() -> None:
    assert scrub_adr017("") == ""


@pytest.mark.parametrize(
    "bad",
    [
        "BUY now",
        "a brutal sell-off",
        "TP3 at 1.10",
        "set a stop loss",
        "10x leverage",
        "acheter EUR maintenant",  # FR imperative
        "comprar dólares",  # ES imperative
        "TARGET 1.0850",
        "ENTRY 1.0820",
        "ＢＵＹ",  # full-width confusable
    ],
)
def test_scrub_guarantees_clean_for_any_violation(bad: str) -> None:
    """The hard contract: whatever the forbidden token (incl. multilingual /
    full-width obfuscations), the scrubbed output passes the safety gate."""
    assert is_adr017_clean(scrub_adr017(bad)), f"residual violation in scrub of {bad!r}"
