"""Self-healing clamp for free-text LLM agent fields.

Every Couche-2 agent output carries an optional free-text ``notes`` caveat
field with a sanity ``max_length`` cap. The cap is a real DB / context-budget
bound — but enforcing it as a *hard* Pydantic constraint makes a harmless
overrun fatal: the whole agent run dies.

Witnessed prod failure (``ichor-couche2@cb_nlp.service``, 2026-06-09 16:15
CEST): the runner SUCCEEDED (valid JSON, 2023 chars) but the LLM emitted a
``notes`` value > 1000 chars → ``string_too_long`` ValidationError →
``ClaudeRunnerOutputError`` → ``AllProvidersFailed`` (no Cerebras/Groq creds)
→ systemd exit 1. The central-bank rhetoric dimension was silently killed
every fire. This is the same "valid runner output → Pydantic narrows → entire
run crashes" class already defended against in ``news_nlp`` (hallucinated
asset codes) and ``cb_nlp`` (``'mixed'`` bias token) — structural defense
beats prompt engineering.

A ``mode="before"`` validator built on :func:`truncate_free_text` clamps the
over-long string to the cap (with an ellipsis marker) BEFORE the length
constraint runs, turning a fatal crash into a graceful, lossy-but-alive
degradation. The cap survives as the sanity bound; only the failure mode
changes.
"""

from __future__ import annotations

#: Sentinel appended to a clamped string so downstream readers can tell the
#: note was truncated rather than naturally short.
_ELLIPSIS = "…"


def truncate_free_text(value: object, max_len: int) -> object:
    """Clamp an over-long free-text string to ``max_len`` chars.

    Non-string values (``None``, already-typed objects) and strings within the
    cap pass through unchanged, so the validator is byte-identical for every
    non-violating output. An over-long string is truncated to ``max_len``
    characters total (``max_len - 1`` content chars + a single ellipsis), which
    satisfies a ``Field(max_length=max_len)`` constraint applied afterwards.
    """
    if not isinstance(value, str) or len(value) <= max_len:
        return value
    if max_len <= 0:
        # Defensive: a non-positive cap admits no non-empty string. Never hit
        # by the real Couche-2 fields (caps are 120-1000) but keeps the helper
        # total — no IndexError, no negative-slice surprise.
        return ""
    return value[: max_len - 1].rstrip() + _ELLIPSIS
