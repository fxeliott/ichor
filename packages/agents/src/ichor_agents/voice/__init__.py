"""Audio synthesis for Ichor briefings.

Stack (per ADR-009 + AUDIT_V3 §3):
  - Primary: Azure Neural TTS FR free tier (5M chars/mo)
  - Fallback: Piper self-host on Hetzner CPU (siwis-medium MIT)
"""

from .tts import (
    AzureTTSDownError,
    AzureTTSQuotaExceeded,
    VoiceFR,
    azure_neural_tts,
    piper_local_tts,
    synthesize_briefing,
)

__all__ = [
    "AzureTTSDownError",
    "AzureTTSQuotaExceeded",
    "VoiceFR",
    "azure_neural_tts",
    "piper_local_tts",
    "synthesize_briefing",
]
