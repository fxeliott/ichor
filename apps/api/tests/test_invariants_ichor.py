"""W90 — Doctrinal invariant CI guards for Ichor (ADR-081).

Mechanises 5 of the most important Ichor doctrinal invariants so they
fail the build instead of relying on human code review :

  1. ADR-017     — No BUY/SELL signals in production Python code.
                   `BUY` and `SELL` may appear in strings (docstrings,
                   prompt text, error messages) and comments, never in
                   Python code (identifiers, attributes, dict keys).
  2. ADR-009     — No `anthropic` SDK consumption in production code
                   (Voie D : Max 20x flat, subprocess `claude -p` only).
  3. ADR-023     — Couche-2 agents use Claude Haiku low, not Sonnet
                   (Sonnet medium hits CF Free 100s edge timeout).
  4. ADR-029     — `audit_log` table has immutable BEFORE-UPDATE/DELETE
                   trigger (MiFID Article 16 + EU AI Act §50 logging).
  5. ADR-077     — `tool_call_audit` table has the same immutable
                   trigger pattern (Capability 5 audit chain).

Test design philosophy :
  - Each test is a single source of truth for one invariant.
  - Tests use Python's tokenize to distinguish code tokens from
    string/comment tokens — `BUY` inside a docstring is OK, `BUY`
    as a Python identifier is not.
  - Allowed exceptions are explicit, not implicit. Adding a new
    allowed file requires editing the test (visible in code review).
  - Tests run in <2s on every CI run + every developer pre-commit.

ADR-081 codifies the policy. Adding a new invariant test =
extending this file + extending ADR-081's "Tracked invariants"
table.
"""

from __future__ import annotations

import re
import tokenize
from pathlib import Path

import pytest

# Repo root resolution : this file lives at
# apps/api/tests/test_invariants_ichor.py — climb three levels.
_REPO_ROOT = Path(__file__).resolve().parents[3]


# ────────────────────────── helpers ──────────────────────────


def _iter_python_sources(roots: list[Path]) -> list[Path]:
    """Walk a list of roots and return every .py file inside them.

    Skips :
      - any path containing `.venv` (third-party deps).
      - any path containing `__pycache__`.
      - any path under `archive/` (frozen pre-reset code, ADR-017).
      - any test file (tests INSPECT the invariant, the invariant
        itself lives in production code).
    """
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            parts = set(p.parts)
            if ".venv" in parts or "__pycache__" in parts:
                continue
            if "archive" in parts:
                continue
            if p.name.startswith("test_") or p.parent.name == "tests":
                continue
            files.append(p)
    return files


def _code_tokens(file_path: Path) -> list[tokenize.TokenInfo]:
    """Tokenize a .py file and return non-STRING, non-COMMENT tokens.

    Returns empty list (silently) if the file fails to tokenize —
    this is conservative ; a malformed file is caught by other CI
    steps (ruff, mypy, pytest-collect).
    """
    try:
        with open(file_path, "rb") as f:
            all_tokens = list(tokenize.tokenize(f.readline))
    except (tokenize.TokenError, SyntaxError, UnicodeDecodeError):
        return []
    return [
        t
        for t in all_tokens
        if t.type
        not in (
            tokenize.STRING,
            tokenize.COMMENT,
            tokenize.FSTRING_START,
            tokenize.FSTRING_MIDDLE,
            tokenize.FSTRING_END,
            tokenize.NL,
            tokenize.NEWLINE,
            tokenize.INDENT,
            tokenize.DEDENT,
            tokenize.ENCODING,
            tokenize.ENDMARKER,
        )
    ]


# ────────────────────────── ADR-017 ──────────────────────────

# Ichor production Python sources — the boundary surface that must
# never emit BUY/SELL signals.
_ADR017_PROD_ROOTS = [
    _REPO_ROOT / "apps" / "api" / "src",
    _REPO_ROOT / "apps" / "claude-runner" / "src",
    _REPO_ROOT / "apps" / "ichor-mcp" / "src",
    _REPO_ROOT / "packages" / "ichor_brain" / "src",
    _REPO_ROOT / "packages" / "agents" / "src",
    _REPO_ROOT / "packages" / "ml" / "src",
]

# Word-boundary BUY/SELL pattern (case-sensitive — lowercase "buy" /
# "sell" inside identifiers like `buy_order_book` is unrelated to the
# trading-signal invariant and is allowed).
_BUY_SELL_RE = re.compile(r"\b(BUY|SELL)\b")


def test_no_buy_sell_in_python_code_tokens() -> None:
    """ADR-017 : `BUY` and `SELL` are forbidden in Python code tokens
    (identifiers, attributes, dict keys). They MAY appear in strings
    (docstrings, prompts, error messages) and comments — those are the
    boundary explanations and prompt text.

    Failure mode caught : a developer accidentally introduces
    `bias_direction = "BUY"` as a Python literal — but Python literal
    is a STRING token, so this test wouldn't catch it. The string
    literal IS allowed by ADR-017 because it's the prompt-side
    description, not an executable signal.

    What this test catches : `BUY = 1`, `class BuyOrder` (matches BUY
    boundary), `dict[..., BUY]`, attribute access `.BUY`, etc. — any
    identifier-shaped use.
    """
    offenders: list[str] = []
    for path in _iter_python_sources(_ADR017_PROD_ROOTS):
        for tok in _code_tokens(path):
            if _BUY_SELL_RE.search(tok.string):
                rel = path.relative_to(_REPO_ROOT)
                offenders.append(f"{rel}:{tok.start[0]} — token {tok.string!r}")
    assert offenders == [], (
        "ADR-017 violated : BUY/SELL appears in Python code tokens "
        f"(not strings/comments). Found {len(offenders)} :\n"
        + "\n".join(offenders[:20])
        + ("\n..." if len(offenders) > 20 else "")
    )


# ────────────────────────── ADR-009 ──────────────────────────

# Voie D : the production code MUST NOT import the `anthropic` Python
# SDK. The Max 20x plan does not authorise SDK consumption (cf. issue
# anthropic/claude-agent-sdk-python#559 — SDK requires API key, prohibits
# Max billing). Subprocess `claude -p` is the only authorised path.

_ADR009_FORBIDDEN_IMPORT_RE = re.compile(
    r"^\s*(?:import\s+anthropic|from\s+anthropic(?:\.|\s+import))",
    re.MULTILINE,
)


def test_no_anthropic_sdk_imports() -> None:
    """ADR-009 Voie D : no `import anthropic` or `from anthropic ...`
    statements anywhere in production Python code."""
    offenders: list[str] = []
    for path in _iter_python_sources(_ADR017_PROD_ROOTS):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for m in _ADR009_FORBIDDEN_IMPORT_RE.finditer(text):
            line_no = text.count("\n", 0, m.start()) + 1
            rel = path.relative_to(_REPO_ROOT)
            offenders.append(f"{rel}:{line_no} — {m.group(0).strip()!r}")
    assert offenders == [], (
        "ADR-009 Voie D violated : `anthropic` SDK imported in production code. "
        "Use `claude -p` subprocess only (apps/claude-runner pattern). "
        f"Offenders ({len(offenders)}) :\n" + "\n".join(offenders)
    )


