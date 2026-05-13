"""Phase D W117a — DSPy 3.2 BaseLM custom wrapper for Voie D (ADR-009).

W117 (GEPA meta-prompt optimizer) needs DSPy 3.2 to drive its evolutionary
prompt-mutation loop. DSPy's DEFAULT LM (`dspy.LM(model="claude-...")`)
routes via litellm → paid Anthropic API → VIOLATES ADR-009.

This module ships the ONLY allowed LM under DSPy : `ClaudeRunnerLM` —
inherits `dspy.BaseLM`, routes `forward()` through the existing
Couche-2 `call_agent_task_async` path → claude-runner Win11 subprocess
→ Max 20x plan, ZERO API spend.

W117a (this round) = foundation only. The class is instantiable + has
`forward()` that round-trips through claude-runner. W117b/c (future)
will wire GEPA optimizer + ADR-017 regex penalty fitness function on top.

DSPy capability properties (per researcher SOTA brief round-15) :
- `supports_function_calling = False` — claude-runner is text-only
- `supports_reasoning = False` — no extended-thinking through subprocess
- `supports_response_schema = False` — schema enforcement via _AddendumOut
  Pydantic pattern, not DSPy native
- `supported_params = {"temperature", "max_tokens", "stop"}`

Raises `dspy.ContextWindowExceededError` on 413 from claude-runner so
DSPy retry/truncation logic engages.

ADR-009 paranoia : when DSPy isn't installed (no `[phase-d-w117]`
extras), the module is still IMPORTABLE — `ClaudeRunnerLM` raises
RuntimeError on instantiation with a clear install hint. The W90
ADR-009 invariant test ensures `import anthropic` never sneaks in
via DSPy/litellm transitive deps.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

log = structlog.get_logger(__name__)


# Try-import : DSPy is optional. When missing, the wrapper class is a
# stub that raises on instantiation. This keeps the module importable
# in non-Phase-D-W117 environments (CI, dev, Hetzner without extras).
try:
    import dspy  # type: ignore[import-not-found]

    _DSPY_AVAILABLE = True
except ImportError:
    dspy = None  # type: ignore[assignment]
    _DSPY_AVAILABLE = False


_MISSING_DSPY_MSG = (
    "DSPy 3.2 not installed — Phase D W117 needs the [phase-d-w117] "
    "extras. Install with : `pip install -e 'apps/api[phase-d-w117]'` "
    "in the venv that will run the GEPA optimizer."
)


# ──────────────────────────── Voie D invariant ──────────────────────────


# CRITICAL : the only valid `model` string for ClaudeRunnerLM. DSPy's
# default LM uses these tokens to route via litellm → paid Anthropic
# API ; our wrapper IGNORES the model string at the API-call level and
# uses the ClaudeRunnerConfig's model field instead. The pinned tokens
# below are TRACER values for the invariant test only.
_ALLOWED_MODEL_TAGS = frozenset(
    {
        "ichor-claude-runner-haiku",
        "ichor-claude-runner-sonnet",
        "ichor-claude-runner-opus",
    }
)


if _DSPY_AVAILABLE:

    class ClaudeRunnerLM(dspy.BaseLM):  # type: ignore[misc]
        """DSPy 3.2 BaseLM that routes ALL forward() calls via the
        existing claude-runner subprocess (ADR-009 Voie D).

        Usage in W117 GEPA optimizer (future round) :

            from ichor_agents.claude_runner import ClaudeRunnerConfig
            from ichor_api.services.dspy_claude_runner_lm import ClaudeRunnerLM

            cfg = ClaudeRunnerConfig.from_env(model="haiku", effort="low")
            lm = ClaudeRunnerLM(runner_cfg=cfg)
            dspy.configure(lm=lm)
            # Now dspy.Predict / dspy.GEPA / etc. all route via Max plan.
        """

        def __init__(
            self,
            *,
            runner_cfg: Any,
            model_tag: str = "ichor-claude-runner-haiku",
            max_tokens: int = 4096,
            temperature: float = 0.0,
        ) -> None:
            if model_tag not in _ALLOWED_MODEL_TAGS:
                raise ValueError(
                    f"model_tag={model_tag!r} not in {sorted(_ALLOWED_MODEL_TAGS)} ; "
                    "use one of the ichor-claude-runner-* sentinels (the actual "
                    "model is picked from runner_cfg.model — Voie D)."
                )
            super().__init__(model=model_tag)
            self._runner_cfg = runner_cfg
            self._max_tokens = max_tokens
            self._temperature = temperature

        # ─── DSPy 3.2 capability properties (gate adapter behaviors) ───

        @property
        def supports_function_calling(self) -> bool:
            """Claude-runner is text-only over CF Tunnel ; no tool-use
            round-trip at the DSPy adapter layer."""
            return False

        @property
        def supports_reasoning(self) -> bool:
            """Extended-thinking not exposed through the subprocess path."""
            return False

        @property
        def supports_response_schema(self) -> bool:
            """Schema enforcement handled by callers via Pydantic (cf
            services/addendum_generator._AddendumOut)."""
            return False

        @property
        def supported_params(self) -> set[str]:
            return {"temperature", "max_tokens", "stop"}

        # ─── forward path (Voie D : routes via call_agent_task_async) ───

        def forward(
            self,
            prompt: str | None = None,
            messages: list[dict[str, str]] | None = None,
            **kwargs: Any,
        ) -> dict[str, Any]:
            """Sync wrapper around the async `call_agent_task_async` path.

            DSPy's BaseLM.forward is SYNC ; we drive the async runner
            call via `asyncio.run`. Refuses to run from inside an
            existing event loop (DSPy optimizers run sync top-level —
            nested-loop attempts indicate a configuration bug).
            """
            try:
                asyncio.get_running_loop()
                # If we get here, we're nested inside an event loop —
                # DSPy GEPA / Predict should NOT be invoked from async
                # context. Surface the bug.
                raise RuntimeError(
                    "ClaudeRunnerLM.forward called from inside an asyncio "
                    "event loop. DSPy 3.2 BaseLM is sync ; invoke from "
                    "top-level / sync context."
                )
            except RuntimeError as e:
                if "called from inside" in str(e):
                    raise
                # No running loop — safe path.

            return asyncio.run(self._async_forward(prompt=prompt, messages=messages, **kwargs))

        async def _async_forward(
            self,
            *,
            prompt: str | None,
            messages: list[dict[str, str]] | None,
            **kwargs: Any,
        ) -> dict[str, Any]:
            """Inner async path. Pure Voie D : lazy-imports
            ichor_agents.claude_runner.call_agent_task_async (the
            canonical W116c entry point)."""
            from ichor_agents.claude_runner import call_agent_task_async

            user_prompt = prompt if prompt is not None else self._messages_to_prompt(messages or [])
            system_prompt = kwargs.get("system", "")

            try:
                # call_agent_task_async returns the raw text (or a parsed
                # Pydantic if output_type given). We use raw text + let
                # DSPy adapters parse downstream.
                text = await call_agent_task_async(
                    cfg=self._runner_cfg,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    output_type=None,
                )
            except Exception as e:  # noqa: BLE001 — surface as DSPy-shape error
                # Map runner failures to DSPy's exception family when
                # possible. 413-equivalent (context too large) is the
                # only specific one we surface ; everything else is a
                # generic RuntimeError that DSPy retry will catch.
                error_str = str(e)
                if "413" in error_str or "context window" in error_str.lower():
                    raise dspy.ContextWindowExceededError(
                        f"claude-runner reported context exceeded : {e}"
                    ) from e
                raise

            return self._wrap_response(text)

        # ─── helpers ───

        def _messages_to_prompt(self, messages: list[dict[str, str]]) -> str:
            """Collapse a DSPy messages list to a single prompt string.
            The claude-runner agent-task path takes (system, user) only,
            so we flatten any extra turns into the user side."""
            return "\n\n".join(
                f"[{m.get('role', 'user')}] {m.get('content', '')}" for m in messages
            )

        def _wrap_response(self, text: str) -> dict[str, Any]:
            """Return a litellm-shape dict so DSPy adapters parse it
            uniformly with their internal LM responses."""
            return {
                "choices": [{"message": {"content": text}}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0},
            }

else:

    class ClaudeRunnerLM:  # type: ignore[no-redef]
        """Stub when DSPy is not installed. Raises on instantiation
        with a clear install hint."""

        def __init__(self, **_kw: Any) -> None:
            raise RuntimeError(_MISSING_DSPY_MSG)


__all__ = [
    "_ALLOWED_MODEL_TAGS",
    "_DSPY_AVAILABLE",
    "_MISSING_DSPY_MSG",
    "ClaudeRunnerLM",
]
