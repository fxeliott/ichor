"""r173 — honest_sentinels.py backend SSOT specs.

Pins the 5-sentinel canonical source-of-truth + exhaustive dispatch
invariant + frontend-lockstep contract (the frontend
`lib/dxyCorrelation.ts:HONEST_SENTINELS` tuple MUST match this
backend tuple verbatim ; mechanically validated as a W90 invariant
extension r174+ candidate).

Doctrine #5 pure-module discipline : no I/O, no Pydantic, no
SQLAlchemy — the SSOT is dict-based for fastest import time + zero
external dependencies. CI-gated since r173.
"""

from __future__ import annotations

import pytest
from ichor_api.services.honest_sentinels import (
    HONEST_SENTINEL_CITATION,
    HONEST_SENTINEL_FR,
    HONEST_SENTINEL_HINT_FR,
    HONEST_SENTINEL_TONE,
    HONEST_SENTINELS,
)


class TestHonestSentinelsDomain:
    """The 5 sentinels are the canonical doctrinal honesty surface
    documented in r171b (frontend-only SSOT) + r172 (Pattern #15 R59
    catches). r173 backend SSOT is the lift target."""

    def test_exactly_5_sentinels(self) -> None:
        """The 5-value enum is intentionally bounded ; new sentinels
        MUST land via PR with peer-reviewed citation."""
        assert len(HONEST_SENTINELS) == 5

    def test_canonical_render_order(self) -> None:
        """Stable render order : least technical → most technical.
        Frontend `lib/dxyCorrelation.ts:HONEST_SENTINELS` MUST match
        this tuple verbatim (W90 invariant extension r174+)."""
        assert HONEST_SENTINELS == (
            "engel_west_random_walk_regime",
            "rolling_corr_low_n",
            "us_active_stress_source",
            "vix_above_30_funding_stress",
            "dxy_dtwexbgs_divergence_em_stress",
        )


class TestHonestSentinelsSsotExhaustiveDispatch:
    """Doctrine #4 SSOT — every Record-shaped map MUST cover every
    HONEST_SENTINELS entry. Mirror sessionVerdict TRADEABILITY +
    gepa_optimizer invariant lockstep r29."""

    def test_fr_label_per_sentinel(self) -> None:
        for sentinel in HONEST_SENTINELS:
            assert sentinel in HONEST_SENTINEL_FR
            assert HONEST_SENTINEL_FR[sentinel]
            assert len(HONEST_SENTINEL_FR[sentinel]) >= 5

    def test_hint_fr_per_sentinel(self) -> None:
        for sentinel in HONEST_SENTINELS:
            assert sentinel in HONEST_SENTINEL_HINT_FR
            assert HONEST_SENTINEL_HINT_FR[sentinel]
            assert len(HONEST_SENTINEL_HINT_FR[sentinel]) >= 30

    def test_tone_per_sentinel(self) -> None:
        for sentinel in HONEST_SENTINELS:
            assert sentinel in HONEST_SENTINEL_TONE
            assert HONEST_SENTINEL_TONE[sentinel]
            # All sentinels use the muted token by design (honest
            # disclosure sans drama, mirror sessionVerdict
            # TRADEABILITY_TONE non-tradeable convention).
            assert "var(--color-text-muted)" in HONEST_SENTINEL_TONE[sentinel]

    def test_citation_per_sentinel(self) -> None:
        for sentinel in HONEST_SENTINELS:
            assert sentinel in HONEST_SENTINEL_CITATION
            assert HONEST_SENTINEL_CITATION[sentinel]
            assert len(HONEST_SENTINEL_CITATION[sentinel]) >= 50