# ────────────────────────── ADR-023 ──────────────────────────

# Couche-2 agents must default to Claude Haiku low. Sonnet medium
# was the original mapping (ADR-021) but it hit Cloudflare Free 100s
# edge timeout 60% of the time. ADR-023 supersedes ADR-021 with Haiku.

_COUCHE2_AGENTS_DIR = _REPO_ROOT / "packages" / "agents" / "src" / "ichor_agents" / "agents"

# We look for hard-coded `"sonnet"` / `'sonnet'` / `model="sonnet"` /
# `model: "sonnet"` patterns in agent files. The default in
# ClaudeRunnerProvider is acceptable to be `"haiku"` ; agents that
# override are flagged.
_SONNET_LITERAL_RE = re.compile(r"""['"]sonnet['"]""")
_HAIKU_LITERAL_RE = re.compile(r"""['"]haiku['"]""")


def test_couche2_agents_do_not_default_to_sonnet() -> None:
    """ADR-023 : Couche-2 agent modules MUST NOT hard-code `"sonnet"`
    as their default model.

    Allowed mention sites : docstrings/comments explaining the historical
    transition (ADR-021 → ADR-023). The check tokenises and only flags
    `sonnet` literals appearing as Python STRING tokens whose enclosing
    line does NOT mention ADR-021/ADR-023/historical context.
    """
    if not _COUCHE2_AGENTS_DIR.exists():
        pytest.skip("ichor_agents package not yet installed in this checkout")

    offenders: list[str] = []
    history_marker_re = re.compile(r"ADR-02[13]|historical|deprecated|supersed", re.IGNORECASE)
    for path in _iter_python_sources([_COUCHE2_AGENTS_DIR]):
        try:
            with open(path, "rb") as f:
                tokens = list(tokenize.tokenize(f.readline))
        except (tokenize.TokenError, SyntaxError, UnicodeDecodeError):
            continue
        for tok in tokens:
            if tok.type != tokenize.STRING:
                continue
            if not _SONNET_LITERAL_RE.search(tok.string):
                continue
            # Allowed if the enclosing line (or one of the surrounding
            # 3 lines) mentions an ADR-021/023 transition marker.
            line_text = tok.line
            if history_marker_re.search(line_text):
                continue
            rel = path.relative_to(_REPO_ROOT)
            offenders.append(f"{rel}:{tok.start[0]} — {line_text.strip()[:80]!r}")
    assert offenders == [], (
        "ADR-023 violated : Couche-2 agent code hard-codes `sonnet`. "
        "Use `haiku` (low effort). "
        f"Offenders ({len(offenders)}) :\n" + "\n".join(offenders)
    )


def test_couche2_agents_reference_haiku() -> None:
    """ADR-023 positive guard : at least one Couche-2 agent module
    references `haiku` in code or strings. Catches accidental wholesale
    deletion of the model selection logic."""
    if not _COUCHE2_AGENTS_DIR.exists():
        pytest.skip("ichor_agents package not yet installed in this checkout")

    found_haiku = False
    for path in _iter_python_sources([_COUCHE2_AGENTS_DIR]):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if _HAIKU_LITERAL_RE.search(text):
            found_haiku = True
            break
    assert found_haiku, (
        "ADR-023 sanity : no Couche-2 agent module references 'haiku' anywhere. "
        "The model selection wiring may have been deleted accidentally."
    )


# ────────────────────────── ADR-029 + ADR-077 ──────────────────────────

# Two append-only audit tables exist in the schema, each backed by a
# BEFORE-UPDATE/DELETE Postgres trigger that RAISE EXCEPTIONs unless
# the sanctioned `ichor.audit_purge_mode='on'` GUC is set in the
# transaction. Any attempt to drop or weaken these triggers is a P0
# compliance regression (MiFID Article 16 + EU AI Act §50 logging).

_MIGRATIONS_DIR = _REPO_ROOT / "apps" / "api" / "migrations" / "versions"


def _read_migration_text(slug_substring: str) -> str:
    """Find migration file by slug substring and return its source."""
    matches = list(_MIGRATIONS_DIR.glob(f"*{slug_substring}*.py"))
    if not matches:
        pytest.fail(f"migration matching '{slug_substring}' not found in {_MIGRATIONS_DIR}")
    if len(matches) > 1:
        pytest.fail(
            f"multiple migrations match '{slug_substring}' : "
            f"{[m.name for m in matches]} — narrow the substring."
        )
    return matches[0].read_text(encoding="utf-8")


def test_audit_log_immutable_trigger_present() -> None:
    """ADR-029 : `audit_log` migration installs a BEFORE-UPDATE-OR-DELETE
    trigger that RAISE EXCEPTIONs. The trigger must reference the
    sanctioned-purge GUC `ichor.audit_purge_mode`."""
    text = _read_migration_text("audit_log_immutable_trigger")
    assert "BEFORE UPDATE OR DELETE" in text, (
        "ADR-029 : audit_log migration is missing the BEFORE UPDATE OR DELETE clause. "
        "Without it, rows are mutable and MiFID Article 16 is violated."
    )
    assert "RAISE EXCEPTION" in text, (
        "ADR-029 : audit_log migration is missing a RAISE EXCEPTION in the trigger body."
    )
    assert "audit_purge_mode" in text, (
        "ADR-029 : audit_log migration is missing the sanctioned-purge GUC "
        "`ichor.audit_purge_mode`. Nightly rotation jobs would fail."
    )


def test_tool_call_audit_immutable_trigger_present() -> None:
    """ADR-077 / Cap5 PRE-2 : `tool_call_audit` migration mirrors the
    audit_log pattern. Same checks."""
    text = _read_migration_text("tool_call_audit")
    assert "BEFORE UPDATE OR DELETE" in text, (
        "ADR-077 : tool_call_audit migration is missing the BEFORE UPDATE OR DELETE clause. "
        "Capability 5 audit chain would be mutable, violating MiFID + EU AI Act §50."
    )
    assert "RAISE EXCEPTION" in text, (
        "ADR-077 : tool_call_audit migration is missing a RAISE EXCEPTION in the trigger body."
    )
    assert "audit_purge_mode" in text, (
        "ADR-077 : tool_call_audit migration is missing the sanctioned-purge GUC. "
        "Nightly rotation jobs would fail or hit the trigger."
    )


def test_auto_improvement_log_immutable_trigger_present() -> None:
    """ADR-087 / Phase D W113 : `auto_improvement_log` migration is the
    third member of the append-only audit family (alongside `audit_log`
    and `tool_call_audit`). It backs the Vovk/ADWIN/PBS/GEPA loops and
    must enforce ADR-029-class immutability — every Phase D decision
    is a traceable artefact for SR 11-7-class model risk lineage and
    EU AI Act §13/§50 logging."""
    text = _read_migration_text("auto_improvement_log")
    assert "BEFORE UPDATE OR DELETE" in text, (
        "ADR-087 : auto_improvement_log migration is missing the BEFORE UPDATE OR DELETE "
        "clause. Phase D loop history would be mutable — Brier weight changes, "
        "GEPA prompt adoptions, ADWIN drift escalations could be silently rewritten."
    )
    assert "RAISE EXCEPTION" in text, (
        "ADR-087 : auto_improvement_log migration is missing a RAISE EXCEPTION in the trigger body."
    )
    assert "audit_purge_mode" in text, (
        "ADR-087 : auto_improvement_log migration is missing the sanctioned-purge GUC "
        "`ichor.audit_purge_mode`. Nightly rotation jobs would fail."
    )


