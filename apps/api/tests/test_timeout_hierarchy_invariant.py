"""S02 socle DoD guard — the timeout hierarchy is now FALSIFIABLE in CI.

The Session-02 Definition-of-Done names this verbatim as its 2nd criterion
(`docs/PLAN_DIRECTEUR.md`: "the 900/960/5400 timeout hierarchy re-validated")
and `apps/claude-runner/.../config.py:39-52` raises the ordering to a HARD
invariant ("must stay ordered ... keep it strictly below 960"). Yet until this
file, the four numbers lived in four physically separate files across three
packages with NO test cross-checking their order:

    runner per-call   claude_timeout_sec   = 900   (apps/claude-runner config.py)
      <  brain poll    poll_max_total_sec   = 960   (packages/ichor_brain runner_client.py)
      <= Couche-2 poll poll_timeout_sec     = 960   (packages/agents claude_runner.py)
      <  systemd walls TimeoutStartSec      = 1200..5400 (scripts/hetzner register-cron-*.sh)

Rationale (config.py): the runner must kill a stuck `claude -p` subprocess and
return a clean `status="timeout"` BEFORE the consumer's poll budget expires, and
the poll budget must finish before systemd's wall kills the whole unit — so a
hang is classified at the runner (a real timeout), not mislabelled as a
consumer-side give-up or masked by a systemd SIGTERM. A future edit of ONE value
(e.g. bumping a poll to "give it air", or shrinking a wall) would silently
reorder the chain and resurrect that false-timeout class with no CI net. This
test reads the LITERAL source values wherever they live and asserts the order —
parsing source (not importing) so it works regardless of which package venv runs
pytest.

Added by the S02 socle residual-gap audit (2026-06-19) — the gap the dimension
auditors missed and the completeness critic surfaced.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]

_RUNNER_CONFIG = _REPO_ROOT / "apps/claude-runner/src/ichor_claude_runner/config.py"
_BRAIN_CLIENT = _REPO_ROOT / "packages/ichor_brain/src/ichor_brain/runner_client.py"
_COUCHE2_CLIENT = _REPO_ROOT / "packages/agents/src/ichor_agents/claude_runner.py"
_CRON_DIR = _REPO_ROOT / "scripts/hetzner"

# Crons whose work goes through the claude-runner LLM poll path (run a brain
# pass or a Couche-2 agent via the polling client). Their systemd wall MUST sit
# above the poll budget. NON-LLM collector/check crons (walls 120-600s) do NOT
# poll the runner, so the invariant does not apply to them and they are excluded
# on purpose. A NEW LLM-consumer cron must be added here.
_LLM_CONSUMER_CRONS = (
    "register-cron-session-cards.sh",  # run_session_cards_batch — 4+2 passes x 6 cards
    "register-cron-couche2.sh",  # Couche-2 agents (call_agent_task_async)
    "register-cron-counterfactual-batch.sh",
    "register-cron-addendum-generator.sh",
    "register-cron-streaming-refresh.sh",  # run_session_card regen
)


def _extract(path: Path, pattern: str) -> float:
    assert path.exists(), f"timeout-hierarchy source moved/renamed: {path}"
    m = re.search(pattern, path.read_text(encoding="utf-8"))
    assert m, f"timeout value not found in {path.name} via /{pattern}/ — did the constant move?"
    return float(m.group(1))


def _runner_call_sec() -> float:
    return _extract(_RUNNER_CONFIG, r"claude_timeout_sec\s*:\s*int\s*=\s*(\d+)")


def _brain_poll_sec() -> float:
    return _extract(_BRAIN_CLIENT, r"poll_max_total_sec\s*:\s*float\s*=\s*([\d.]+)")


def _couche2_poll_sec() -> float:
    return _extract(_COUCHE2_CLIENT, r"poll_timeout_sec\s*:\s*float\s*=\s*([\d.]+)")


def _cron_wall_sec(script: str) -> float:
    return _extract(_CRON_DIR / script, r"(?m)^TimeoutStartSec=(\d+)")


def test_runner_call_strictly_below_poll_budgets() -> None:
    """config.py:52 — "keep it strictly below 960". The runner must time out a
    stuck subprocess BEFORE either consumer's poll budget gives up."""
    runner = _runner_call_sec()
    brain = _brain_poll_sec()
    couche2 = _couche2_poll_sec()
    assert runner < brain, f"runner per-call {runner}s must be < brain poll {brain}s"
    assert runner < couche2, f"runner per-call {runner}s must be < Couche-2 poll {couche2}s"


def test_brain_and_couche2_poll_budgets_aligned() -> None:
    """The two consumer poll budgets are documented as equal (the "≤" rung).
    Drift between them would mean one consumer gives up before the other on the
    same runner — keep them locked."""
    assert _brain_poll_sec() == _couche2_poll_sec()


@pytest.mark.parametrize("script", _LLM_CONSUMER_CRONS)
def test_poll_budget_strictly_below_every_llm_cron_wall(script: str) -> None:
    """systemd must not SIGTERM an LLM unit before its poll budget completes —
    else the hang is masked as a unit kill instead of a classified timeout."""
    poll = max(_brain_poll_sec(), _couche2_poll_sec())
    wall = _cron_wall_sec(script)
    assert poll < wall, (
        f"{script} wall {wall}s must be > poll budget {poll}s "
        f"(else systemd kills the unit before the poll classifies the timeout)"
    )


def test_canonical_dod_triple_present() -> None:
    """The DoD names the literal 900/960/5400 triple. Pin the canonical anchors
    so a wholesale rewrite of any of the three is caught here, matching the DoD
    wording (PLAN_DIRECTEUR.md §5quater S02)."""
    assert _runner_call_sec() == 900
    assert _brain_poll_sec() == 960
    assert _cron_wall_sec("register-cron-session-cards.sh") == 5400
