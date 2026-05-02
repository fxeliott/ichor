"""Couche-2 24/7 agents (Cerebras/Groq via Pydantic AI).

Each agent has a single responsibility and produces structured output that
feeds the Bias Aggregator (Couche 3 ML). All agents follow the same pattern:
  - System prompt is hard-coded (versioned with the code)
  - Output is a Pydantic model (validation = first-class)
  - Provider failover via FallbackChain (no single point of failure)
"""

from .macro import MacroAgentOutput, MacroDriver, MacroTheme, make_macro_chain

__all__ = [
    "MacroAgentOutput",
    "MacroDriver",
    "MacroTheme",
    "make_macro_chain",
]