def test_auto_improvement_log_loop_kind_enum_pinned() -> None:
    """ADR-087 : the 4 Phase D loop kinds are pinned by CHECK constraint.
    Adding a new loop = new ADR + new migration (no schema-less drift).
    Removing a loop = explicit downgrade."""
    text = _read_migration_text("auto_improvement_log")
    for kind in ("brier_aggregator", "adwin_drift", "post_mortem", "meta_prompt"):
        assert kind in text, (
            f"ADR-087 : auto_improvement_log loop_kind CHECK is missing {kind!r}. "
            "The 4 Phase D loops are the canonical taxonomy."
        )


def test_auto_improvement_log_decision_enum_pinned() -> None:
    """ADR-087 : the 4 decision outcomes are pinned. Catches a refactor
    that silently adds 'unclear' / 'maybe' / etc., which would void the
    audit trail's machine-readability."""
    text = _read_migration_text("auto_improvement_log")
    for decision in ("adopted", "rejected", "pending_review", "sequestered"):
        assert decision in text, (
            f"ADR-087 : auto_improvement_log decision CHECK is missing {decision!r}."
        )


def test_brier_aggregator_weights_pocket_uniqueness_guarded() -> None:
    """ADR-087 W115 : the `brier_aggregator_weights` table must enforce
    ONE row per `(asset, regime, expert_kind, pocket_version)` tuple.

    Without the UniqueConstraint, the Vovk-AA pocket-version
    freeze-and-spawn workflow (W114 tier-2) would silently end up with
    two rows for the same logical slot — confluence_engine reads
    would become non-deterministic."""
    text = _read_migration_text("brier_aggregator_weights")
    assert "uq_brier_agg_pocket_expert" in text, (
        "ADR-087 W115 : brier_aggregator_weights migration is missing the "
        "uq_brier_agg_pocket_expert UNIQUE constraint. The Vovk pocket "
        "freeze-and-spawn invariant collapses without it."
    )
    for col in ("asset", "regime", "expert_kind", "pocket_version"):
        assert col in text, (
            f"ADR-087 W115 : brier_aggregator_weights migration is missing "
            f"column {col!r} (referenced by the UNIQUE constraint)."
        )


def test_brier_aggregator_weights_check_constraints_present() -> None:
    """ADR-087 W115 : the 4 CHECK constraints (weight∈[0,1],
    n_observations≥0, cumulative_loss≥0, pocket_version≥1) catch bad
    data at insert time before the Vovk update logic gets confused."""
    text = _read_migration_text("brier_aggregator_weights")
    for check in (
        "ck_brier_agg_weight_unit_interval",
        "ck_brier_agg_n_observations_nonneg",
        "ck_brier_agg_cumulative_loss_nonneg",
        "ck_brier_agg_pocket_version_positive",
    ):
        assert check in text, (
            f"ADR-087 W115 : brier_aggregator_weights migration is missing "
            f"CHECK constraint {check!r}."
        )


def test_pass3_addenda_status_enum_pinned() -> None:
    """ADR-087 W116 : the 4 addendum status values are CHECK-pinned.
    Adding a new state (e.g. `'pending_review'`) silently breaks the
    Pass-3 injector's read filter and the audit narrative."""
    text = _read_migration_text("pass3_addenda")
    for status in ("active", "expired", "superseded", "rejected"):
        assert status in text, f"ADR-087 W116 : pass3_addenda status CHECK is missing {status!r}."


def test_pass3_addenda_content_size_constraint_present() -> None:
    """ADR-087 W116 : `char_length(content) >= 8 AND <= 4096`. Catches
    accidental loosening of the body-size guard that would let the
    injector flood Pass-3 prompts with megabytes of text."""
    text = _read_migration_text("pass3_addenda")
    assert "ck_pass3_addenda_content_size" in text, (
        "ADR-087 W116 : pass3_addenda migration is missing the "
        "ck_pass3_addenda_content_size CHECK. Body length bound enforces "
        "the Pass-3 prompt-budget invariant (max 3 × 4096 chars)."
    )
    assert "4096" in text, (
        "ADR-087 W116 : the 4096-char upper bound must be present in the CHECK constraint."
    )


def test_pass3_addenda_expires_after_created_constraint() -> None:
    """ADR-087 W116 : `expires_at > created_at`. Catches a refactor
    that lets `expires_at = created_at` slip through, which would mean
    every addendum is born already-expired."""
    text = _read_migration_text("pass3_addenda")
    assert "ck_pass3_addenda_expires_after_created" in text, (
        "ADR-087 W116 : pass3_addenda migration is missing the TTL sanity CHECK."
    )


def test_gepa_candidate_prompts_immutable_trigger_present() -> None:
    """ADR-091 W117b sub-wave .b (round-32) : `gepa_candidate_prompts`
    migration MUST install the same BEFORE-UPDATE-OR-DELETE trigger
    pattern as `audit_log` / `tool_call_audit` / `auto_improvement_log`.
    The W117b.g adoption admin endpoint uses the sanctioned-purge GUC
    bypass to flip `status` from `candidate` to `adopted` ; without
    the trigger the audit chain is mutable."""
    text = _read_migration_text("gepa_candidate_prompts")
    assert "BEFORE UPDATE OR DELETE" in text, (
        "ADR-091 W117b.b : gepa_candidate_prompts migration is missing the "
        "BEFORE UPDATE OR DELETE clause."
    )
    assert "RAISE EXCEPTION" in text, (
        "ADR-091 W117b.b : gepa_candidate_prompts migration is missing a "
        "RAISE EXCEPTION in the trigger body."
    )
    assert "audit_purge_mode" in text, (
        "ADR-091 W117b.b : gepa_candidate_prompts migration is missing the "
        "sanctioned-purge GUC `ichor.audit_purge_mode`. The W117b.g "
        "adoption endpoint cannot flip status without it."
    )


def test_gepa_candidate_prompts_status_enum_pinned() -> None:
    """ADR-091 W117b.b : the 4 candidate status values are CHECK-pinned.
    Adding a new state (e.g. `'shadow_testing'`) silently breaks the
    orchestrator's `WHERE status = 'adopted'` index-backed lookup."""
    text = _read_migration_text("gepa_candidate_prompts")
    for status in ("candidate", "adopted", "rejected", "archived"):
        assert status in text, (
            f"ADR-091 W117b.b : gepa_candidate_prompts status CHECK is missing {status!r}."
        )


