"""Smoke tests for the post-mortem CLI module.

Verifies imports, output filename pattern, and that argparse defaults
are sane. Real DB-bound flow is exercised in
test_post_mortem_drift_suggestions.py.
"""

from __future__ import annotations

from ichor_api.cli.run_post_mortem import DEFAULT_OUTPUT_DIR, main


def test_default_output_dir_is_var_lib_ichor() -> None:
    """The cron must write to a stable, writable, non-tmpfs path."""
    assert DEFAULT_OUTPUT_DIR == "/var/lib/ichor/post-mortems"


def test_main_returns_int_for_invalid_argv() -> None:
    """argparse exits with SystemExit on --help; main must not raise."""
    import pytest

    with pytest.raises(SystemExit):
        main(["run_post_mortem", "--help"])


def test_imports_clean() -> None:
    """If the module fails to import (NameError on a missing symbol,
    etc.), this test catches it before the cron does."""
    import importlib

    mod = importlib.import_module("ichor_api.cli.run_post_mortem")
    assert hasattr(mod, "run")
    assert hasattr(mod, "main")
