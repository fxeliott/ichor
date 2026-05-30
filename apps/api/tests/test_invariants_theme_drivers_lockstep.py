"""r189 — W90 mechanical lockstep invariant between the backend SSOT
8-driver ``THEME_DRIVERS`` tuple and its frontend mirror ``THEME_DRIVER_KEYS``.

The frontend ``apps/web2/lib/themeDominant.ts`` duplicates the 8-driver
canonical tuple from the backend SSOT
(``services/theme_classifier.py:THEME_DRIVERS``). The themeDominant.ts
module docstring itself flags this as a « W90-style lockstep invariant CI
guard r187+ candidate ». Until the frontend lifts to consume the backend
SSOT via an endpoint, the 2 source files MUST stay in lockstep — drift (a
9th driver added backend-only, or a render-order reshuffle) would silently
break the ``<ThemeRankingPanel>`` index-iterated rendering AND re-introduce
the doctrine #4 SSOT debt.

Mirrors ``test_invariants_honest_sentinels_lockstep.py`` (r176) verbatim
pattern : source-text grep, no AST — survives Python/TypeScript syntax
evolution. Mechanical fail-loud on drift.

Doctrine alignment :
- ADR-081 W90 invariant CI guard discipline
- Doctrine #4 SSOT mechanical enforcement until a frontend endpoint lift
- Doctrine #12 anti-recidive : structural test prevents drift entirely
- Pattern #20 : source-code equivalent of mechanical R59 on the canonical
  8-driver surface
"""

from __future__ import annotations

import re
from pathlib import Path

# Canonical 8-driver order (Eliot Fathom transcript page 1 étape 1) —
# slowest-moving regime-defining first → fastest-moving microstructure last.
_CANONICAL_8: tuple[str, ...] = (
    "macroeconomic",
    "monetary_policy",
    "economic_data",
    "fiscal_policy",
    "market_interconnexions",
    "geopolitics",
    "price_action_flow",
    "supply_demand",
)


# ─────────────────────────────────── PATH HELPERS ──────────────────────


def _backend_source_path() -> Path:
    """Locate the backend SSOT theme_classifier.py source file."""
    here = Path(__file__).resolve()
    # tests/ → api/ → ichor_api/services/theme_classifier.py
    backend = here.parent.parent / "src" / "ichor_api" / "services" / "theme_classifier.py"
    assert backend.is_file(), f"backend SSOT missing : {backend}"
    return backend


def _frontend_source_path() -> Path:
    """Locate the frontend mirror lib/themeDominant.ts source file."""
    here = Path(__file__).resolve()
    # apps/api/tests → apps/api → apps → repo root
    repo_root = here.parent.parent.parent.parent
    frontend = repo_root / "apps" / "web2" / "lib" / "themeDominant.ts"
    assert frontend.is_file(), f"frontend mirror missing : {frontend}"
    return frontend


# ─────────────────────────────────── EXTRACTORS ────────────────────────


def _extract_backend_theme_drivers() -> tuple[str, ...]:
    """Extract the THEME_DRIVERS tuple entries from the backend Python
    source via regex on the literal tuple body."""
    source = _backend_source_path().read_text(encoding="utf-8")
    match = re.search(
        r"THEME_DRIVERS\s*:\s*[^=]*=\s*\((.*?)\)",
        source,
        re.DOTALL,
    )
    assert match, "backend THEME_DRIVERS tuple not found in source"
    body = match.group(1)
    entries = re.findall(r'"([^"]+)"', body)
    assert entries, f"no entries extracted from backend tuple body :\n{body}"
    return tuple(entries)


def _extract_frontend_theme_drivers() -> tuple[str, ...]:
    """Extract the THEME_DRIVER_KEYS array entries from the frontend
    TypeScript source via regex on the literal array body."""
    source = _frontend_source_path().read_text(encoding="utf-8")
    match = re.search(
        r"export\s+const\s+THEME_DRIVER_KEYS\s*:[^=]*=\s*\[(.*?)\]\s*as\s+const",
        source,
        re.DOTALL,
    )
    assert match, "frontend THEME_DRIVER_KEYS array not found in source"
    body = match.group(1)
    entries = re.findall(r'"([^"]+)"', body)
    assert entries, f"no entries extracted from frontend array body :\n{body}"
    return tuple(entries)


# ─────────────────────────────────── INVARIANT TESTS ───────────────────


class TestThemeDriversBackendFrontendLockstep:
    """Mechanical lockstep : backend ``THEME_DRIVERS`` tuple MUST match the
    frontend ``THEME_DRIVER_KEYS`` mirror verbatim (including order)."""

    def test_backend_tuple_has_8_entries(self) -> None:
        backend = _extract_backend_theme_drivers()
        assert len(backend) == 8, f"backend tuple has {len(backend)} entries, expected 8"

    def test_frontend_tuple_has_8_entries(self) -> None:
        frontend = _extract_frontend_theme_drivers()
        assert len(frontend) == 8, f"frontend array has {len(frontend)} entries, expected 8"

    def test_backend_and_frontend_tuples_match_verbatim(self) -> None:
        """The CRITICAL mechanical lockstep — identical verbatim, incl.
        order (slow-moving → fast-moving microstructure)."""
        backend = _extract_backend_theme_drivers()
        frontend = _extract_frontend_theme_drivers()
        assert backend == frontend, (
            f"Doctrine #4 SSOT drift detected :\n"
            f"  backend  : {backend}\n"
            f"  frontend : {frontend}\n"
            f"Fix : reconcile `apps/web2/lib/themeDominant.ts:THEME_DRIVER_KEYS` "
            f"with `apps/api/src/ichor_api/services/theme_classifier.py:THEME_DRIVERS`"
        )

    def test_backend_matches_canonical_8(self) -> None:
        assert _extract_backend_theme_drivers() == _CANONICAL_8

    def test_render_order_slow_to_fast(self) -> None:
        """Stable render order : macroeconomic (slowest) first →
        supply_demand (fastest microstructure) last. Frontend panel
        iterates by index ; order drift would silently reshuffle the UI."""
        backend = _extract_backend_theme_drivers()
        assert backend[0] == "macroeconomic", (
            f"render order drift : index 0 should be 'macroeconomic', got '{backend[0]}'"
        )
        assert backend[-1] == "supply_demand", (
            f"render order drift : last should be 'supply_demand', got '{backend[-1]}'"
        )


class TestThemeDriversSourceFilesExist:
    """Sanity smoke : both source files exist + are readable. If either
    is missing, the path helpers fail loud at call time."""

    def test_backend_source_file_exists(self) -> None:
        content = _backend_source_path().read_text(encoding="utf-8")
        assert "THEME_DRIVERS" in content
        assert "ThemeDriverKey" in content

    def test_frontend_source_file_exists(self) -> None:
        content = _frontend_source_path().read_text(encoding="utf-8")
        assert "THEME_DRIVER_KEYS" in content
        assert "ThemeDriverKey" in content


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
