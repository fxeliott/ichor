"""r176 — W90 mechanical lockstep invariant between backend SSOT and
frontend duplicate for the 5 HONEST_SENTINEL frame conditions.

Closes the r173 RED-3 lift queue : the frontend `lib/dxyCorrelation.ts`
duplicates the 5-sentinel canonical tuple from the backend SSOT (r173
`services/honest_sentinels.py`). Until the frontend lifts to consume
the backend SSOT via a `/v1/honest-sentinels` endpoint (r177+ candidate),
the 2 source files MUST stay in lockstep — drift between them would
re-introduce the doctrine #4 SSOT debt that r173 closed.

This test mechanically enforces the lockstep by reading both source
files as text + extracting the HONEST_SENTINELS tuple verbatim from
each + asserting identical 5-entry verbatim match. Source-text grep,
no AST — survives Python/TypeScript syntax evolution.

ADR-099 W90 invariant extension r176. Mechanical fail-loud on drift.

Doctrine alignment :
- ADR-081 W90 invariant CI guard discipline
- Doctrine #4 SSOT mechanical enforcement until r177+ frontend lift
- Doctrine #12 anti-recidive : structural test prevents drift entirely
  (vs prompt-only discipline that has drifted across the cumulative
  ledger)
- Pattern #20 r175 codification : memory cites REQUIRE R59-mandatory ;
  this test is the SOURCE-CODE equivalent for the HONEST_SENTINELS
  tuple (mechanical R59 on the canonical 5-key surface)
"""

from __future__ import annotations

import re
from pathlib import Path

# ─────────────────────────────────── PATH HELPERS ──────────────────────


def _backend_source_path() -> Path:
    """Locate the backend SSOT honest_sentinels.py source file."""
    # This test file is at apps/api/tests/test_invariants_honest_sentinels_lockstep.py
    # Backend SSOT is at  apps/api/src/ichor_api/services/honest_sentinels.py
    here = Path(__file__).resolve()
    # tests/ → api/ → ichor_api/services/honest_sentinels.py
    backend = here.parent.parent / "src" / "ichor_api" / "services" / "honest_sentinels.py"
    assert backend.is_file(), f"backend SSOT missing : {backend}"
    return backend


def _frontend_source_path() -> Path:
    """Locate the frontend duplicate lib/dxyCorrelation.ts source file."""
    # Repo root is 3 levels up from tests/ : apps/api/tests → apps/api → apps → repo
    here = Path(__file__).resolve()
    repo_root = here.parent.parent.parent.parent
    frontend = repo_root / "apps" / "web2" / "lib" / "dxyCorrelation.ts"
    assert frontend.is_file(), f"frontend duplicate missing : {frontend}"
    return frontend


# ─────────────────────────────────── EXTRACTORS ────────────────────────


def _extract_backend_honest_sentinels() -> tuple[str, ...]:
    """Extract HONEST_SENTINELS tuple entries from the backend Python
    source via regex on the literal tuple body."""
    source = _backend_source_path().read_text(encoding="utf-8")

    # Match : HONEST_SENTINELS: Final[tuple[HonestSentinelKey, ...]] = (
    #     "engel_west_random_walk_regime",
    #     ...
    # )
    match = re.search(
        r"HONEST_SENTINELS\s*:\s*[^=]*=\s*\((.*?)\)",
        source,
        re.DOTALL,
    )
    assert match, "backend HONEST_SENTINELS tuple not found in source"

    body = match.group(1)
    # Extract string literals (single or double quoted)
    entries = re.findall(r'"([^"]+)"', body)
    assert entries, f"no entries extracted from backend tuple body :\n{body}"
    return tuple(entries)


def _extract_frontend_honest_sentinels() -> tuple[str, ...]:
    """Extract HONEST_SENTINELS tuple entries from the frontend TypeScript
    source via regex on the literal tuple body."""
    source = _frontend_source_path().read_text(encoding="utf-8")

    # Match : export const HONEST_SENTINELS: readonly HonestSentinel[] = [
    #     "engel_west_random_walk_regime",
    #     ...
    # ] as const;
    match = re.search(
        r"export\s+const\s+HONEST_SENTINELS\s*:[^=]*=\s*\[(.*?)\]\s*as\s+const",
        source,
        re.DOTALL,
    )
    assert match, "frontend HONEST_SENTINELS array not found in source"

    body = match.group(1)
    entries = re.findall(r'"([^"]+)"', body)
    assert entries, f"no entries extracted from frontend array body :\n{body}"
    return tuple(entries)


