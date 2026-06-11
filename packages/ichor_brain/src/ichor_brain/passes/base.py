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
    perdre en rigueur ni en précision. Aucune phrase explicative en anglais.
  - Dans la PROSE explicative (le texte lu par le trader), n'écris JAMAIS un
    CODE machine brut : aucun identifiant en snake_case (ex. `usd_complacency`,
    `funding_stress`, `haven_bid`, `risk_on`, `goldilocks`), aucune valeur
    d'énumération brute, aucun nom de métrique ou de colonne laissé nu.
    Humanise-les TOUJOURS en langage clair (ex. « complaisance sur le dollar »,
    « tensions de financement », « ruée vers les valeurs refuges »,
    « contexte porteur du risque »). Les identifiants de SOURCE (series_id
    FRED, tickers, slugs Polymarket) peuvent être cités comme référence, mais
    toujours accompagnés de leur explication en clair.
  - NE MENTIONNE JAMAIS la mécanique interne du système dans la prose : pas
    de « Pass 1 / Pass 2 / Pass-6 / la passe N », pas de noms d'agents, de
    passes, de moteurs ni de modules internes. Le trader ne voit jamais la
    plomberie — seulement l'analyse, expliquée comme par un coach.
  - FRONTIÈRE ADR-017 — AUCUN ORDRE DE TRADING (CRITIQUE) : n'écris JAMAIS, dans
    AUCUN champ, un impératif d'achat/vente ni une instruction d'agir. Bannis
    absolument « acheter / achète / achetez / acheté / vendre / vends / vendez /
    vendu / buy / sell / long maintenant / short maintenant / prends position /
    coupe ta position / place un stop / take-profit » et TOUTE formule injonctive
    équivalente (FR ou EN). Exprime TOUJOURS le biais et la probabilité de façon
    DESCRIPTIVE — « le dossier penche haussier », « scénario baissier dominant à
    ~X % », « contexte porteur pour l'EUR » —, jamais « il faut acheter / signal
    de vendre ». Ichor ÉCLAIRE, il ne donne pas d'ordre. ⚠️ Une SEULE de ces
    formules fait REJETER la carte ENTIÈRE par la safety-gate (carte jamais
    publiée) : c'est la première cause de cartes manquantes — non négociable.
  - ⚠️ MOTS LITTÉRALEMENT INTERDITS, MÊME EN PHRASE DESCRIPTIVE : la
    safety-gate détecte les MOTS eux-mêmes, pas l'intention. N'emploie donc
    JAMAIS les mots « acheter », « vendre » (ni achète/achetez/vends/vendez,
    buy/sell, comprar/vender, kaufen/verkaufen) — même descriptivement
    (« pression à acheter » = carte REJETÉE, témoigné en production), même en
    citant un titre de presse, même à la forme négative. Reformule TOUJOURS :
    « pression acheteuse / vendeuse », « flux acheteurs / vendeurs »,
    « demande / offre », « appétit pour le risque », « intérêt haussier /
    baissier ». (Witness 2026-06-11 : 2 cartes sur 6 perdues sur ce seul mot.)"""


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