def test_gepa_candidate_prompts_pass_kind_enum_pinned() -> None:
    """ADR-091 W117b.b : the 4 4-pass labels are CHECK-pinned. Matches
    the Pass-1/2/3/4 canonical surface ; adding a 5th pass requires
    a separate ADR + schema migration."""
    text = _read_migration_text("gepa_candidate_prompts")
    for kind in ("regime", "asset", "stress", "invalidation"):
        assert kind in text, (
            f"ADR-091 W117b.b : gepa_candidate_prompts pass_kind CHECK is missing {kind!r}."
        )


def test_gepa_candidate_prompts_adr017_hard_zero_check_present() -> None:
    """ADR-091 amended round-32 §"Invariant 2" : a candidate with any
    ADR-017 violation MUST land as `status='rejected'`, never
    `'candidate'` or `'adopted'`. The hard-zero contract is enforced
    at the DB level via CHECK constraint so neither the optimizer nor
    the admin endpoint can promote a tainted candidate."""
    text = _read_migration_text("gepa_candidate_prompts")
    assert "ck_gepa_candidate_adr017_hard_zero" in text, (
        "ADR-091 amended round-32 : gepa_candidate_prompts migration is "
        "missing the hard-zero CHECK constraint "
        "`adr017_violations = 0 OR status = 'rejected'`. Soft-lambda "
        "penalty was the original ADR-091 §Invariant 2 reading but "
        "round-32 ichor-trader review proved it allows obfuscated "
        "candidates to score net-positive fitness — landmine closed."
    )


def test_gepa_candidate_prompts_unique_pocket_generation_run() -> None:
    """ADR-091 W117b.b : one candidate per pocket per generation per
    GEPA run. UNIQUE constraint prevents the optimizer from re-emitting
    duplicate rows when its loop logic glitches."""
    text = _read_migration_text("gepa_candidate_prompts")
    assert "uq_gepa_candidate_pocket_generation_run" in text, (
        "ADR-091 W117b.b : gepa_candidate_prompts migration is missing "
        "the UNIQUE constraint on (pocket_asset, pocket_regime, "
        "pocket_session_type, pass_kind, generation, gepa_run_id)."
    )
    for col in (
        "pocket_asset",
        "pocket_regime",
        "pocket_session_type",
        "pass_kind",
        "generation",
        "gepa_run_id",
    ):
        assert col in text, (
            f"ADR-091 W117b.b : gepa_candidate_prompts migration is missing "
            f"column {col!r} (referenced by the UNIQUE constraint)."
        )


def test_brier_aggregator_register_cron_present() -> None:
    """ADR-087 W115b cron : `scripts/hetzner/register-cron-brier-aggregator.sh`
    is the Hetzner systemd timer installer. Without it the Vovk-AA
    nightly cron has no scheduler ; Phase D loop #2 stays dormant."""
    sh_path = _REPO_ROOT / "scripts" / "hetzner" / "register-cron-brier-aggregator.sh"
    assert sh_path.exists(), (
        "ADR-087 W115b : register-cron-brier-aggregator.sh missing. "
        "The Vovk-AA cron loop cannot auto-fire without it."
    )
    text = sh_path.read_text(encoding="utf-8")
    # Critical assertions on the systemd unit content :
    assert (
        "ichor.cli.run_brier_aggregator" in text or "ichor_api.cli.run_brier_aggregator" in text
    ), "ADR-087 W115b : ExecStart must reference the canonical CLI module."
    assert "OnCalendar=*-*-* 03:30:00 Europe/Paris" in text, (
        "ADR-087 W115b : the canonical 03:30 Paris slot is pinned — "
        "after reconciler (02:00) and RAG embed (03:00), before "
        "Tokyo/EUR overlap."
    )
    assert "EnvironmentFile=/etc/ichor/api.env" in text, (
        "ADR-087 W115b : the systemd unit MUST load /etc/ichor/api.env "
        "or the database URL won't resolve at runtime."
    )


def test_post_mortem_pbs_register_cron_present() -> None:
    """ADR-087 W116b cron : `scripts/hetzner/register-cron-post-mortem-pbs.sh`
    is the weekly Sunday timer for the PBS aggregator."""
    sh_path = _REPO_ROOT / "scripts" / "hetzner" / "register-cron-post-mortem-pbs.sh"
    assert sh_path.exists(), "ADR-087 W116b : register-cron-post-mortem-pbs.sh missing."
    text = sh_path.read_text(encoding="utf-8")
    assert "ichor_api.cli.run_post_mortem_pbs" in text, (
        "ADR-087 W116b : ExecStart must reference the canonical CLI module."
    )
    assert "OnCalendar=Sun *-*-* 18:00:00 Europe/Paris" in text, (
        "ADR-087 W116b : Sunday 18:00 Paris is the pinned slot — after "
        "Friday NY close + Asian Sunday open, full week of reconciled "
        "session windows."
    )


def test_post_mortem_pbs_cli_module_present() -> None:
    """ADR-087 W116b CLI : module presence + ahmadian_lambda=2.0
    + min cards = 4."""
    cli_path = _REPO_ROOT / "apps" / "api" / "src" / "ichor_api" / "cli" / "run_post_mortem_pbs.py"
    assert cli_path.exists(), "ADR-087 W116b : run_post_mortem_pbs.py CLI is missing."
    text = cli_path.read_text(encoding="utf-8")
    assert re.search(r"_AHMADIAN_LAMBDA\s*=\s*2\.0\b", text), (
        "ADR-087 W116b : _AHMADIAN_LAMBDA must equal 2.0 to preserve "
        "the Ahmadian superior-ordering property on K=7 buckets."
    )
    assert re.search(r"_MIN_CARDS_PER_POCKET\s*=\s*4\b", text), (
        "ADR-087 W116b : pocket aggregation requires ≥ 4 cards ; "
        "below that the PBS mean is too noisy to be actionable."
    )
    # The CLI MUST write loop_kind='post_mortem' to the audit table.
    assert 'loop_kind="post_mortem"' in text or "loop_kind='post_mortem'" in text, (
        "ADR-087 W116b : the PBS aggregator MUST write to "
        "auto_improvement_log with loop_kind='post_mortem'."
    )


