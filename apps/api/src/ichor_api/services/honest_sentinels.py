"""honest_sentinels.py — r173 backend SSOT for the 5 HONEST_SENTINEL frame
conditions documented across r171b + r172 (closes doctrine #4 debt).

Materialises the 5 sentinels listed in `_REFERENCE_CORR` honesty stamps
(``correlations.py:91-95`` r171a + Pattern #15 R59 r172 catches) as a
SINGLE canonical source-of-truth consumed by :

- `apps/web2/lib/dxyCorrelation.ts` ``DXY_CORR_FR`` + ``DXY_CORR_HINT_FR``
  + ``DXY_CORR_TONE`` (r171b frontend-only SSOT — should lift to read
  from this backend SSOT via extended `CorrelationOut` Pydantic schema
  in r174+ ; see RED-3 in §Impl(r171b) + §Impl(r172))
- Couche-2 ``news_nlp`` + ``macro`` agents narrative attribution (r174+
  candidate — currently neither consumes the sentinel labels)
- Pass-6 ``Scenario.invalidations`` (ADR-106 Stride 1, r163 Strand C) —
  the 5 sentinels are static frame conditions that bound the
  interpretation of any scenario-fired alert

These are MONITORING flags, NEVER trade signals (ADR-017 boundary). Each
label points to a peer-reviewed framing OR a known cold-start gap. The
5-value enum is a snapshot of the doctrinal honesty surface ; new
sentinels added via PR with peer-reviewed citation justification.

Doctrine alignment :
- ADR-017 boundary preserved (sentinels surface NON-DIRECTIONAL
  interpretation cautions ; never imperatives)
- Doctrine #4 SSOT — this module is THE canonical source ; frontend +
  Couche-2 + Pass-6 consumers read from here, NEVER duplicate the
  labels inline (closes r171b RED-3 + r172 RED-7 debt accumulated
  pre-r173)
- Doctrine #11 calibrated honesty — each sentinel acknowledges a SPECIFIC
  interpretation boundary (random-walk regime / low-n sample / stress
  source / VIX threshold / basket-divergence) with peer-reviewed citation
- Doctrine #12 anti-recidive — Pattern #15 R59 sub-agent identified that
  the 5 labels had ZERO backend SSOT pre-r173 (frontend-only duplicates),
  structural defense by SSOT module prevents future drift

CI guard : `apps/api/tests/test_invariants_ichor.py` W90 invariant
extension r174+ candidate to assert frontend `dxyCorrelation.ts`
``DXY_CORR_FR`` keys match this module's ``HONEST_SENTINELS`` tuple
verbatim (mechanical lockstep). For now, frontend tests
(``__tests__/dxyCorrelation.test.ts`` r171b lines 88-101) pin the
expected keys ; backend pins them HERE as the canonical source.
"""

from __future__ import annotations

from typing import Final, Literal

# ─────────────────────────────────── DOMAIN ───────────────────────────

HonestSentinelKey = Literal[
    "engel_west_random_walk_regime",
    "rolling_corr_low_n",
    "us_active_stress_source",
    "vix_above_30_funding_stress",
    "dxy_dtwexbgs_divergence_em_stress",
]
"""Canonical 5-value literal type for the doctrinal honesty surface.

Ordered tuple `HONEST_SENTINELS` below provides the stable render
order (least technical → most technical) for UI consumption. New
sentinels MUST be appended (not inserted) to preserve back-compat
with frontend consumers that iterate by index. Each addition
requires a peer-reviewed citation in the docstring and a
companion entry in `HONEST_SENTINEL_FR` + `HONEST_SENTINEL_HINT_FR`
+ `HONEST_SENTINEL_TONE` (doctrine #4 SSOT exhaustive dispatch)."""