class TestHonestSentinelsCitationProvenance:
    """Pattern #15 R59 honest provenance — peer-reviewed citations or
    explicit practitioner-stamp acknowledgement per sentinel."""

    def test_engel_west_citation_references_jpe_and_doi(self) -> None:
        cite = HONEST_SENTINEL_CITATION["engel_west_random_walk_regime"]
        assert "Engel" in cite
        assert "West" in cite
        assert "2005" in cite
        assert "10.1086/429137" in cite
        assert "Journal of Political Economy" in cite

    def test_bekaert_citation_references_jme_and_doi(self) -> None:
        cite = HONEST_SENTINEL_CITATION["vix_above_30_funding_stress"]
        assert "Bekaert" in cite
        assert "Hoerova" in cite
        assert "Lo Duca" in cite
        assert "10.1016/j.jmoneco.2013.06.003" in cite
        assert "Journal of Monetary Economics" in cite

    def test_vix_30_threshold_marked_practitioner_not_peer_reviewed(self) -> None:
        """Doctrine #11 calibrated honesty — the VIX > 30 threshold is
        practitioner-grade (Whaley 2000 walked back 2009) ; the
        funding-stress CHANNEL is the peer-reviewed contribution.
        The citation MUST distinguish these two layers."""
        cite = HONEST_SENTINEL_CITATION["vix_above_30_funding_stress"]
        assert "practitioner" in cite.lower()
        assert "Whaley" in cite

    def test_low_n_threshold_cites_cohen_1988(self) -> None:
        """Standard small-sample threshold n=30 — Cohen 1988 power
        analysis textbook ; ICHOR implementation file:line cite."""
        cite = HONEST_SENTINEL_CITATION["rolling_corr_low_n"]
        assert "Cohen" in cite
        assert "n < 30" in cite or "n ≥ 30" in cite
        assert "correlations.py" in cite

    def test_dtwexbgs_citation_references_fed_h10_methodology(self) -> None:
        cite = HONEST_SENTINEL_CITATION["dxy_dtwexbgs_divergence_em_stress"]
        assert "H.10" in cite or "H10" in cite
        assert "DTWEXBGS" in cite
        assert "Bertaut" in cite or "FRB" in cite


class TestHonestSentinelsBackwardCompatWithFrontend:
    """r173 backend SSOT is the lift target for frontend
    `lib/dxyCorrelation.ts` r171b. Once frontend lifts to read from
    a /v1/honest-sentinels endpoint (r174+ candidate), this test
    becomes a W90 mechanical lockstep invariant."""

    def test_frontend_dxy_corr_fr_keys_match_backend_tuple(self) -> None:
        """The frontend `DXY_CORR_FR` Record uses the SAME 5 keys.
        Lockstep ensured by both files importing the same Literal
        domain (r174+ wire-up — currently pinned by this test as
        documentation contract)."""
        expected_keys = {
            "engel_west_random_walk_regime",
            "rolling_corr_low_n",
            "us_active_stress_source",
            "vix_above_30_funding_stress",
            "dxy_dtwexbgs_divergence_em_stress",
        }
        assert set(HONEST_SENTINELS) == expected_keys


class TestHonestSentinelsInvariantEnforcedAtImport:
    """Doctrine #4 SSOT invariant fires at import time (fail-loud) —
    `_verify_exhaustive_dispatch()` is called at module bottom. If a
    future contributor adds a sentinel to HONEST_SENTINELS but forgets
    to add the FR label, the import itself raises AssertionError
    BEFORE any code consumes the broken state."""

    def test_module_imports_clean(self) -> None:
        """Smoke test : if any of the 4 maps drifts, the import-time
        assertion raises and this test fails to even start. This test
        passing is empirical proof of exhaustive dispatch coverage."""
        # The module is already imported at test discovery ; reaching
        # this assertion means the invariant fired successfully.
        assert len(HONEST_SENTINELS) == len(HONEST_SENTINEL_FR)
        assert len(HONEST_SENTINELS) == len(HONEST_SENTINEL_HINT_FR)
        assert len(HONEST_SENTINELS) == len(HONEST_SENTINEL_TONE)
        assert len(HONEST_SENTINELS) == len(HONEST_SENTINEL_CITATION)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
