"""Pre-commit wrapper for ichor-invariants hook (W90/W91/W92, ADR-081).

Pre-commit on Win11 (`language: system`) calls subprocess.run without
shell=True. Direct entries like a `.bat` wrapper or relative-path
exes (`apps/api/.venv/Scripts/python.exe -m pytest …`) hit
`WinError 2` because the binary token is not resolved through cmd.exe
or PATH.

This Python launcher boots the apps/api venv pytest using only the
host Python (Python 3.14 system, on PATH because pre-commit was
installed with `pip install pre-commit`). Cross-platform : on Linux
the venv path becomes `apps/api/.venv/bin/python`, handled below.

Used by `.pre-commit-config.yaml` :

    entry: python
    args: [scripts/run_invariants.py]
"""

from __future__ import annotations

import os
import subprocess
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TEST_FILE = os.path.join(_REPO_ROOT, "apps", "api", "tests", "test_invariants_ichor.py")

# Win11 venv layout : .venv\Scripts\python.exe
# Linux venv layout : .venv/bin/python
_WIN_VENV_PY = os.path.join(_REPO_ROOT, "apps", "api", ".venv", "Scripts", "python.exe")
_LINUX_VENV_PY = os.path.join(_REPO_ROOT, "apps", "api", ".venv", "bin", "python")


def _resolve_venv_python() -> str:
    """Pick the venv python that exists, regardless of platform."""
    for candidate in (_WIN_VENV_PY, _LINUX_VENV_PY):
        if os.path.exists(candidate):
            return candidate
    sys.stderr.write(
        f"ERROR: apps/api venv python not found at either:\n"
        f"  {_WIN_VENV_PY}\n  {_LINUX_VENV_PY}\n"
        f"Run `python -m venv apps/api/.venv` (or `uv venv`) and "
        f"`apps/api/.venv/Scripts/pip install -e apps/api[dev]` first.\n"
    )
    sys.exit(2)


def main() -> int:
    venv_py = _resolve_venv_python()
    # S603 : subprocess input is fully constructed from this module's
    # constants (`_REPO_ROOT`, `_TEST_FILE`, hard-coded venv paths).
    # No external input flows into the args list. Safe by construction.
    return subprocess.call(  # noqa: S603
        [venv_py, "-m", "pytest", _TEST_FILE, "-q", "--no-header"],
    )


if __name__ == "__main__":
    sys.exit(main())