HONEST_SENTINELS: Final[tuple[HonestSentinelKey, ...]] = (
    "engel_west_random_walk_regime",
    "rolling_corr_low_n",
    "us_active_stress_source",
    "vix_above_30_funding_stress",
    "dxy_dtwexbgs_divergence_em_stress",
)
"""Stable render order for UI consumption — least technical first.
Frontend `lib/dxyCorrelation.ts` ``HONEST_SENTINELS`` tuple MUST match
this verbatim (W90 invariant CI guard r174+ candidate)."""


# ─────────────────────────────────── FR COPY SSOT ──────────────────────

HONEST_SENTINEL_FR: Final[dict[HonestSentinelKey, str]] = {
    "engel_west_random_walk_regime": "Régime random-walk (Engel-West)",
    "rolling_corr_low_n": "Échantillon insuffisant",
    "us_active_stress_source": "Stress d'origine US",
    "vix_above_30_funding_stress": "VIX > 30 — stress de funding",
    "dxy_dtwexbgs_divergence_em_stress": "Divergence DXY / DTWEXBGS — stress EM",
}
"""Short pill-friendly FR label per sentinel. Doctrine #4 SSOT — every
UI surface reads from this map ; never hardcode a translation. Mirror
of frontend `lib/dxyCorrelation.ts:DXY_CORR_FR:133-139` (r171b)."""


HONEST_SENTINEL_HINT_FR: Final[dict[HonestSentinelKey, str]] = {
    "engel_west_random_walk_regime": (
        "Engel-West 2005 (JPE) : les fondamentaux expliquent peu la "
        "variation des changes flottants à court terme — la corrélation "
        "DXY est un signal de co-mouvement à surveiller, pas une "
        "prédiction directionnelle."
    ),
    "rolling_corr_low_n": (
        "Quand la fenêtre de retours horaires est trop courte (n < 30), "
        "la corrélation Pearson est trop bruitée pour être lue — la "
        "cellule reste à — (skip backend)."
    ),
    "us_active_stress_source": (
        "Quand le stress vient des États-Unis (dette, fiscal, élections), "
        "le dollar peut perdre son statut de valeur-refuge et inverser "
        "ses corrélations historiques avec les actifs risqués."
    ),
    "vix_above_30_funding_stress": (
        "Bekaert-Hoerova-Lo Duca 2013 (JME) : VIX > 30 = régime de "
        "stress de funding où les corrélations cross-assets s'effondrent "
        "vers +1 (panique) ou se découplent — lecture standard caduque."
    ),
    "dxy_dtwexbgs_divergence_em_stress": (
        "Quand DXY (basket étroit 6 devises) diverge de DTWEXBGS "
        "(basket large 26 devises), c'est typiquement un stress "
        "émergent — la corrélation DXY-FX-majeur sous-estime alors "
        "le mouvement de fond du dollar."
    ),
}
"""One-sentence FR explainer per sentinel — peer-reviewed citations
inline. Surfaced in collapsible chips so the trader understands WHY
each frame condition bounds the interpretation. Pedagogical — never
imperative (ADR-017). Mirror of frontend
`lib/dxyCorrelation.ts:DXY_CORR_HINT_FR:144-154` (r171b)."""


HONEST_SENTINEL_TONE: Final[dict[HonestSentinelKey, str]] = {
    "engel_west_random_walk_regime": "text-[var(--color-text-muted)]",
    "rolling_corr_low_n": "text-[var(--color-text-muted)]",
    "us_active_stress_source": "text-[var(--color-text-muted)]",
    "vix_above_30_funding_stress": "text-[var(--color-text-muted)]",
    "dxy_dtwexbgs_divergence_em_stress": "text-[var(--color-text-muted)]",
}
"""Tailwind v4 tone token per sentinel. All identical (`text-muted`) —
honest disclosure sans drama, mirror sessionVerdict `TRADEABILITY_TONE`
pattern (r167) for non-tradeable states. Mirror of frontend
`lib/dxyCorrelation.ts:DXY_CORR_TONE:160-166` (r171b)."""


# ─────────────────────────────────── PEER-REVIEWED CITATIONS ──────────

