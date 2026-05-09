"""ichor_brain — 4-pass Claude pipeline that produces session cards.

Public surface:
  - `Orchestrator` — runs régime → asset → stress → invalidation, applies
    the Critic Agent gate, returns a `SessionCard`.
  - `RunnerClient` — abstract LLM gateway. `HttpRunnerClient` posts to
    the local Win11 claude-runner over the Cloudflare Tunnel; tests use
    `InMemoryRunnerClient` to stub the pipeline.
  - `SessionCard` and per-pass result types — see `types.py`.
"""

from .orchestrator import Orchestrator, OrchestratorResult
from .runner_client import (
    HttpRunnerClient,
    InMemoryRunnerClient,
    RunnerCall,
    RunnerClient,
    RunnerResponse,
    ToolConfig,
)
from .types import (
    AssetSpecialization,
    BiasDirection,
    InvalidationConditions,
    RegimeReading,
    SessionCard,
    SessionType,
    StressTest,
)

__all__ = [
    "Orchestrator",
    "OrchestratorResult",
    "RunnerClient",
    "RunnerCall",
    "RunnerResponse",
    "InMemoryRunnerClient",
    "HttpRunnerClient",
    "ToolConfig",
    "SessionCard",
    "SessionType",
    "BiasDirection",
    "RegimeReading",
    "AssetSpecialization",
    "StressTest",
    "InvalidationConditions",
]

__version__ = "0.0.0"