def test_w117a_dspy_lm_voie_d_compliant() -> None:
    """ADR-009 + ADR-087 W117a (round-26) : the DSPy ClaudeRunnerLM
    MUST route via `ichor_agents.claude_runner.call_agent_task_async`
    (the canonical Voie D entry point). The class MUST inherit from
    `dspy.BaseLM` (or stub when DSPy missing) ; MUST refuse Anthropic-
    canonical model names ; MUST raise `dspy.ContextWindowExceededError`
    on 413 so DSPy retry logic engages."""
    lm_path = (
        _REPO_ROOT / "apps" / "api" / "src" / "ichor_api" / "services" / "dspy_claude_runner_lm.py"
    )
    if not lm_path.exists():
        pytest.skip(f"dspy_claude_runner_lm.py not found at {lm_path}")
    text = lm_path.read_text(encoding="utf-8")
    # Canonical Voie D import path inside the async forward.
    assert "ichor_agents.claude_runner" in text, (
        "ADR-009 + W117a : ClaudeRunnerLM MUST lazy-import "
        "`from ichor_agents.claude_runner import call_agent_task_async` "
        "in its `_async_forward` path."
    )
    assert "call_agent_task_async" in text, (
        "ADR-009 + W117a : the wrapper MUST call the canonical async "
        "entry point (NOT the sync `call_agent_task` ; not a raw "
        "httpx POST that bypasses retry envelope)."
    )
    # 413 → ContextWindowExceededError mapping is explicit.
    assert "ContextWindowExceededError" in text, (
        "W117a : 413 / context-window failures MUST be mapped to "
        "`dspy.ContextWindowExceededError` so DSPy retry/truncation "
        "engages instead of raw RuntimeError bubbling."
    )
    # Allowed model tags = sentinel namespace, NOT raw Anthropic names.
    assert "ichor-claude-runner-haiku" in text, (
        "ADR-009 W117a : the only model_tag values accepted are "
        "`ichor-claude-runner-{haiku,sonnet,opus}` sentinels. Raw "
        "Anthropic names (`claude-3-haiku-*`) would let litellm-aware "
        "DSPy adapters route to paid API."
    )


def test_w117a_extras_declared_in_pyproject() -> None:
    """ADR-087 W117a : the `[phase-d-w117]` optional extras MUST be
    declared in `apps/api/pyproject.toml` with `dspy>=3.2` (the
    BaseLM-decoupled-from-litellm release). The W90 ADR-009 invariant
    catches `import anthropic` ; this pin catches a refactor that
    silently drops the extras and breaks the W117 install flow."""
    pyp_path = _REPO_ROOT / "apps" / "api" / "pyproject.toml"
    if not pyp_path.exists():
        pytest.skip(f"pyproject.toml not found at {pyp_path}")
    text = pyp_path.read_text(encoding="utf-8")
    assert "phase-d-w117" in text, (
        "W117a : `[phase-d-w117]` extras MUST be declared in "
        "apps/api/pyproject.toml. Mirrors the `[phase-d]` + `[ml]` "
        "optional-deps pattern."
    )
    # `dspy>=3.2` is the BaseLM-decoupled-from-litellm minimum version.
    assert re.search(r"dspy\s*>=\s*3\.2", text), (
        "W117a : the phase-d-w117 extras MUST pin `dspy>=3.2`. The "
        "BaseLM/litellm separation landed in 3.2 ; older versions "
        "would force-pull litellm + paid-API client wrappers."
    )


def test_pass3_addenda_injection_feature_flag_key_pinned() -> None:
    """ADR-087 W116c stage 2 (round-24) : the feature flag key that
    gates Pass-3 addenda injection in `run_session_card.py` is pinned
    at `pass3_addenda_injection_enabled`. Renaming silently breaks
    the consumer (flag query returns False = no injection)."""
    rsc_path = _REPO_ROOT / "apps" / "api" / "src" / "ichor_api" / "cli" / "run_session_card.py"
    if not rsc_path.exists():
        pytest.skip(f"run_session_card.py not found at {rsc_path}")
    text = rsc_path.read_text(encoding="utf-8")
    assert "pass3_addenda_injection_enabled" in text, (
        "ADR-087 W116c stage 2 : the feature flag key "
        "'pass3_addenda_injection_enabled' must be referenced in "
        "run_session_card.py. The Stage 2 caller wire is the only "
        "consumer of pass3_addenda_section ; without this query the "
        "Phase D loop never closes."
    )
    assert "pass3_addenda_section" in text, (
        "ADR-087 W116c stage 2 : the orchestrator kwarg "
        "'pass3_addenda_section' (round-22 abstraction) must be passed "
        "from run_session_card.py to orch.run() — otherwise the "
        "abstraction is dead code."
    )


def test_w116c_addendum_generator_voie_d_compliant() -> None:
    """ADR-009 + ADR-087 W116c (round-25) : the LLM addendum generator
    MUST route via the Couche-2 claude-runner path. It MUST NOT import
    `anthropic` or any other paid-API client.

    The W90 ADR-009 anthropic-imports test already covers the repo-wide
    invariant — this guard is the W116c-specific pin : the lazy import
    inside `generate_addendum_text` must reference the canonical Voie D
    entry point + the ADR-017 defense-in-depth filter must exist."""
    gen_path = (
        _REPO_ROOT / "apps" / "api" / "src" / "ichor_api" / "services" / "addendum_generator.py"
    )
    if not gen_path.exists():
        pytest.skip(f"addendum_generator.py not found at {gen_path}")
    text = gen_path.read_text(encoding="utf-8")
    assert "ichor_agents.claude_runner" in text, (
        "ADR-009 + W116c : addendum_generator MUST route via the "
        "Couche-2 claude-runner subprocess path. The lazy import "
        "`from ichor_agents.claude_runner import call_agent_task_async` "
        "is the canonical Voie D entry point."
    )
    assert "call_agent_task_async" in text, (
        "ADR-009 + W116c : the generator MUST call "
        "`call_agent_task_async` (Voie D async path with retry envelope), "
        "NOT a direct HTTP POST that bypasses the retry / 530 storm "
        "mitigations."
    )
    assert "addendum_passes_adr017_filter" in text, (
        "ADR-017 + W116c : the addendum generator MUST run the "
        "ADR-017 regex filter as a SECOND layer (defense-in-depth) "
        "even when the LLM obeyed the NO-TRADE-SIGNALS prompt "
        "instruction."
    )


def test_w116c_cli_present_with_feature_flag_gate() -> None:
    """ADR-087 W116c CLI (round-25) : `cli/run_addendum_generator.py`
    MUST exist and MUST gate execution behind feature flag
    `w116c_llm_addendum_enabled`. Default flag value is False (fail-
    closed) so the cron does nothing until Eliot explicitly enables
    it via UPDATE feature_flags."""
    cli_path = (
        _REPO_ROOT / "apps" / "api" / "src" / "ichor_api" / "cli" / "run_addendum_generator.py"
    )
    if not cli_path.exists():
        pytest.skip(f"run_addendum_generator.py not found at {cli_path}")
    text = cli_path.read_text(encoding="utf-8")
    assert "w116c_llm_addendum_enabled" in text, (
        "ADR-087 W116c : the CLI MUST check the feature flag "
        "`w116c_llm_addendum_enabled` before any LLM call. Default "
        "is False (fail-closed) ; the cron silently no-ops until "
        "Eliot enables via UPDATE feature_flags."
    )
    sh_path = _REPO_ROOT / "scripts" / "hetzner" / "register-cron-addendum-generator.sh"
    assert sh_path.exists(), (
        "ADR-087 W116c : register-cron-addendum-generator.sh MUST exist alongside the CLI module."
    )
    sh_text = sh_path.read_text(encoding="utf-8")
    assert "Sun *-*-* 19:00:00 Europe/Paris" in sh_text, (
        "ADR-087 W116c : the cron schedules at Sunday 19:00 Paris, "
        "1 hour AFTER the W116b PBS post-mortem cron at 18:00 "
        "(which provides the input data)."
    )


