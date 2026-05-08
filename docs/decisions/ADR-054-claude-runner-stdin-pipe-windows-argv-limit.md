# ADR-054: claude-runner stdin pipe (Windows 32K argv limit fix)

- **Status**: Accepted
- **Date**: 2026-05-08
- **Deciders**: Eliot
- **Implements**: Phase I.3 — production session-cards + briefings + Couche-2
  failure (BLOCKER #2 post-wave 22)

## Context

Wave 22 audit (2026-05-08) revealed that the `ichor-session-cards@pre_ny`
batch was producing only **2 out of 8 cards** despite the wave 20
async/polling fix (ADR-053). Worse, three nominal `ichor-briefing@*`
services and two `ichor-couche2@*` runs failed the same day.

Logs all show the same pattern:

```
runner_client.async.completed elapsed_sec=5.1 status=error
batch.card_failed asset=GBP_USD error='async briefing task ...
   crashed: FileNotFoundError: [WinError 206] Nom de fichier ou
   extension trop long'
```

The error happened immediately (5.1 s) — well before any LLM
inference — meaning the subprocess never even started.

### Root cause — Windows 32 768-char `lpCommandLine` limit

`apps/claude-runner/src/ichor_claude_runner/subprocess_runner.py`
passed `prompt` (the full data_pool markdown, up to 200 KB by Pydantic
contract) **as an argv argument** to `claude -p <prompt>`:

```python
cmd = [settings.claude_binary, "-p", prompt, ..., "--append-system-prompt", persona_text]
proc = await asyncio.create_subprocess_exec(*cmd, ...)
```

On Windows, `subprocess` ultimately calls `CreateProcessW(lpCommandLine=...)`
which the Microsoft docs cap at **32 768 characters** for the
serialized command line. Passing a 27 KB prompt + 7 KB persona + flags
overflows that cap → the OS returns `ERROR_FILENAME_EXCED_RANGE` (206)
before the binary even runs. Python surfaces it as `FileNotFoundError:
[WinError 206]`.

Empirically the threshold landed at ~17 KB of `data_pool` content,
which matches the only two assets that DID succeed in the broken
batch (EUR_USD 16 980 chars, SPX500 15 152 chars). All six other
assets had `data_pool` >27 KB and crashed the same way.

## Decision

Pipe `prompt` via **stdin** instead of argv. Keep the persona inline
via `--append-system-prompt` (it stays well under 10 KB).

Concrete change in `subprocess_runner.run_claude`:

```python
cmd = [
    settings.claude_binary,
    "-p",
    "Read the task and full context piped via stdin, then respond per the system prompt.",
    "--output-format", "json",
    "--model", model,
    "--effort", effort,
    "--no-session-persistence",
    "--append-system-prompt", persona_text,
]
proc = await asyncio.create_subprocess_exec(
    *cmd,
    stdin=asyncio.subprocess.PIPE,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    cwd=str(workdir),
)
stdout, stderr = await asyncio.wait_for(
    proc.communicate(input=prompt.encode("utf-8")),
    timeout=settings.claude_timeout_sec,
)
```

The `-p` value becomes a short task wrapper (~80 chars) that instructs
claude to read its actual context from stdin. This matches the
canonical claude CLI usage pattern documented in the
[CLI reference](https://code.claude.com/docs/en/cli-reference): `cat
file | claude -p "task description"`.

### Why not write to a temp file and reference its path

Anthropic's "very large prompt" guidance (>100 KB) is to write the
context to a file and pre-authorize `Read` so claude reads it as a
tool call. That works but:

- adds one round-trip (a Read tool call) → +500 ms latency per pass.
- requires `--allowedTools "Read"` and a temp-file lifecycle (mkstemp
  - cleanup) not currently in scope.
- changes the semantics: claude sees the content as "tool output"
  rather than user input, which alters cache-breakpoint behaviour.

stdin pipe keeps the existing semantics, has no extra round-trip, and
the actual prompts are 15-30 KB — well under the documented 10 MB
stdin cap of claude CLI v2.1.128.

### Why not raise Windows `LongPathsEnabled` registry key

`LongPathsEnabled=1` only affects file _path_ length (260 → 32 767),
not the `CreateProcessW` command-line limit. The 32 768-char argv cap
is a hard Win32 API contract — there is no flag to bypass it.

## Consequences

### Positive

- **Production unblocked**: live verification on 2026-05-08 14:55 CEST
  showed GBP_USD (27 740 chars data_pool) persisting an approved card
  in 84 s after the fix, vs systematic crash before.
- **Zero schema change**: HttpRunnerClient contract unchanged —
  payload still `context_markdown` field. The async/polling pattern
  (ADR-053) keeps working as designed.
- **Couche-2 + briefings + session-cards** all benefit from the fix
  — they share the same `subprocess_runner.run_claude()` entry point.
- **Cross-platform**: Linux/macOS have `ARG_MAX` ~128KB-2MB so they
  weren't affected, but the stdin path is identical and safer
  long-term.
- **Regression-tested**: 5 new `tests/test_subprocess_runner.py`
  cases assert the prompt is NOT in argv and IS in stdin, with a
  30 KB synthetic prompt as the "would have crashed" probe.

### Negative

- **No more inline persona prompt-cache reuse via `-p prompt`**: the
  prompt-cache breakpoint moves to the stdin payload. Anthropic
  caches stdin content as well (verified empirically: cache_creation
  /cache_read fields populate normally) but this hasn't been
  long-running observed in prod yet.
- **Stdin known-bug GitHub anthropics/claude-code#7263**: large
  stdin in headless mode reportedly returns empty output. Live
  verification (46 KB stdin) returned a valid 78 KB response, so the
  bug seems resolved by v2.1.128. Will be monitored in 24 h prod.

## Implementation

- `apps/claude-runner/src/ichor_claude_runner/subprocess_runner.py:78-110` — pipe prompt via stdin.
- `apps/claude-runner/tests/test_subprocess_runner.py` — 5 new regression tests.
- No deploy required for Hetzner side — only Win11 claude-runner restart picked up.

## Verification

| Test                                                      | Pre-fix            | Post-fix                 |
| --------------------------------------------------------- | ------------------ | ------------------------ |
| Local pytest (22 cases)                                   | 17 pass            | 22 pass (+5 new)         |
| Live POST /async with 46 KB prompt                        | not run            | success 26 s             |
| Hetzner ichor-session-cards@pre_ny GBP_USD (27 740 chars) | crash WinError 206 | persist DB approved 84 s |

## Linked

- ADR-009 — Voie D (Max 20x via subprocess; the whole reason this
  code path exists).
- ADR-017 — Boundary preserved (no behavioral change).
- ADR-053 — async/polling fix layered on top.
