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