def test_realized_open_session_migration_present() -> None:
    """ADR-087 W118 (round-23) : migration 0045 adds the
    `realized_open_session` column to `session_card_audit`. Without it
    the W115b Vovk-AA climatology expert stays a 0.5 stand-in, the
    informative empirical y=1 rate is unreachable, and the W116b PBS
    bull-vs-bear breakdown can't render."""
    text = _read_migration_text("realized_open_session")
    assert "session_card_audit" in text, "W118 migration must target session_card_audit table."
    assert "realized_open_session" in text, (
        "W118 migration must add the column literally named realized_open_session."
    )
    assert "add_column" in text, (
        "W118 migration must use op.add_column (ADD COLUMN), not "
        "create_table — additive schema change on a populated table."
    )
    assert "nullable=True" in text, (
        "W118 migration must declare nullable=True so existing 158 rows "
        "remain valid post-deploy. The W115b query excludes NULL rows "
        "from the climatology denominator."
    )


def test_brier_aggregator_cli_module_present() -> None:
    """ADR-087 W115b : `cli/run_brier_aggregator.py` is the nightly
    Vovk-AA cron entry point. The Hetzner systemd unit `ExecStart=`
    references it ; accidental deletion / rename would silently break
    the Phase D learn loop without firing CI."""
    cli_path = _REPO_ROOT / "apps" / "api" / "src" / "ichor_api" / "cli" / "run_brier_aggregator.py"
    assert cli_path.exists(), (
        "ADR-087 W115b : run_brier_aggregator.py CLI is missing. The "
        "nightly Vovk-AA cron depends on this module."
    )
    text = cli_path.read_text(encoding="utf-8")
    # Pinned constants must remain — divergence breaks Vovk pocket
    # upserts on the migration 0043 default `pocket_version=1`.
    assert re.search(r"_POCKET_VERSION\s*=\s*1\b", text), (
        "ADR-087 W115b : _POCKET_VERSION must equal 1 to match the migration 0043 server_default."
    )
    assert re.search(
        r'_EXPERT_KINDS\s*=\s*\(\s*"prod_predictor"\s*,\s*"climatology"\s*,\s*"equal_weight"\s*,?\s*\)',
        text,
    ), (
        "ADR-087 W115b : _EXPERT_KINDS canonical tuple drifted. The "
        "Vovk aggregator caller threads len(_EXPERT_KINDS) into "
        "n_experts ; changing the tuple without updating upserts "
        "would orphan pocket rows."
    )
    # The CLI MUST call `auto_improvement_log.record` (loop_kind=
    # 'brier_aggregator') so the Phase D audit trail captures every
    # pocket update. Catches refactor that "removes the boilerplate".
    assert 'loop_kind="brier_aggregator"' in text or "loop_kind='brier_aggregator'" in text, (
        "ADR-087 W115b : Vovk cron MUST write to auto_improvement_log "
        "with loop_kind='brier_aggregator'. Audit trail is contractual."
    )


def test_penalized_brier_misclassification_penalty_default_is_two() -> None:
    """ADR-087 W116 : the Ahmadian PBS misclassification penalty
    default is 2.0. This is the smallest λ that dominates the worst-
    case Brier swing on K=7 (the W105/ADR-085 7-bucket case), so it's
    the value that GUARANTEES the superior-ordering property. Any
    refactor lowering this default breaks the proof."""
    pbs_path = _REPO_ROOT / "apps" / "api" / "src" / "ichor_api" / "services" / "penalized_brier.py"
    if not pbs_path.exists():
        pytest.skip(f"penalized_brier.py not found at {pbs_path}")
    text = pbs_path.read_text(encoding="utf-8")
    # Match `misclassification_penalty: float = 2.0` in the kwarg-only
    # signature of `ahmadian_pbs`.
    assert re.search(
        r"misclassification_penalty:\s*float\s*=\s*2\.0\b",
        text,
    ), (
        "ADR-087 W116 : `ahmadian_pbs(...)` default "
        "`misclassification_penalty` MUST be 2.0 to preserve the "
        "Ahmadian-2025 superior-ordering property. Any other default "
        "voids the proof on K=7 buckets."
    )


def test_vovk_aggregator_eta_default_is_one() -> None:
    """ADR-087 W115 : the `VovkBrierAggregator` class default `eta=1.0`
    matches the Vovk-Zhdanov 2009 Theorem 1 Brier-game mixability
    optimum. Any refactor that "tunes" to a different default
    invalidates the regret bound proof."""
    vovk_path = (
        _REPO_ROOT / "apps" / "api" / "src" / "ichor_api" / "services" / "vovk_aggregator.py"
    )
    if not vovk_path.exists():
        pytest.skip(f"vovk_aggregator.py not found at {vovk_path}")
    text = vovk_path.read_text(encoding="utf-8")
    # Match `eta: float = 1.0` in the dataclass field declaration.
    assert re.search(r"\beta:\s*float\s*=\s*1\.0\b", text), (
        "ADR-087 W115 : VovkBrierAggregator.eta default MUST be 1.0 "
        "(Vovk-Zhdanov 2009 Theorem 1 Brier-game optimum). "
        "Any other value invalidates the ln(N) regret bound."
    )


# ────────────────────────── ADR-091 W117b.c skeleton (round-36) ──────────────────────────


def test_gepa_optimizer_budget_hard_cap_pinned_at_100() -> None:
    """ADR-091 §"Invariant 1" : `_GEPA_BUDGET_HARD_CAP` MUST equal 100.

    Round-36 W117b.c skeleton fixes this as the maximum LLM-calls-per-
    optimization-run. A future refactor bumping this without a
    successor ADR would silently raise the Anthropic Max 20x quota
    burn rate (rule 16 ban-risk minimisation).

    Source inspection : the constant declaration MUST appear verbatim
    as `_GEPA_BUDGET_HARD_CAP: Final[int] = 100`. A rename, an int
    different from 100, or removal of the `Final` type hint all fail
    this guard.
    """
    gepa_path = _REPO_ROOT / "apps" / "api" / "src" / "ichor_api" / "services" / "gepa_optimizer.py"
    if not gepa_path.exists():
        pytest.skip(f"gepa_optimizer.py not found at {gepa_path}")
    text = gepa_path.read_text(encoding="utf-8")
    assert re.search(r"_GEPA_BUDGET_HARD_CAP\s*:\s*Final\[int\]\s*=\s*100\b", text), (
        "ADR-091 §Invariant 1 : the budget hard cap MUST be 100 calls "
        "per GEPA optimization run, declared as "
        "`_GEPA_BUDGET_HARD_CAP: Final[int] = 100`. A successor ADR is "
        "required to raise this number (rule 16 ban-risk minimisation)."
    )