HONEST_SENTINEL_CITATION: Final[dict[HonestSentinelKey, str]] = {
    "engel_west_random_walk_regime": (
        "Engel, C. & West, K. D. (2005). Exchange Rates and Fundamentals. "
        "Journal of Political Economy 113(3):485-517. "
        "DOI: 10.1086/429137. NBER WP 10723."
    ),
    "rolling_corr_low_n": (
        "Standard Pearson correlation small-sample threshold (n ≥ 30) — "
        "see Cohen, J. (1988) Statistical Power Analysis §3.3 ; ICHOR "
        "implementation at `apps/api/src/ichor_api/services/"
        "correlations.py:198` (`len(common) < 30` skip)."
    ),
    "us_active_stress_source": (
        "Practitioner stamp — see e.g. Caballero-Krishnamurthy 2008 "
        "(Journal of Political Economy 116(4):699-724, DOI: 10.1086/591790) "
        "on flight-to-quality reversal during US-originated stress ; "
        "Ranaldo-Söderlind 2010 (Review of Finance 14(3):385-407) on "
        "safe-haven flow inversion."
    ),
    "vix_above_30_funding_stress": (
        "Bekaert, G., Hoerova, M. & Lo Duca, M. (2013). Risk, Uncertainty "
        "and Monetary Policy. Journal of Monetary Economics 60(7):771-788. "
        "DOI: 10.1016/j.jmoneco.2013.06.003. Note: the VIX > 30 threshold "
        "specifically is practitioner (NOT peer-reviewed — Whaley 2000 JPM "
        "originally proposed 'fear zone' at 30 but walked back 2009) ; the "
        "FUNDING-STRESS CHANNEL is the peer-reviewed Bekaert-Hoerova-Lo "
        "Duca contribution."
    ),
    "dxy_dtwexbgs_divergence_em_stress": (
        "Federal Reserve H.10 / FactSet basket methodology — DXY is the "
        "6-currency narrow basket (EUR/JPY/GBP/CAD/SEK/CHF) ; DTWEXBGS "
        "is the trade-weighted broad index (26 currencies, includes EM). "
        "Divergence between the two = EM stress channel decoupling from "
        "G10. See Bertaut-DeMarco-Kamin-Tryon 2012 (FRB International "
        "Finance Discussion Paper 1063) on broad vs narrow USD index "
        "divergence as financial-stress signal."
    ),
}
"""Peer-reviewed citation per sentinel (Pattern #15 R59 honest
provenance). Each entry includes the exact paper/journal/DOI or
explicit 'practitioner stamp' acknowledgement (doctrine #11 calibrated
honesty — when a threshold is practitioner-grade NOT peer-reviewed,
we say so verbatim)."""


# ─────────────────────────────────── INVARIANTS ────────────────────────


def _verify_exhaustive_dispatch() -> None:
    """Doctrine #4 SSOT invariant — every HONEST_SENTINELS entry MUST
    have a key in every Record-shaped map. Mechanically enforced at
    import time (raises at first import if drift, fail-loud). Mirrors
    the sessionVerdict TRADEABILITY pattern + the gepa_optimizer
    invariant lockstep r29.
    """
    for sentinel in HONEST_SENTINELS:
        if sentinel not in HONEST_SENTINEL_FR:
            raise AssertionError(
                f"honest_sentinels.py SSOT drift : '{sentinel}' missing in HONEST_SENTINEL_FR"
            )
        if sentinel not in HONEST_SENTINEL_HINT_FR:
            raise AssertionError(
                f"honest_sentinels.py SSOT drift : '{sentinel}' missing in HONEST_SENTINEL_HINT_FR"
            )
        if sentinel not in HONEST_SENTINEL_TONE:
            raise AssertionError(
                f"honest_sentinels.py SSOT drift : '{sentinel}' missing in HONEST_SENTINEL_TONE"
            )
        if sentinel not in HONEST_SENTINEL_CITATION:
            raise AssertionError(
                f"honest_sentinels.py SSOT drift : '{sentinel}' missing in HONEST_SENTINEL_CITATION"
            )


_verify_exhaustive_dispatch()