# ─────────────────────────────────── INVARIANT TESTS ───────────────────


class TestHonestSentinelsBackendFrontendLockstep:
    """Mechanical lockstep enforcement : backend SSOT tuple MUST match
    frontend duplicate verbatim. Until r177+ frontend lifts to backend
    SSOT via endpoint, this test prevents doctrine #4 SSOT drift."""

    def test_backend_tuple_has_5_entries(self) -> None:
        """The 5-sentinel canon is bounded ; new sentinels land via PR
        with peer-reviewed citation (per r173 honest_sentinels.py
        module docstring)."""
        backend = _extract_backend_honest_sentinels()
        assert len(backend) == 5, f"backend tuple has {len(backend)} entries, expected 5"

    def test_frontend_tuple_has_5_entries(self) -> None:
        """Frontend duplicate MUST match backend cardinality."""
        frontend = _extract_frontend_honest_sentinels()
        assert len(frontend) == 5, f"frontend tuple has {len(frontend)} entries, expected 5"

    def test_backend_and_frontend_tuples_match_verbatim(self) -> None:
        """The CRITICAL mechanical lockstep — backend and frontend
        HONEST_SENTINELS tuples MUST be identical verbatim including
        order (stable render order : least → most technical per r173
        module docstring)."""
        backend = _extract_backend_honest_sentinels()
        frontend = _extract_frontend_honest_sentinels()
        assert backend == frontend, (
            f"Doctrine #4 SSOT drift detected (r173 RED-3 regression) :\n"
            f"  backend  : {backend}\n"
            f"  frontend : {frontend}\n"
            f"Fix : reconcile `apps/web2/lib/dxyCorrelation.ts:HONEST_SENTINELS` "
            f"with `apps/api/src/ichor_api/services/honest_sentinels.py:HONEST_SENTINELS`"
        )

    def test_canonical_5_sentinels_present(self) -> None:
        """Sanity check : the 5 canonical sentinels MUST all be present
        in backend (and by transitive lockstep, frontend)."""
        backend = _extract_backend_honest_sentinels()
        canonical = {
            "engel_west_random_walk_regime",
            "rolling_corr_low_n",
            "us_active_stress_source",
            "vix_above_30_funding_stress",
            "dxy_dtwexbgs_divergence_em_stress",
        }
        assert set(backend) == canonical, (
            f"canonical 5-sentinel set drift : got {set(backend)}, expected {canonical}"
        )

    def test_render_order_is_least_to_most_technical(self) -> None:
        """Stable render order per r173 module docstring : least
        technical first (engel_west_random_walk_regime) → most
        technical last (dxy_dtwexbgs_divergence_em_stress).
        Frontend UI consumers iterate by index for collapsible chip
        rendering ; render-order drift would silently reshuffle the
        UI."""
        backend = _extract_backend_honest_sentinels()
        assert backend[0] == "engel_west_random_walk_regime", (
            f"render order drift : index 0 should be 'engel_west_random_walk_regime' (least technical), got '{backend[0]}'"
        )
        assert backend[-1] == "dxy_dtwexbgs_divergence_em_stress", (
            f"render order drift : last entry should be 'dxy_dtwexbgs_divergence_em_stress' (most technical), got '{backend[-1]}'"
        )


class TestHonestSentinelsSourceFilesAreCanonicalSSOT:
    """Sanity smoke : both source files exist + are readable. If either
    file is missing, this test fails immediately at module-import time
    (the path-helper asserts fail loud)."""

    def test_backend_source_file_exists_and_is_readable(self) -> None:
        backend = _backend_source_path()
        content = backend.read_text(encoding="utf-8")
        assert "HONEST_SENTINELS" in content, (
            f"backend source missing HONEST_SENTINELS canonical export : {backend}"
        )
        assert "HonestSentinelKey" in content, (
            f"backend source missing HonestSentinelKey Literal type : {backend}"
        )

    def test_frontend_source_file_exists_and_is_readable(self) -> None:
        frontend = _frontend_source_path()
        content = frontend.read_text(encoding="utf-8")
        assert "HONEST_SENTINELS" in content, (
            f"frontend source missing HONEST_SENTINELS canonical export : {frontend}"
        )
        assert "HonestSentinel" in content, (
            f"frontend source missing HonestSentinel TypeScript type : {frontend}"
        )


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
