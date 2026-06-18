"""S02 socle — CI guard: every Hetzner cron unit with a tolerant
``SuccessExitStatus=`` whitelist MUST also wire ``OnFailure=ichor-notify@``.

Rationale (silent-failure hole)
--------------------------------
The ``scripts/hetzner/register-cron-*.sh`` helpers each emit a systemd
``.service`` unit via a heredoc. A unit that declares ``SuccessExitStatus=``
deliberately tolerates a few non-zero exit codes (transient blips). But a
*hard* failure — OOM kill, ``TimeoutStartSec`` SIGTERM (143), an uncaught
exit 2+, or a unit-start failure — still resolves to ``Result=failed`` and,
without an ``OnFailure=`` handler, is **completely silent**: nobody is paged.

Adding ``OnFailure=ichor-notify@%n.service`` is zero-risk — it only fires
once systemd already considers the unit failed; it does not change *which*
exit codes count as failures (``SuccessExitStatus`` is untouched).

This is a pure-filesystem lint (no DB, no import of app code). It is the
durable guard that keeps the hole from silently reopening when a future
contributor adds a new cron script with a ``SuccessExitStatus`` whitelist
but forgets the ``OnFailure`` line.
"""

from __future__ import annotations

import time
from pathlib import Path

# apps/api/tests/<this file> -> tests(0) -> api(1) -> apps(2) -> repo root(3)
_REPO_ROOT = Path(__file__).resolve().parents[3]
_HETZNER_DIR = _REPO_ROOT / "scripts" / "hetzner"

# Marker that a unit tolerates some non-zero exits (i.e. it has a meaningful
# failure surface worth notifying on).
_SUCCESS_EXIT_MARKER = "SuccessExitStatus"
# The notify handler. ``%n`` expands to the failing unit name at runtime, so we
# only assert the stable prefix is present (``@%n.service`` / ``@<name>`` etc.).
_ONFAILURE_MARKER = "OnFailure=ichor-notify@"

# Lower bound on how many register-cron scripts declare a SuccessExitStatus
# whitelist. If a glob path break or a refactor silently drops the scan to a
# handful of files, this catches it instead of the test passing vacuously.
_MIN_SCRIPTS_WITH_WHITELIST = 40


def _register_cron_scripts() -> list[Path]:
    return sorted(_HETZNER_DIR.glob("register-cron-*.sh"))


def _read_text_stable(path: Path, attempts: int = 5) -> str:
    """Read a script with a small retry.

    On Windows another process (editor, AV scanner, git) can briefly hold a
    file open, surfacing a transient ``OSError``/``PermissionError``. Retrying
    keeps this lint deterministic without weakening any assertion — the file
    contents themselves are stable, only the read access momentarily isn't.
    """
    last_exc: OSError | None = None
    for attempt in range(attempts):
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:  # pragma: no cover - timing dependent
            last_exc = exc
            time.sleep(0.05 * (attempt + 1))
    assert last_exc is not None
    raise last_exc


def test_hetzner_dir_exists() -> None:
    assert _HETZNER_DIR.is_dir(), (
        f"Expected Hetzner cron scripts dir at {_HETZNER_DIR} — repo-root "
        "resolution (parents[3]) is likely wrong."
    )


def test_every_cron_with_success_exit_status_has_onfailure() -> None:
    """A unit that whitelists exit codes must also page on hard failure."""
    scripts = _register_cron_scripts()
    assert scripts, f"No register-cron-*.sh scripts found under {_HETZNER_DIR}"

    scanned_with_whitelist: list[str] = []
    offenders: list[str] = []

    for script in scripts:
        text = _read_text_stable(script)
        if _SUCCESS_EXIT_MARKER not in text:
            continue
        scanned_with_whitelist.append(script.name)
        if _ONFAILURE_MARKER not in text:
            offenders.append(script.name)

    # Sanity: a glob/path break would shrink this list — fail loudly if so.
    assert len(scanned_with_whitelist) >= _MIN_SCRIPTS_WITH_WHITELIST, (
        f"Only {len(scanned_with_whitelist)} register-cron-*.sh scripts with "
        f"'{_SUCCESS_EXIT_MARKER}' were scanned under {_HETZNER_DIR}; expected "
        f"at least {_MIN_SCRIPTS_WITH_WHITELIST}. The glob path is probably "
        "broken — this guard would otherwise pass vacuously."
    )

    assert not offenders, (
        "These Hetzner cron scripts declare a tolerant "
        f"'{_SUCCESS_EXIT_MARKER}=' whitelist but are missing "
        f"'{_ONFAILURE_MARKER}...' — a hard failure (OOM, TimeoutStartSec "
        "SIGTERM=143, exit 2+, unit-start failure) would be SILENT. Add "
        "`OnFailure=ichor-notify@%n.service` to the [Unit] block of the "
        ".service heredoc:\n  - " + "\n  - ".join(sorted(offenders))
    )