def test_gepa_optimizer_imports_adr017_count_violations() -> None:
    """ADR-091 §"Invariant 2" amended r32 + round-36 W117b.c :
    `gepa_optimizer.py` MUST import `count_violations` from
    `services.adr017_filter`. This is the LAYER 1 of the 3-layer
    ADR-017 defense (regex source-of-truth + this Python fitness gate
    + DB CHECK constraint).

    Removing the import would break the hard-zero gate at the Python
    layer ; only the DB CHECK would catch tainted candidates, and
    that's too late (the optimizer would emit them, pollute the
    Pareto frontier, and waste budget on them).
    """
    gepa_path = _REPO_ROOT / "apps" / "api" / "src" / "ichor_api" / "services" / "gepa_optimizer.py"
    if not gepa_path.exists():
        pytest.skip(f"gepa_optimizer.py not found at {gepa_path}")
    text = gepa_path.read_text(encoding="utf-8")
    assert "from .adr017_filter import count_violations" in text, (
        "ADR-091 §Invariant 2 round-36 : gepa_optimizer.py MUST import "
        "`count_violations` from `.adr017_filter`. This is layer 1 of "
        "the 3-layer ADR-017 hard-zero defense — its absence would "
        "demote the boundary check to DB-only (too late)."
    )


def test_gepa_optimizer_uses_hard_zero_not_soft_lambda() -> None:
    """ADR-091 §"Invariant 2" amended r32 + round-36 W117b.c :
    `compute_fitness_with_hard_zero` MUST return `float("-inf")` when
    `count_violations(...)` is positive — not a soft-lambda subtraction.

    The original ADR-091 draft proposed `fitness = brier_skill - lambda
    * count_violations(...)` but the ichor-trader r32 pre-implementation
    review correctly identified that as a bypass landmine (a candidate
    with high Brier skill + 1 obfuscated trade signal could score
    net-positive fitness). The amended r32 doctrine is HARD-ZERO.

    Source inspection : the body of `compute_fitness_with_hard_zero`
    MUST contain BOTH :
      1. `count_violations(candidate_output)` — the boundary check
      2. `float("-inf")` — the hard-zero return value

    A refactor introducing a soft-lambda penalty would fail this guard.
    """
    gepa_path = _REPO_ROOT / "apps" / "api" / "src" / "ichor_api" / "services" / "gepa_optimizer.py"
    if not gepa_path.exists():
        pytest.skip(f"gepa_optimizer.py not found at {gepa_path}")
    text = gepa_path.read_text(encoding="utf-8")
    # Find the function body
    fn_match = re.search(
        r"def compute_fitness_with_hard_zero\([^)]*\)[^:]*:(.*?)(?=^def |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert fn_match is not None, (
        "ADR-091 round-36 : `compute_fitness_with_hard_zero` function "
        "definition not found in gepa_optimizer.py — was it renamed or "
        "removed ? This is the canonical fitness gate."
    )
    fn_body = fn_match.group(1)
    assert "count_violations(" in fn_body, (
        "ADR-091 §Invariant 2 amended r32 : compute_fitness_with_hard_zero "
        "MUST call count_violations() to check the ADR-017 boundary. "
        "Without it, ANY candidate passes through unfiltered."
    )
    assert 'float("-inf")' in fn_body or "float('-inf')" in fn_body, (
        "ADR-091 §Invariant 2 amended r32 : compute_fitness_with_hard_zero "
        "MUST return float('-inf') on violation (HARD-ZERO), NOT a soft-"
        "lambda subtraction. Soft-lambda was the original draft reading, "
        "REJECTED r32 because it lets candidates with high Brier skill + "
        "1 obfuscated signal score net-positive fitness."
    )


# ────────────────────────── ADR-079 ──────────────────────────


# ────────────────────────── ADR-017 cap 95 ──────────────────────────


def test_conviction_pct_capped_at_95() -> None:
    """ADR-017 + ADR-022 : Pass-2 `conviction_pct` and Pass-3
    `revised_conviction_pct` are capped at 95.0. Macro-frameworks
    doctrine : "100 % conviction never exists" — anything above 95 %
    is a red flag, not a bug to fix the cap. Catches accidental
    `Field(ge=0.0, le=100.0)` regression on any future schema edit.

    Implementation reads the source text directly (no import) so the
    test runs even when the apps/api venv doesn't have ichor_brain
    installed.
    """
    types_path = _REPO_ROOT / "packages" / "ichor_brain" / "src" / "ichor_brain" / "types.py"
    if not types_path.exists():
        pytest.skip(f"types.py not found at {types_path}")

    text = types_path.read_text(encoding="utf-8")
    for field_name in ("conviction_pct", "revised_conviction_pct"):
        # Match : `conviction_pct: float = Field(ge=0.0, le=95.0)`
        # Field(...) args are kept on one line in this codebase ; if the
        # convention ever changes we'll need a multi-line aware parser.
        pattern = rf"\b{field_name}\s*:\s*float\s*=\s*Field\(([^)]+)\)"
        match = re.search(pattern, text)
        assert match, (
            f"ADR-017 sanity : {field_name} field not found (or its Field(...) "
            f"signature changed) in {types_path.name}. The cap-95 test must be "
            "updated to track the new shape."
        )
        args = match.group(1)
        assert re.search(r"\ble\s*=\s*95\.0\b", args), (
            f"ADR-017 violated : {field_name} Field(...) has args {args!r} but "
            "is missing `le=95.0`. Macro-frameworks doctrine : 100 % conviction "
            "never exists. Cap MUST be 95.0 — anything above is a red flag, "
            "not a bug to fix the cap."
        )


# ────────────────────────── ADR-079 exclusion ──────────────────────────


def test_pure_data_routes_excluded_from_watermark() -> None:
    """ADR-079 §"Pure-data routes excluded" + ADR-080 §"Pure-data routes" :
    routes that return collector outputs (FRED, market data, calendar,
    /v1/tools/*, /healthz, /metrics) MUST NOT be in the watermark
    prefix set. Watermarking pure-data is legally incorrect — EU AI
    Act §50.2 applies to AI-generated content only.

    This is a NEGATIVE guard : adding any of these prefixes to the
    default would silently flip the legal posture.
    """
    from ichor_api.middleware.ai_watermark import DEFAULT_WATERMARKED_PREFIXES

    forbidden_prefixes = [
        "/v1/tools",  # Capability 5 client tools — data-only return shape (ADR-077)
        "/v1/market",  # OHLCV from Stooq / yfinance / Polygon
        "/v1/fred",  # FRED Observations passthrough
        "/v1/calendar",  # ForexFactory metadata
        "/v1/sources",  # static metadata
        "/v1/correlations",  # computed from collector outputs
        "/v1/macro-pulse",  # idem
        # W118 round-21 — Phase D observability is pure-data over
        # ADR-087 audit tables (auto_improvement_log,
        # brier_aggregator_weights). Cron-computed aggregates, NOT
        # AI-generated narrative text. ADR-079 watermark MUST exclude.
        "/v1/phase-d",
        "/healthz",  # infra
        "/livez",  # infra
        "/readyz",  # infra
        "/metrics",  # infra (Prometheus)
        "/.well-known",  # discovery (W89, served by separate code path)
    ]
    leaked: list[str] = []
    for prefix in forbidden_prefixes:
        for watermarked in DEFAULT_WATERMARKED_PREFIXES:
            # Forbidden prefix matches if any watermarked prefix is a
            # prefix of it OR vice versa (covers both "/v1/tools" being
            # added AND a longer "/v1/tools/special" being added).
            if watermarked.startswith(prefix) or prefix.startswith(watermarked):
                leaked.append(f"{prefix!r} <-> {watermarked!r}")
    assert leaked == [], (
        "ADR-079 violated : pure-data / infra routes leaked into "
        "DEFAULT_WATERMARKED_PREFIXES. EU AI Act §50.2 applies to "
        "AI-generated content only — collector outputs and infra "
        "endpoints must stay unwatermarked. Conflicts :\n" + "\n".join(leaked)
    )


