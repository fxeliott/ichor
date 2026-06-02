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
from typing import Any


class PassError(RuntimeError):
    """Raised when a pass cannot parse a runner response."""


# ─────────────────────── shared language directive ─────────────────────
# Single source of truth (SSOT) appended to every pass system prompt so the
# trader-facing free-text the LLM emits (rationale / claim / condition /
# event / mechanism / notes / description …) renders in plain-French coach
# tone — Eliot's Prompt_Ichor §6.6 (coach) + §15 (niveau débutant FR) +
# §6.9 (no jargon dump). Before this, only Pass-6 scenarios instructed
# French, so Pass-2 mechanisms + Pass-4 invalidations rendered in ENGLISH on
# a French product (verified live on /briefing/EUR_USD 2026-06-02). JSON keys
# + enum values + source identifiers stay verbatim so nothing machine-side
# (Critic sourcing checks, ADR-017 regex, ORM enums) is affected.
FRENCH_COACH_DIRECTIVE = """

LANGUE & TON — COACH FR (obligatoire) :
  - Rédige TOUS les champs de texte libre lus par le trader (selon le
    schéma de cette passe : par ex. `rationale`, `claim`, `condition`,
    `event`, `expected_impact`, `notes`, `mechanism`, `description`) en
    FRANÇAIS clair, ton de coach pour un débutant motivé : pédagogique,
    précis, sans jargon laissé inexpliqué.
  - NE TRADUIS PAS et garde VERBATIM : les identifiants de source
    (series_id FRED, tickers, slugs Polymarket, URLs) et les nombres.
  - Les clés JSON et les valeurs d'énumération (long/short/neutral,
    quadrant, label, metric_name, direction, severity, …) restent en
    ANGLAIS — seul le texte explicatif destiné à l'humain passe en français.
  - Explique le « pourquoi » comme à quelqu'un qui découvre, sans jamais
    perdre en rigueur ni en précision. Aucune phrase explicative en anglais."""


class Pass[T](ABC):
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


_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)
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

    raise PassError(f"could not extract JSON from response (first 200 chars): {text[:200]!r}")
