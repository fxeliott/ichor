"""ADR-017 SSOT enforcement — closes the `adr017-regex-unenforced` finding.

S02 socle audit (2026-06-18). Before this commit the brain validators
(`scenarios` / `session_verdict` / `passes.counterfactual`) each carried a
LOCAL weak 8-token ASCII regex with NO Unicode normalization. The module
docstrings CLAIMED a "byte-identical, CI-guarded" invariant — but no test
actually enforced it, so:

  * obfuscated trade signals (full-width `ＢＵＹ`, Cyrillic `ВUY`, zero-width
    split `B​UY`, FR/ES/DE imperatives `acheter`/`comprar`/`kaufen`) passed
    SILENTLY through `LiveTrigger.description` (which ingests EXTERNAL news /
    GDELT / eco-event text) and the LLM-emitted `mechanism` / `coach` fields ;
  * the three copies could drift without breaking the build.

The fix relocated the canonical filter to `ichor_brain.adr017` (SSOT) and routed
every brain validator through `contains_trade_signal` (normalize → narrow
imperative match). This test makes that boundary REAL and obfuscation-resistant,
and proves the narrow gate does NOT false-positive on legitimate "referenced not
prescribed" technical levels (which would crash a whole card at construction).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ichor_brain.adr017 import contains_trade_signal, is_adr017_clean
from ichor_brain.passes.counterfactual import CounterfactualReading
from ichor_brain.scenarios import InvalidationCondition, Scenario
from ichor_brain.session_verdict import LiveTrigger
from pydantic import ValidationError

# --------------------------------------------------------------------
# Obfuscation / multilingual corpus that the OLD weak ASCII regex MISSED.
# Each must be caught by the normalized narrow gate.
# --------------------------------------------------------------------
OBFUSCATED_SIGNALS = [
    "BUY",  # plain (sanity)
    "ＢＵＹ EUR_USD",  # full-width Latin (NFKC)
    "ВUY now",  # Cyrillic В U+0412
    "ΒUY the dip",  # Greek Β U+0392
    "B​UY here",  # zero-width-space split
    "SELL﻿",  # BOM tail
    "acheter EUR",  # FR imperative
    "achète maintenant",  # FR imperative accented
    "comprar oro",  # ES imperative
    "vender ahora",  # ES imperative
    "kaufen Sie jetzt",  # DE imperative
    "verkaufen",  # DE infinitive
    "long entry at the open",  # English compound
    "stop loss below",  # English compound
    "TP2 then TP3",  # numbered ladder
]

# Legitimate macro / structural prose that must STAY constructible (the narrow
# gate must NOT flag these — they are descriptive, not prescriptive).
LEGITIMATE_PROSE = [
    "Le marché vise 1.0850 comme résistance majeure avant la séance NY.",
    "L'origine acheteuse de la session asiatique reste le pivot du mouvement.",
    "La cible d'inflation de la Fed à 2 % encadre le récit macro.",
    "Un repli sous le support invaliderait la lecture haussière structurée.",
    "Le vendeur a dominé le flux institutionnel en première partie de séance.",
    "Resistance targets near 1.0850 cap the upside per the prior NY range.",
]


@pytest.mark.parametrize("text", OBFUSCATED_SIGNALS)
def test_contains_trade_signal_catches_obfuscation(text: str) -> None:
    assert contains_trade_signal(text) is True, (
        f"obfuscated/multilingual trade signal {text!r} slipped the narrow gate "
        "— the OLD weak ASCII regex bug has regressed"
    )


@pytest.mark.parametrize("text", LEGITIMATE_PROSE)
def test_contains_trade_signal_allows_legitimate_macro_prose(text: str) -> None:
    assert contains_trade_signal(text) is False, (
        f"legitimate descriptive prose {text!r} was flagged as a trade signal — "
        "the narrow construction gate must not false-positive on referenced "
        "(not prescribed) levels, or it crashes legitimate cards at construction"
    )


def _valid_mechanism(extra: str) -> str:
    # mechanism needs >=20 chars ; pad with neutral macro prose.
    return f"Contexte macro structurant la séance de New York. {extra}"


@pytest.mark.parametrize("token", ["BUY", "ＢＵＹ", "acheter", "ВUY", "TP3"])
def test_scenario_mechanism_rejects_obfuscated_signal(token: str) -> None:
    with pytest.raises(ValidationError):
        Scenario(
            label="base",
            p=0.5,
            magnitude_pips=(0.0, 10.0),
            mechanism=_valid_mechanism(f"{token} EUR"),
        )


def test_scenario_mechanism_accepts_level_reference() -> None:
    # "vise 1.0850 comme résistance" — a referenced level, ADR-017 allowed.
    s = Scenario(
        label="mild_bull",
        p=0.4,
        magnitude_pips=(0.0, 30.0),
        mechanism=_valid_mechanism("Le marché vise 1.0850 comme résistance."),
    )
    assert s.label == "mild_bull"


@pytest.mark.parametrize("token", ["SELL", "vendre", "ＳＥＬＬ", "stop loss"])
def test_invalidation_description_rejects_obfuscated_signal(token: str) -> None:
    with pytest.raises(ValidationError):
        InvalidationCondition(
            metric_name="VIX",
            threshold=30.0,
            direction="above",
            severity="hard",
            description=f"Le pic de volatilité {token} invalide le scénario.",
        )


@pytest.mark.parametrize("token", ["BUY", "ВUY", "kaufen", "comprar"])
def test_live_trigger_description_rejects_obfuscated_signal(token: str) -> None:
    # LiveTrigger.description carries EXTERNAL text — the highest-risk surface.
    with pytest.raises(ValidationError):
        LiveTrigger(
            trigger_type="news_headline",
            description=f"Headline burst suggests {token} pressure on the desk.",
            fired_at_utc=datetime.now(UTC),
            impact="tests_verdict",
            source="gdelt:test",
        )


def test_live_trigger_description_accepts_plain_news() -> None:
    lt = LiveTrigger(
        trigger_type="news_headline",
        description="La BCE confirme une pause ; le marché vise 1.0850 en résistance.",
        fired_at_utc=datetime.now(UTC),
        impact="tests_verdict",
        source="gdelt:ecb",
    )
    assert lt.source == "gdelt:ecb"


@pytest.mark.parametrize("token", ["BUY", "acheter", "ＢＵＹ", "long entry"])
def test_counterfactual_narrative_rejects_obfuscated_signal(token: str) -> None:
    with pytest.raises(ValidationError):
        CounterfactualReading(
            scrubbed_event="FOMC",
            counterfactual_bias="neutral",
            counterfactual_conviction_pct=20.0,
            delta_narrative=f"Sans le FOMC, le récit pousse à {token} sur EUR.",
        )


def test_api_reexport_is_the_same_canonical_object() -> None:
    """The apps/api re-export MUST be the identical brain SSOT object — proves
    there is ONE filter, not a drifting copy (the relocation invariant).

    ``ichor_api`` is not installed in the brain test venv ; this assertion is
    also enforced in the apps/api suite (test_adr017_ssot_reexport.py) where both
    packages are present. Skips cleanly here when ichor_api is absent."""
    pytest.importorskip("ichor_api")
    from ichor_api.services.adr017_filter import (  # noqa: PLC0415
        contains_trade_signal as api_contains,
    )
    from ichor_api.services.adr017_filter import (  # noqa: PLC0415
        is_adr017_clean as api_clean,
    )

    assert api_contains is contains_trade_signal
    assert api_clean is is_adr017_clean


def test_strong_gate_still_broad_for_persistence() -> None:
    """is_adr017_clean (persistence gate) stays broad — leverage / TARGET <num>
    / MARGIN CALL are caught there even though the narrow construction gate
    intentionally ignores them."""
    assert is_adr017_clean("leverage is elevated") is False
    assert is_adr017_clean("TARGET 1.0850") is False
    assert is_adr017_clean("MARGIN CALL risk rises") is False
    # ...and the narrow gate intentionally does NOT flag these macro mentions:
    assert contains_trade_signal("leverage is elevated") is False
    assert contains_trade_signal("TARGET 1.0850 as resistance") is False
