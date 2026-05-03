"""Common scaffolding for every pass.

A pass owns :
  - a `name` (used in logs + cache keys),
  - a `system_prompt` (Claude persona + rubric, cacheable),
  - a `build_prompt(...)` that interpolates the data pool into the
    user-side prompt,
  - a `parse(text)` that turns the LLM's markdown/JSON reply into the
    pass's typed output.

Passes are pure : they never call the runner themselves. The
`Orchestrator` does that, so passes stay trivially testable.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar


class PassError(RuntimeError):
    """Raised when a pass cannot parse a runner response."""


T = TypeVar("T")


class Pass(ABC, Generic[T]):
    """Base class for the 4 passes."""

    name: str

    @property
    @abstractmethod
    def system_prompt(self) -> str: ...

    @abstractmethod
    def build_prompt(self, **kwargs: Any) -> str: ...

    @abstractmethod
    def parse(self, response_text: str) -> T: ...


# ─────────────────────── shared parsing helpers ────────────────────────


_FENCED_JSON_RE = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE
)
_BARE_JSON_RE = re.compile(r"(\{.*\})", re.DOTALL)


def extract_json_block(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of an LLM response.

    Tolerates the common shapes :
      - fenced ```json {...}``` block (preferred output format)
      - bare {...} object on its own line
      - prose around a JSON object
    Raises `PassError` if nothing parses.
    """
    candidates: list[str] = []
    m = _FENCED_JSON_RE.search(text)
    if m:
        candidates.append(m.group(1))
    m = _BARE_JSON_RE.search(text)
    if m:
        candidates.append(m.group(1))

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    raise PassError(
        f"could not extract JSON from response (first 200 chars): {text[:200]!r}"
    )
