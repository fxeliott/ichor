"""Round-10 adversarial-audit regression guard for the SEAM-1 extraction.

`services/dimension_vote_builders.py` was carved out of the `data_pool` god-file
with a re-export shim. It reads 3 shared constants back from `data_pool`, but
does so LAZILY (inside the functions), so the module carries NO module-level edge
back to `data_pool`. This must stay true: a module-level `from .data_pool import
...` would make a standalone `import dimension_vote_builders` (as the FIRST
ichor_api import, fresh interpreter) deadlock on a partial-init circular import.

We assert it in a fresh subprocess interpreter — pytest collection imports many
modules in-process, so `data_pool` would already be loaded and the cycle would be
masked; only a fresh interpreter actually exercises the standalone-first path.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"


def test_dimension_vote_builders_imports_standalone_first() -> None:
    proc = subprocess.run(
        [sys.executable, "-c", "import ichor_api.services.dimension_vote_builders"],
        cwd=str(_SRC),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, (
        "standalone-first import of dimension_vote_builders failed — a module-level "
        f"back-import to data_pool re-introduced the circular import:\n{proc.stderr}"
    )


def test_dimension_vote_builders_reexport_identity_holds() -> None:
    """The data_pool re-export must remain the SAME object (back-compat shim)."""
    from ichor_api.services.data_pool import build_cot_vote_for_asset as via_pool
    from ichor_api.services.dimension_vote_builders import (
        build_cot_vote_for_asset as via_module,
    )

    assert via_pool is via_module