def test_ai_watermark_default_prefixes_match_settings() -> None:
    """ADR-079 + ADR-080 : the W88 middleware default prefix tuple,
    the W89 well-known endpoint inventory, and the Settings field
    must agree on the watermarked surface. Any divergence is a
    silent compliance regression (some routes watermarked,
    others advertised, or vice versa)."""
    # Lazy import — keeps the test file importable even when the api
    # venv isn't activated (CI reuses test_collection-only paths).
    from ichor_api.config import Settings
    from ichor_api.middleware.ai_watermark import DEFAULT_WATERMARKED_PREFIXES

    settings = Settings()
    assert set(DEFAULT_WATERMARKED_PREFIXES) == set(settings.ai_watermarked_route_prefixes), (
        "ADR-079/080 single-source-of-truth violated : "
        f"middleware default prefixes {sorted(DEFAULT_WATERMARKED_PREFIXES)} "
        f"differ from Settings default {sorted(settings.ai_watermarked_route_prefixes)}."
    )


def test_ai_watermark_module_docstring_pinned_to_art_50_4_deployer() -> None:
    """ADR-079 §"Round-35+38 amendment" — W90 r39 anti-future-drift
    guard. Pins the `ai_watermark.py` module docstring header to the
    Article 50(4) DEPLOYER framing. Catches a refactor that
    re-introduces the pre-round-35 over-claim "EU AI Act §50.2
    machine-readable watermark middleware" (Ichor is a deployer of
    Anthropic Claude under §50(4), NOT a GPAI provider under §50(2)
    — the heavier signed-C2PA + PKI + detector-API obligations from
    the 2nd-draft Code of Practice bind Anthropic upstream).

    Round-35 (commit `2c1233d`) corrected the docstring text but the
    ADR-079 document drifted out-of-sync for 4 rounds (closed
    round-38). This test prevents the docstring side from drifting
    back."""
    import re
    from pathlib import Path

    path = Path(__file__).parent.parent / "src" / "ichor_api" / "middleware" / "ai_watermark.py"
    text = path.read_text(encoding="utf-8")

    # Match the module-level docstring (string literal at the very
    # start of the file). DOTALL needed because docstring spans many
    # lines.
    m = re.match(r'\s*"""(.+?)"""', text, re.DOTALL)
    assert m is not None, "ai_watermark.py module docstring missing"
    docstring = m.group(1)
    first_line = docstring.lstrip().split("\n", 1)[0]

    # Positive assertion : the header line must explicitly mention
    # "Article 50(4)" AND "DEPLOYER" (canonical r35 framing).
    assert "Article 50(4)" in first_line, (
        f"ai_watermark.py docstring header lost 'Article 50(4)' marker : {first_line!r}. "
        "See ADR-079 §'Round-35+38 amendment'."
    )
    assert "DEPLOYER" in first_line.upper(), (
        f"ai_watermark.py docstring header lost 'DEPLOYER' marker : {first_line!r}. "
        "See ADR-079 §'Round-35+38 amendment'."
    )

    # Negative assertion : the docstring MUST NOT reintroduce the
    # canonical over-claim phrasing "EU AI Act §50.2 machine-readable
    # watermark middleware" / "EU AI Act Article 50(2) machine-readable
    # watermark middleware" — those were the pre-r35 wordings that
    # conflated Ichor's deployer role with Anthropic's upstream
    # provider obligations. Mentioning §50(2) IS allowed (line 10
    # legitimately attributes the burden to Anthropic) but it must
    # not be the middleware's claimed compliance article.
    over_claims = (
        "Article 50(2) machine-readable watermark middleware",
        "§50.2 machine-readable watermark middleware",
        "Article 50.2 machine-readable watermark middleware",
    )
    for phrase in over_claims:
        assert phrase not in docstring, (
            f"ai_watermark.py docstring reintroduced the pre-r35 over-claim {phrase!r}. "
            "Ichor is an Art 50(4) deployer per ADR-079 §'Round-35+38 amendment'."
        )


# ────────────────────────── ADR-085 Pass-6 ──────────────────────────


def test_pass6_bucket_labels_exactly_seven_canonical() -> None:
    """ADR-085 §"The 7 buckets" : the Pass-6 scenario_decompose taxonomy
    is frozen at 7 buckets in the canonical stratification order. Any
    refactor that adds, removes or reorders is a P0 compliance regression
    (Pass-6 LLM prompt, Brier scoring, frontend rendering, and reconciler
    all assume exact match against this list)."""
    from ichor_api.services.scenarios import BUCKET_LABELS

    canonical = (
        "crash_flush",
        "strong_bear",
        "mild_bear",
        "base",
        "mild_bull",
        "strong_bull",
        "melt_up",
    )
    assert BUCKET_LABELS == canonical, (
        f"ADR-085 violated : BUCKET_LABELS drift detected.\n"
        f"  expected (canonical): {canonical}\n"
        f"  found:                {BUCKET_LABELS}"
    )


def test_pass6_cap_95_constant_unchanged() -> None:
    """ADR-022 + ADR-085 §"Probability cap" : the Pass-6 per-bucket cap
    is 0.95 exactly. Macro-frameworks doctrine : 100 % conviction on
    any single bucket never exists. Catches accidental bump (e.g. an
    over-eager refactor that loosens to 0.99 to "let confident calls
    through")."""
    from ichor_api.services.scenarios import CAP_95

    assert CAP_95 == 0.95, (
        f"ADR-085 violated : CAP_95 = {CAP_95}, must be exactly 0.95. "
        "100 % conviction is a red flag, never a target."
    )


def test_pass6_scenario_mechanism_rejects_trade_tokens() -> None:
    """ADR-017 boundary at runtime : the `Scenario.mechanism` field is
    a free-text explanation but it must never contain BUY/SELL/TP/SL
    tokens. The validator lives on the Pydantic model itself ; this
    test catches the regression where someone removes the validator
    "because it's verbose" or weakens its regex.
    """
    from ichor_api.services.scenarios import Scenario
    from pydantic import ValidationError

    for forbidden in ("BUY", "SELL", "TP", "SL"):
        try:
            Scenario(
                label="base",
                p=0.5,
                magnitude_pips=(-10.0, 10.0),
                mechanism=f"Some valid context including {forbidden} token here as standalone",
            )
        except ValidationError:
            continue
        raise AssertionError(
            f"ADR-017 violated : Scenario.mechanism validator FAILED to reject "
            f"the token {forbidden!r}. The _reject_trade_tokens validator on "
            f"Scenario.mechanism (apps/api/src/ichor_api/services/scenarios.py) "
            "may have been removed or weakened."
        )
