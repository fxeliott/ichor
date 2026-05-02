"""Ichor agent package — Pydantic AI providers + agent factories.

Voie D constraint (ADR-009): no Anthropic API consumption. Production
Couche-1 quality work runs via apps/claude-runner (Max 20x subprocess);
Couche-2 24/7 automation runs via Cerebras + Groq free tiers wrapped here.
"""

__version__ = "0.0.0"
