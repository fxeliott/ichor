"""Wave 1.6 fixed a long-standing bug in the cron template that called
`python -m ichor_api.cli.run_collector` (singular, module doesn't exist)
instead of the actual `run_collectors` module. This test guards against
regression by reading the shell script and asserting the corrected
ExecStart line is present.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_extended_cron_template_uses_correct_module() -> None:
    script = (
        ROOT / "scripts" / "hetzner" / "register-cron-collectors-extended.sh"
    ).read_text(encoding="utf-8")
    # The systemd ExecStart MUST use the plural module name
    assert "run_collectors" in script
    # And explicitly NOT the singular (broken) one
    assert "run_collector %i" not in script
    assert "run_collector\n" not in script
    # The --persist flag must be passed so cron runs actually write to DB
    assert "--persist" in script


def test_extended_cron_template_lists_forex_factory() -> None:
    """forex_factory was added to the SCHEDULES dict in this audit."""
    script = (
        ROOT / "scripts" / "hetzner" / "register-cron-collectors-extended.sh"
    ).read_text(encoding="utf-8")
    assert "[forex_factory]=" in script


def test_register_fx_stream_script_present_and_systemd_unit_simple() -> None:
    """Wave 2.4 added a long-running systemd Type=simple unit (NOT a oneshot
    timer like the cron collectors). Verify the install script exists and
    declares Type=simple."""
    p = ROOT / "scripts" / "hetzner" / "register-fx-stream.sh"
    assert p.exists(), f"register-fx-stream.sh missing at {p}"
    body = p.read_text(encoding="utf-8")
    assert "Type=simple" in body
    assert "Restart=always" in body
    assert "run_fx_stream" in body
    assert "ExecStart=/opt/ichor/api/.venv/bin/python -m ichor_api.cli.run_fx_stream" in body
