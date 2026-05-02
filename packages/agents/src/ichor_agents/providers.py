"""Multi-provider LLM wrappers for Couche-2 24/7 automation.

Both Cerebras and Groq expose OpenAI-compatible /chat/completions endpoints,
so we use Pydantic AI's OpenAI provider with custom base_url + api_key.

Free-tier limits (verified 2026-05 — see docs/AUDIT_V3.md §7):
  - Cerebras: 30 RPM Llama 3.3-70B (primary for high-quality automation)
  - Groq:     1000 RPD most models, 14400 RPD Llama 3.1-8B-instant (high-volume News-NLP)

Failover chain (per ADR-009 risk mitigation):
  Cerebras (primary)  →  Groq (fallback)  →  static template (last resort)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

ProviderName = Literal["cerebras", "groq"]


@dataclass(frozen=True)
class ProviderConfig:
    name: ProviderName
    base_url: str
    api_key_env: str
    default_model: str
    requests_per_minute: int
    requests_per_day: int


CEREBRAS = ProviderConfig(
    name="cerebras",
    base_url="https://api.cerebras.ai/v1",
    api_key_env="CEREBRAS_API_KEY",
    default_model="llama-3.3-70b",
    requests_per_minute=30,
    requests_per_day=30 * 60 * 24,  # nominal 24h ceiling
)

GROQ = ProviderConfig(
    name="groq",
    base_url="https://api.groq.com/openai/v1",
    api_key_env="GROQ_API_KEY",
    default_model="llama-3.3-70b-versatile",
    requests_per_minute=30,
    requests_per_day=1_000,
)

GROQ_HIGH_VOLUME = ProviderConfig(
    name="groq",
    base_url="https://api.groq.com/openai/v1",
    api_key_env="GROQ_API_KEY",
    default_model="llama-3.1-8b-instant",
    requests_per_minute=30,
    requests_per_day=14_400,
)


class MissingCredentials(RuntimeError):
    """API key env var not set or empty."""


def build_model(cfg: ProviderConfig, *, model_name: str | None = None) -> OpenAIModel:
    """Construct a Pydantic AI OpenAIModel for the given provider.

    Reads the API key from the env var named in cfg.api_key_env. Raises
    MissingCredentials if unset.
    """
    api_key = os.environ.get(cfg.api_key_env, "").strip()
    if not api_key:
        raise MissingCredentials(
            f"{cfg.api_key_env} env var is empty. "
            f"Get a free key at "
            f"{'https://cloud.cerebras.ai' if cfg.name == 'cerebras' else 'https://console.groq.com'} "
            f"and set it (e.g. via SOPS-decrypted infra/secrets/{cfg.name}.env)."
        )

    return OpenAIModel(
        model_name=model_name or cfg.default_model,
        provider=OpenAIProvider(base_url=cfg.base_url, api_key=api_key),
    )
